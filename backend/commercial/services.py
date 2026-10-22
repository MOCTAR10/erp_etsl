"""Droits métier M1 et calculs de pilotage pipeline (RF-ERP-01/04).

Lectures : tout utilisateur authentifié. Écriture : rôles porteurs du module
(proc. MANUEL 6.3-6.9 → circuit commercial, Direction des Projets). Montants/marge :
volontairement restreints (même logique que RF-59 dans `documents`).
"""

from django.db.models import Count, Q, Sum

from rest_framework.permissions import BasePermission

from users.models import User

from .models import Affaire, Opportunity

# Écriture sur le module Commercial (circuit commercial, MANUEL ch.2).
COMM_WRITE_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.SECRETAIRE_GENERAL,
    User.Role.DIRECTEUR_PROJETS,
    User.Role.DIRECTION,
    User.Role.CHARGE_AFFAIRES,  # lot a5 : saisie M1 par le chargé d'affaires
)

# Montants / marge visibles (chef_service volontairement exclu, pattern RF-59).
COMM_AMOUNT_ROLES = (
    User.Role.ADMIN,
    User.Role.COMPTABLE,
    User.Role.FINANCE,
    User.Role.DIRECTION,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.DIRECTEUR_PROJETS,
)


def is_admin_or_staff(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser or user.role == User.Role.ADMIN)


def can_manage_commercial(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in COMM_WRITE_ROLES


def can_see_amount(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in COMM_AMOUNT_ROLES


class CanManageCommercial(BasePermission):
    """Écriture réservée aux rôles commerciaux (commercial + admin)."""

    def has_permission(self, request, view):
        return can_manage_commercial(getattr(request, "user", None))


def pipeline_stats():
    """Pilotage M1.4 — pipeline par étape, taux de conversion, marge par segment, pipe pondéré 90/60/25."""
    active = Q(is_active=True)
    stages = (
        Opportunity.objects.filter(active)
        .values("stage")
        .annotate(
            count=Count("id"),
            total=Sum("amount"),
        )
        .order_by("stage")
    )
    by_stage = {row["stage"]: {"count": row["count"], "total": float(row["total"] or 0)} for row in stages}

    won = (
        Opportunity.objects.filter(active, stage="gagne")
        .aggregate(count=Count("id"), total=Sum("amount"))
    )
    lost = (
        Opportunity.objects.filter(active, stage="perdu")
        .aggregate(count=Count("id"))
    )
    closed = (won["count"] or 0) + (lost["count"] or 0)
    conversion_rate = round((won["count"] or 0) / closed, 4) if closed else 0.0

    margins = (
        Affaire.objects.filter(status__in=[Affaire.Status.EN_COURS, Affaire.Status.CLOTUREE])
        .exclude(client__isnull=True)
        .values("client__segment")
        .annotate(
            count=Count("id"),
            total_margin=Sum("margin"),
            total_amount=Sum("contract_amount"),
        )
    )
    margin_by_segment = {
        row["client__segment"] or "autre": {
            "count": row["count"],
            "total_margin": float(row["total_margin"] or 0),
            "total_amount": float(row["total_amount"] or 0),
        }
        for row in margins
    }

    return {
        "pipe_pondere": pipe_pondere(),
        "by_stage": by_stage,
        "conversion_rate": conversion_rate,
        "won_total": float(won["total"] or 0),
        "margin_by_segment": margin_by_segment,
    }


RETENTION_CONTRATS_ANS = 10


def controle_document_contractuel(document):
    """Document contractuel valide (CDC M1 §3.5 / §3.11) : version courante **signée** électroniquement (signature
    avancée achevée sur l'empreinte exacte de cette version, CL-OM-06) et classée en GED pour **10 ans** au moins.
    Renvoie le motif de refus, ou None."""
    from documents.models import SignatureRequest

    if document is None:
        return "Contrat signé requis : joignez le document GED signé électroniquement."
    version = document.current_version
    signe = version and SignatureRequest.objects.filter(
        version=version, status=SignatureRequest.Status.COMPLETED, document_sha256=version.sha256
    ).exists()
    if not signe:
        return "Le document n'est pas signé électroniquement (signature achevée sur sa version courante)."
    if not document.type_id or document.type.retention_years < RETENTION_CONTRATS_ANS:
        return f"Le document doit être classé dans un type GED conservé au moins {RETENTION_CONTRATS_ANS} ans."
    return None


def controle_crrl(affaire):
    """Démarrage d'affaire : compte-rendu de réunion de lancement (CRRL) tenu et archivé en GED (CDC M1 §3.6)."""
    from juridique.models import Reunion

    crrl = affaire.reunions.filter(type=Reunion.Type.LANCEMENT).exclude(statut=Reunion.Statut.PLANIFIEE)
    if not crrl.exists():
        return "Réunion de lancement (CRRL) non tenue : démarrage impossible."
    if not crrl.filter(compte_rendu__isnull=False).exists():
        return "Le compte-rendu de la réunion de lancement (CRRL) doit être archivé en GED avant le démarrage."
    return None


MARGE_AXES = ("client", "profil", "affaire", "responsable")


def _cle_marge(affaire, par):
    if par == "client":
        return affaire.client.partner.name if affaire.client_id else "—"
    if par == "responsable":
        return affaire.responsable.email if affaire.responsable_id else "—"
    if par == "affaire":
        return affaire.code
    if affaire.is_global_rental:
        return "global_rental"
    contrat = next(iter(affaire.contracts.all()), None)
    return contrat.profile if contrat else affaire.affaire_type


def marges_affaires(par, voir_montants):
    """Marges prévues (affaire) et réelles (grand livre, compte analytique de l'affaire, coût GR 618 isolé) par client,
    profil contractuel, affaire ou responsable (CDC M1 §3.4 / §3.7) — publiées vers M11 sans ressaisie."""
    from decimal import Decimal

    from django.db.models import Case, DecimalField, F, Value, When

    from accounting_kernel.models import AccountMove, AccountMoveLine
    from referentiels.models import Account

    affaires = list(
        Affaire.objects.exclude(status=Affaire.Status.ARCHIVEE)
        .select_related("client__partner", "responsable")
        .prefetch_related("contracts")
    )
    zero = Decimal("0")
    lignes_gl = (
        AccountMoveLine.objects.filter(
            analytic_account_id__in=[a.analytic_id for a in affaires if a.analytic_id],
            move__status__in=[AccountMove.Status.POSTED, AccountMove.Status.REVERSED],
        )
        .values("analytic_account_id")
        .annotate(
            produits=Sum(Case(When(account__account_type=Account.AccountType.INCOME, then=F("credit") - F("debit")),
                              default=Value(zero), output_field=DecimalField())),
            charges=Sum(Case(When(Q(account__account_type=Account.AccountType.EXPENSE) & ~Q(account__code="618000"),
                                  then=F("debit") - F("credit")), default=Value(zero), output_field=DecimalField())),
            cout_gr=Sum(Case(When(account__code="618000", then=F("debit") - F("credit")),
                             default=Value(zero), output_field=DecimalField())),
        )
    )
    reel = {row["analytic_account_id"]: row for row in lignes_gl}
    groupes = {}
    for affaire in affaires:
        cle = _cle_marge(affaire, par)
        g = groupes.setdefault(cle, {"cle": cle, "affaires": 0, "ca_prevu": zero, "marge_prevue": zero,
                                     "produits": zero, "charges": zero, "cout_gr": zero})
        g["affaires"] += 1
        g["ca_prevu"] += affaire.contract_amount or zero
        g["marge_prevue"] += affaire.margin or zero
        r = reel.get(affaire.analytic_id) or {}
        for champ in ("produits", "charges", "cout_gr"):
            g[champ] += r.get(champ) or zero
    lignes = []
    for g in sorted(groupes.values(), key=lambda x: x["cle"]):
        g["marge_reelle"] = g["produits"] - g["charges"] - g["cout_gr"]
        for champ in ("ca_prevu", "marge_prevue", "produits", "charges", "cout_gr", "marge_reelle"):
            g[champ] = f"{g[champ]:.2f}" if voir_montants else None
        lignes.append(g)
    return {"par": par, "lignes": lignes}


# Pondération du pipe 90 / 60 / 25 % (signé / en cours / prospect) — CDC M1 §3.4, M11 §4.4 (pipe → budget).
PIPE_CATEGORIES = {
    "signe": ("gagne",),
    "en_cours": ("offre", "negociation"),
    "prospect": ("prospection", "qualification"),
}


def pipe_pondere():
    from django.conf import settings

    poids = getattr(settings, "COMMERCIAL_PIPE_PONDERATION", {"signe": 0.90, "en_cours": 0.60, "prospect": 0.25})
    resultat = {}
    for categorie, etapes in PIPE_CATEGORIES.items():
        brut = Opportunity.objects.filter(is_active=True, stage__in=etapes).aggregate(t=Sum("amount"))["t"] or 0
        resultat[categorie] = round(float(brut) * poids[categorie], 2)
    resultat["total"] = round(sum(resultat.values()), 2)
    resultat["ponderations"] = poids
    return resultat
