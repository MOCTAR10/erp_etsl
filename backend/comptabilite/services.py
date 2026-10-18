"""Droits métier M10 — Comptabilité & Trésorerie (RF-ERP-90…94).

Écriture : rôles compte / finance, Secrétariat Général (visa des dépenses,
RF-ERP-W1), Opérations (dépenses atelier), Projets, Direction. Montants masqués
hors rôles autorisés (pattern RF-59). Lecture : tous utilisateurs authentifiés.
Les paiements rapprochent les pièces M2 (factures fournisseurs) ; la
refacturation intra-groupe s'appuie sur le partenaire flaggé `is_global_rental`
et le compte 618 (M4/M5, RF-ERP-93).
"""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.permissions import BasePermission

from accounting_kernel.models import AccountMove, AccountMoveLine
from users.models import User
from users.rbac import can_read_app

from .models import Lettrage, LigneLettree, ParametreCompta, Paiement

COMPTA_WRITE_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.SECRETAIRE_GENERAL,
    User.Role.DIRECTEUR_PROJETS,
    User.Role.DIRECTEUR_OPERATIONS,
    User.Role.FINANCE,
    User.Role.COMPTABLE,
    User.Role.DIRECTION,
)

COMPTA_AMOUNT_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.SECRETAIRE_GENERAL,
    User.Role.FINANCE,
    User.Role.COMPTABLE,
    User.Role.DIRECTION,
)


def is_admin_or_staff(user):
    return user.is_authenticated and (
        user.is_staff or user.is_superuser or user.role == User.Role.ADMIN
    )


def can_manage_compta(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in COMPTA_WRITE_ROLES


def can_see_amount(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in COMPTA_AMOUNT_ROLES


class CanManageCompta(BasePermission):
    """Lecture authentifiée ; écriture réservée aux rôles comptables / finance."""

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return can_read_app(getattr(request, "user", None), "comptabilite")
        return can_manage_compta(getattr(request, "user", None))


class CanValidateCompta(BasePermission):
    """Comptabilisation / validation des paiements : cercle restreint (RF-33)."""

    message = "Rôle non autorisé à comptabiliser un paiement."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return is_admin_or_staff(user) or user.role in COMPTA_AMOUNT_ROLES


def _account(code):
    """Compte du plan SYSCOHADA ou erreur métier claire (jamais un 500 DoesNotExist)."""
    from referentiels.models import Account

    try:
        return Account.objects.get(code=code)
    except Account.DoesNotExist:
        raise ValidationError(f"Compte {code} absent du plan comptable (seed_referentiels).")


@transaction.atomic
def build_paiement_move(paiement, user):
    """Construit et comptabilise l'écriture d'un paiement via le noyau comptable.

    Décaissement : Débit compte dépense (601/602/618…) / Crédit banque (512x).
    Encaissement : Débit banque (512x) / Crédit produit (701/706…) hors TVA 18 %
    restituée via la TVA sur opérations (gestion simplifiée : ligne produit HT,
    FAQ — la TVA est portée par les écritures de facturation M2 via `integrations`).
    Refacturation intra-groupe : compte de dépense 618000 (M4/M5).
    """
    from accounting_kernel.models import Journal
    from accounting_kernel.services import period_for_date, post_move
    from referentiels.models import Account, Partner

    # Verrou : deux clics / deux utilisateurs simultanés ne produisent qu'une écriture.
    Paiement.objects.select_for_update().get(pk=paiement.pk)
    paiement.refresh_from_db()  # l'instance de l'appelant reflète l'état verrouillé
    if paiement.move_id or paiement.statut == Paiement.Statut.VALIDE:
        raise ValidationError("Paiement déjà comptabilisé.")
    if paiement.statut == Paiement.Statut.ANNULE:
        raise ValidationError("Paiement annulé — comptabilisation impossible.")
    if paiement.montant is None or paiement.montant <= 0:
        raise ValidationError("Le montant du paiement doit être strictement positif.")
    if paiement.engagement_id:
        from .models import Engagement

        eng = paiement.engagement
        if eng.statut != Engagement.Statut.APPROUVE:
            raise ValidationError("Engagement non approuvé — paiement impossible (proc. 4.3).")
        if paiement.sens == paiement.Sens.SORTIE and paiement.montant > eng.solde:
            raise ValidationError(
                f"Dépassement de l'engagement : solde disponible {eng.solde}, paiement {paiement.montant}."
            )

    banque = paiement.compte_bancaire.compte_comptable
    journal_codes = {"especes": "CAI", "cheque": "BQ", "virement": "BQ", "cfonb": "BQ", "autre": "OD"}
    try:
        journal = Journal.objects.get(code=journal_codes[paiement.mode])
    except Journal.DoesNotExist:
        raise ValidationError(f"Journal {journal_codes[paiement.mode]} absent (seed_accounting).")
    try:
        period = period_for_date(paiement.date)
    except ValidationError as exc:
        raise ValidationError(str(exc))

    # Détermination des comptes.
    tiers = paiement.tiers
    if paiement.sens == paiement.Sens.SORTIE:
        if paiement.imputation_618:
            compte_depense = _account("618000")
        elif paiement.engagement_id:
            compte_depense = paiement.engagement.compte_depense
        elif tiers and tiers.kind in (Partner.Kind.FOURNISSEUR, Partner.Kind.BOTH):
            compte_depense = _account("401100" if tiers.is_global_rental else "401000")
        else:
            compte_depense = _account("601000")
    else:
        compte_depense = _account("411100" if (tiers and tiers.is_global_rental) else "411000")

    montant = Decimal(paiement.montant)
    from accounting_kernel.models import AccountMove, AccountMoveLine

    move = AccountMove.objects.create(
        journal=journal,
        period=period,
        date=paiement.date,
        reference=paiement.reference or paiement.code,
        label=f"{paiement.get_sens_display()} — {paiement.engagement.objet if paiement.engagement_id else (paiement.tiers.name if paiement.tiers_id else '')}",
        source="M10",
        source_ref=paiement.code,
        status=AccountMove.Status.DRAFT,
    )
    AccountMoveLine.objects.create(
        move=move,
        account=compte_depense,
        partner=paiement.tiers,
        label=paiement.engagement.objet if paiement.engagement_id else (paiement.tiers.name if paiement.tiers_id else paiement.get_sens_display()),
        debit=montant if paiement.sens == paiement.Sens.SORTIE else 0,
        credit=montant if paiement.sens == paiement.Sens.ENTREE else 0,
        order=1,
    )
    AccountMoveLine.objects.create(
        move=move,
        account=banque,
        partner=None,
        label=paiement.compte_bancaire.label,
        debit=montant if paiement.sens == paiement.Sens.ENTREE else 0,
        credit=montant if paiement.sens == paiement.Sens.SORTIE else 0,
        order=2,
    )
    posted = post_move(move, user=user)
    paiement.move = posted
    paiement.statut = paiement.Statut.VALIDE
    paiement.save(update_fields=["move", "statut", "updated_at"])
    return posted


def compute_declaration_tva(declaration):
    """Recalcule la TVA d'un mois à partir des paiements validés du mois.

    Base imposable = encaissements produits (entrees) ; TVA collectée = 18 %.
    TVA déductible = 18 % des décaissements hors refacturation intra-groupe.
    (Approche opérationnelle M10 ; la reprise SAGE / comptabilisation exacte
    reste celle du référentiel — SYSCOHADA révisée via `accounting_kernel`.)
    """
    from datetime import date as dt

    start = declaration.mois
    end = dt(start.year, start.month % 12 + 1, 1)
    if start.month == 12:
        end = dt(start.year + 1, 1, 1)

    paiements = Paiement.objects.filter(
        statut=Paiement.Statut.VALIDE, date__gte=start, date__lt=end
    )
    taux = Decimal(declaration.taux_tva.taux) / 100

    base = sum((p.montant for p in paiements.filter(sens=Paiement.Sens.ENTREE)), Decimal("0"))
    collectee = base * taux
    deductible = sum(
        (
            p.montant for p in paiements.filter(sens=Paiement.Sens.SORTIE).exclude(imputation_618=True)
        ),
        Decimal("0"),
    ) * taux

    declaration.base_imposable = base
    declaration.tva_collectee = collectee.quantize(Decimal("0.01"))
    declaration.tva_deductible = deductible.quantize(Decimal("0.01"))
    declaration.net_a_payer = (collectee - deductible).quantize(Decimal("0.01"))
    declaration.save(
        update_fields=[
            "base_imposable",
            "tva_collectee",
            "tva_deductible",
            "net_a_payer",
        ]
    )
    return declaration


# --------------------------------------------------------------------------------------------------
# Paramètres modifiables (valeur = donnée ETSL, défaut provisoire créé à la volée)
# --------------------------------------------------------------------------------------------------
PARAMETRES_DEFAUT = {
    "LETTRAGE_TOLERANCE": ("Tolérance d'écart de lettrage", Decimal("0"), "FCFA"),
    "LETTRAGE_DELAI_ANOMALIE_JOURS": (
        "Ancienneté d'une ligne non lettrée signalée en anomalie", Decimal("90"), "jours"),
}


def get_param(code):
    """Valeur du paramètre `code` ; crée le défaut provisoire si absent."""
    label, valeur, unite = PARAMETRES_DEFAUT[code]
    obj, _ = ParametreCompta.objects.get_or_create(
        code=code, defaults={"label": label, "valeur": valeur, "unite": unite}
    )
    return obj.valeur


def parametres_provisoires(codes):
    """Vrai si l'un des paramètres `codes` n'est pas encore confirmé par ETSL."""
    for c in codes:
        get_param(c)
    return ParametreCompta.objects.filter(code__in=codes).exclude(statut_valeur="confirme").exists()


# --------------------------------------------------------------------------------------------------
# Lettrage (RF-ERP-91) — n'écrit jamais dans les lignes d'écriture (immuables)
# --------------------------------------------------------------------------------------------------
LIGNES_COMPTABILISEES = (AccountMove.Status.POSTED, AccountMove.Status.REVERSED)


def _lignes_libres(compte, partner=None):
    qs = AccountMoveLine.objects.filter(
        account=compte, move__status__in=LIGNES_COMPTABILISEES, lettrage_actif__isnull=True
    ).select_related("move")
    if partner is not None:
        qs = qs.filter(partner=partner)
    return qs.order_by("move__date", "id")


@transaction.atomic
def lettrer_lignes(lignes, user, automatique=False):
    """Crée un lettrage sur `lignes` (AccountMoveLine) ; ValidationError si incohérent."""
    ids = [l.id for l in lignes]
    if len(set(ids)) < 2:
        raise ValidationError("Un lettrage porte sur au moins deux lignes.")
    lignes = list(
        AccountMoveLine.objects.select_for_update(of=("self",))
        .select_related("move", "account", "partner").filter(id__in=ids)
    )
    if len({l.account_id for l in lignes}) != 1:
        raise ValidationError("Toutes les lignes doivent appartenir au même compte.")
    compte = lignes[0].account
    if not compte.reconcile:
        raise ValidationError(f"Le compte {compte.code} n'est pas lettrable.")
    if any(l.move.status not in LIGNES_COMPTABILISEES for l in lignes):
        raise ValidationError("Seules les lignes d'écritures comptabilisées sont lettrables.")
    if LigneLettree.objects.filter(ligne_id__in=ids).exists():
        raise ValidationError("Une des lignes est déjà lettrée.")
    if len({l.partner_id for l in lignes}) != 1:
        raise ValidationError("Toutes les lignes doivent concerner le même tiers.")
    ecart = abs(sum((l.debit - l.credit for l in lignes), Decimal("0")))
    if ecart > get_param("LETTRAGE_TOLERANCE"):
        raise ValidationError(f"Lettrage déséquilibré : écart {ecart} supérieur à la tolérance.")
    lettrage = Lettrage.objects.create(
        compte=compte, partner=lignes[0].partner, ecart=ecart, automatique=automatique, created_by=user
    )
    LigneLettree.objects.bulk_create([LigneLettree(lettrage=lettrage, ligne=l) for l in lignes])
    return lettrage


@transaction.atomic
def delettrer(lettrage, user, motif):
    lettrage = Lettrage.objects.select_for_update().get(pk=lettrage.pk)
    if lettrage.statut != Lettrage.Statut.ACTIF:
        raise ValidationError("Lettrage déjà annulé.")
    if not (motif or "").strip():
        raise ValidationError("Le motif du dé-lettrage est obligatoire.")
    lettrage.lignes.all().delete()
    lettrage.statut = Lettrage.Statut.ANNULE
    lettrage.annule_par = user
    lettrage.annule_le = timezone.now()
    lettrage.motif_annulation = motif.strip()[:250]
    lettrage.save()
    return lettrage


def _essayer(lignes, user):
    try:
        with transaction.atomic():
            return lettrer_lignes(lignes, user, automatique=True)
    except ValidationError:
        return None


@transaction.atomic
def lettrer_auto(compte, user, partner=None):
    """Lettrage automatique : (1) groupes de même tiers + même référence qui s'équilibrent ;
    (2) montants uniques côté débit et côté crédit pour un même tiers. Retourne (lettrages créés, lignes restantes)."""
    if not compte.reconcile:
        raise ValidationError(f"Le compte {compte.code} n'est pas lettrable.")
    tol = get_param("LETTRAGE_TOLERANCE")
    crees = 0
    par_tiers = {}
    for l in _lignes_libres(compte, partner):
        if l.partner_id:
            par_tiers.setdefault(l.partner_id, []).append(l)
    for lignes in par_tiers.values():
        restantes, groupes = [], {}
        for l in lignes:
            cle = (l.move.reference or l.move.source_ref or "").strip()
            (groupes.setdefault(cle, []) if cle else restantes).append(l)
        for g in groupes.values():
            equilibre = abs(sum((x.debit - x.credit for x in g), Decimal("0"))) <= tol
            if len(g) >= 2 and any(x.debit for x in g) and any(x.credit for x in g) and equilibre:
                crees += 1 if _essayer(g, user) else 0
            else:
                restantes.extend(g)
        debits, credits = {}, {}
        for l in restantes:
            if l.debit:
                debits.setdefault(l.debit, []).append(l)
            else:
                credits.setdefault(l.credit, []).append(l)
        for montant, d in debits.items():
            c = credits.get(montant)
            if c and len(d) == 1 and len(c) == 1:
                crees += 1 if _essayer([d[0], c[0]], user) else 0
    return crees, _lignes_libres(compte, partner).count()


def anomalies_lettrage(compte):
    """Lignes non lettrées jugées anormales : sans tiers, ou plus anciennes que le délai paramétré."""
    delai = int(get_param("LETTRAGE_DELAI_ANOMALIE_JOURS"))
    limite = timezone.localdate() - timedelta(days=delai)
    out = []
    for l in _lignes_libres(compte):
        if not l.partner_id:
            motif = "sans_tiers"
        elif l.move.date < limite:
            motif = "ancienne"
        else:
            continue
        out.append({
            "ligne": str(l.id), "motif": motif, "date": l.move.date, "reference": l.move.reference,
            "debit": l.debit, "credit": l.credit, "tiers": str(l.partner_id) if l.partner_id else None,
        })
    return delai, out
