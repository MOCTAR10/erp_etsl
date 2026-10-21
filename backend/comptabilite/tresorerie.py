"""Trésorerie prévisionnelle M10 : plan glissant de N semaines (13 par défaut), prévu / réalisé, alerte de seuil.

Prévu = prévisions saisies (salaires, impôts, financement…) + factures clients émises non lettrées (à l'échéance)
+ factures fournisseurs comptabilisées non réglées (date de facture + délai paramétré). Réalisé = mouvements
comptabilisés des comptes de trésorerie (classe 5) de la semaine. Horizon, seuil d'alerte et délai fournisseur
sont des paramètres ETSL, provisoires jusqu'à confirmation.
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from accounting_kernel.models import AccountMove, AccountMoveLine

from .etats import semaine
from .models import FactureClient, PrevisionTresorerie
from .services import get_param, parametres_provisoires

ZERO = Decimal("0")
CENT = Decimal("0.01")
COMPTABILISEES = (AccountMove.Status.POSTED, AccountMove.Status.REVERSED)
PARAMS = ["TRESO_HORIZON_SEMAINES", "TRESO_SEUIL_ALERTE", "TRESO_DELAI_FOURNISSEUR_JOURS"]


def _treso():
    return AccountMoveLine.objects.filter(move__status__in=COMPTABILISEES, account__account_class=5)


def solde_tresorerie(avant):
    agg = _treso().filter(move__date__lt=avant).aggregate(d=Sum("debit"), c=Sum("credit"))
    return (agg["d"] or ZERO) - (agg["c"] or ZERO)


def _echeances_clients():
    """(date, montant) des factures clients émises dont la créance 411 n'est pas lettrée."""
    out = []
    for f in FactureClient.objects.filter(statut=FactureClient.Statut.EMISE, nature=FactureClient.Nature.FACTURE).select_related("move"):
        if f.move_id and not f.move.lines.filter(account__code__startswith="411", lettrage_actif__isnull=False).exists():
            out.append((f.echeance or f.date, f.montant_ttc, f"Facture {f.code}"))
    return out


def _echeances_fournisseurs(delai):
    from achats.models import PurchaseInvoice

    out = []
    for inv in PurchaseInvoice.objects.filter(status=PurchaseInvoice.Status.COMPTABILISEE).prefetch_related("lines", "paiements"):
        if inv.paiements.filter(statut="valide").exists():
            continue
        out.append((inv.invoice_date + timedelta(days=delai), inv.total_ttc, f"Facture fournisseur {inv.code}"))
    return out


def plan_tresorerie(debut=None, semaines=None):
    """Plan semaine par semaine à partir du lundi de `debut` (aujourd'hui par défaut)."""
    aujourdhui = timezone.localdate()
    lundi0 = semaine(debut or aujourdhui)
    n = int(semaines or get_param("TRESO_HORIZON_SEMAINES"))
    n = max(1, min(n, 52))
    seuil = get_param("TRESO_SEUIL_ALERTE")
    delai = int(get_param("TRESO_DELAI_FOURNISSEUR_JOURS"))
    clients, fournisseurs = _echeances_clients(), _echeances_fournisseurs(delai)
    previsions = list(PrevisionTresorerie.objects.filter(date_prevue__lt=lundi0 + timedelta(weeks=n)))
    semaine_courante = semaine(aujourdhui)
    solde_prevu = solde_tresorerie(lundi0)
    solde_reel = solde_prevu
    rows, alertes = [], []
    for i in range(n):
        lundi = lundi0 + timedelta(weeks=i)
        dimanche = lundi + timedelta(days=6)
        premiere = i == 0

        def dans(d):
            # Les échéances échues non réglées sont reportées sur la première semaine du plan.
            return lundi <= d <= dimanche or (premiere and d < lundi0)

        enc = sum((m for d, m, _ in clients if dans(d)), ZERO)
        dec = sum((m for d, m, _ in fournisseurs if dans(d)), ZERO)
        for p in previsions:
            if dans(p.date_prevue):
                if p.sens == PrevisionTresorerie.Sens.ENTREE:
                    enc += p.montant
                else:
                    dec += p.montant
        reel = _treso().filter(move__date__gte=lundi, move__date__lte=dimanche).aggregate(d=Sum("debit"), c=Sum("credit"))
        reel_enc, reel_dec = reel["d"] or ZERO, reel["c"] or ZERO
        passee = lundi <= semaine_courante
        debut_prevu = solde_prevu
        solde_prevu = solde_prevu + enc - dec
        if passee:
            solde_reel = solde_reel + reel_enc - reel_dec
        alerte = solde_prevu < seuil
        if alerte:
            alertes.append(lundi.isoformat())
        rows.append({
            "semaine": lundi.isoformat(), "fin": dimanche.isoformat(), "numero": lundi.isocalendar()[1],
            "solde_debut": debut_prevu.quantize(CENT),
            "prevu_encaissements": enc.quantize(CENT), "prevu_decaissements": dec.quantize(CENT),
            "realise_encaissements": reel_enc.quantize(CENT) if passee else None,
            "realise_decaissements": reel_dec.quantize(CENT) if passee else None,
            "ecart": ((reel_enc - reel_dec) - (enc - dec)).quantize(CENT) if passee else None,
            "solde_fin_prevu": solde_prevu.quantize(CENT),
            "solde_fin_reel": solde_reel.quantize(CENT) if passee else None,
            "alerte": alerte,
        })
    return {
        "debut": lundi0.isoformat(), "semaines": n, "seuil": seuil.quantize(CENT),
        "solde_initial": solde_tresorerie(lundi0).quantize(CENT), "alertes": alertes, "rows": rows,
        "provisoire": parametres_provisoires(PARAMS),
    }


def alerter_tresorerie():
    """Notifie (base + e-mail) Finance, Comptable et Direction générale si le solde prévu passe sous le seuil
    dans l'horizon ; une alerte par jour au plus."""
    from users.models import User
    from workflow.models import Notification
    from workflow.notifications import notify

    plan = plan_tresorerie()
    if not plan["alertes"]:
        return []
    premiere = plan["alertes"][0]
    sujet = "Trésorerie prévisionnelle sous le seuil d'alerte"
    message = (
        f"Le solde de trésorerie prévu passe sous le seuil de {plan['seuil']:,.0f} F la semaine du {premiere} "
        f"({len(plan['alertes'])} semaine(s) en alerte sur {plan['semaines']})."
    ).replace(",", " ")
    debut_jour = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    notifies = []
    for user in User.objects.filter(
        is_active=True, role__in=(User.Role.FINANCE, User.Role.COMPTABLE, User.Role.PDG, User.Role.DGA)
    ):
        if not Notification.objects.filter(user=user, subject=sujet, created_at__gte=debut_jour).exists():
            notify(user, sujet, message, kind="reminder")
            notifies.append(user.email)
    return notifies
