"""Reconnaissance du revenu à l'avancement (M10 → M11 / M1) — contrats au forfait (EPC, travaux).

% d'avancement d'une affaire à une date d'arrêté, selon la méthode du paramètre provisoire `REVENU_METHODE` :
  1 = coûts engagés : charges réelles (classe 6, imputées au compte analytique de l'affaire, comptabilisées) /
      budget de charges de l'affaire (M11, budgets non brouillons) ;
  2 = situations de travaux (M3) : avancement de la dernière situation validée ou facturée à la date d'arrêté.
Revenu cumulé = montant du contrat (contrat actif M1, avenants signés inclus ; à défaut montant de l'affaire) × %.
Comparé au facturé HT cumulé (factures − avoirs émis à la date) :
  revenu > facturé → produits à recevoir   : Dr 4181 « Clients, factures à établir » / Cr 706 ;
  revenu < facturé → produits constatés d'avance : Dr 706 / Cr 477.
La reconnaissance suivante de la même affaire extourne la précédente (une seule position en vigueur).
"""

from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum

ZERO = Decimal("0")
CENT = Decimal("100")
METHODES = {1: "couts", 2: "situations"}
LIBELLES = {"couts": "Coûts engagés / budget de charges", "situations": "Situations de travaux validées"}


def _param(code):
    from .services import get_param

    return get_param(code)


def methode_courante():
    return METHODES.get(int(_param("REVENU_METHODE")), "situations")


def ca_reference(affaire):
    from .retenues import contrat_affaire

    contrat = contrat_affaire(affaire.pk)
    if contrat is not None and contrat.montant_actuel:
        return Decimal(contrat.montant_actuel), f"contrat {contrat.code}"
    return Decimal(affaire.contract_amount or 0), "montant de l'affaire"


def _pct_couts(affaire, jour):
    from accounting_kernel.models import AccountMove, AccountMoveLine
    from controle_gestion.models import Budget

    if not affaire.analytic_id:
        return ZERO, "affaire sans compte analytique : aucun coût imputé"
    agg = AccountMoveLine.objects.filter(
        analytic_account_id=affaire.analytic_id, account__code__startswith="6", move__date__lte=jour,
        move__status__in=(AccountMove.Status.POSTED, AccountMove.Status.REVERSED),
    ).aggregate(d=Sum("debit"), c=Sum("credit"))
    couts = (agg["d"] or ZERO) - (agg["c"] or ZERO)
    budget = Budget.objects.filter(
        analytic_id=affaire.analytic_id, type_budget=Budget.TypeBudget.CHARGE
    ).exclude(statut=Budget.Statut.BROUILLON).aggregate(t=Sum("montant"))["t"] or ZERO
    if budget <= 0:
        raise ValidationError(
            f"Affaire {affaire.code} : aucun budget de charges approuvé (M11) — méthode des coûts impossible."
        )
    pct = min(CENT, max(ZERO, couts * CENT / budget))
    return pct, f"coûts {couts:.0f} / budget {budget:.0f}"


def _pct_situations(affaire, jour):
    from operations.models import SituationTravaux

    sit = SituationTravaux.objects.filter(
        affaire=affaire, period_end__lte=jour,
        status__in=(SituationTravaux.Status.VALIDEE, SituationTravaux.Status.FACTUREE),
    ).order_by("-period_end", "-progress").first()
    if sit is None:
        return ZERO, "aucune situation validée"
    return Decimal(sit.progress), f"situation {sit.code} ({sit.progress} %)"


def facture_cumule(affaire, jour):
    from .models import FactureClient

    qs = FactureClient.objects.filter(affaire=affaire, statut=FactureClient.Statut.EMISE, date__lte=jour)
    agg = qs.aggregate(
        f=Sum("montant_ht", filter=Q(nature=FactureClient.Nature.FACTURE)),
        a=Sum("montant_ht", filter=Q(nature=FactureClient.Nature.AVOIR)),
    )
    return (agg["f"] or ZERO) - (agg["a"] or ZERO)


def calculer(affaire, jour, methode=None):
    methode = methode or methode_courante()
    ca, base_ca = ca_reference(affaire)
    pct, detail = (_pct_couts if methode == "couts" else _pct_situations)(affaire, jour)
    pct = pct.quantize(Decimal("0.01"), ROUND_HALF_UP)
    revenu = (ca * pct / CENT).quantize(Decimal("1"), ROUND_HALF_UP)
    facture = facture_cumule(affaire, jour)
    ecart = revenu - facture
    return {
        "affaire": str(affaire.pk), "affaire_code": affaire.code, "affaire_label": affaire.title,
        "methode": methode, "methode_label": LIBELLES[methode], "pct_avancement": pct, "ca_reference": ca,
        "revenu_cumule": revenu, "facture_cumule": facture, "ecart": ecart,
        "nature": "produits_a_recevoir" if ecart > 0 else ("produits_constates_avance" if ecart < 0 else "aucune"),
        "detail": f"{detail} · base : {base_ca}"[:250],
    }


def apercu(jour):
    """Toutes les affaires portant un montant (contrat ou affaire) : calcul sans écriture ; erreurs signalées."""
    from commercial.models import Affaire

    sortie = []
    for affaire in Affaire.objects.filter(status__in=(Affaire.Status.CONFIRMEE, Affaire.Status.EN_COURS)).order_by("code"):
        try:
            row = calculer(affaire, jour)
        except ValidationError as exc:
            row = {"affaire": str(affaire.pk), "affaire_code": affaire.code, "affaire_label": affaire.title,
                   "erreur": exc.messages[0]}
        else:
            if not row["ca_reference"]:
                continue
        sortie.append(row)
    return sortie


def _comptes():
    from .devises import compte

    return (
        compte("418100", "Clients — factures à établir (produits à recevoir)", 4, "asset"),
        compte("477000", "Produits constatés d'avance", 4, "liability"),
        compte("706000", "Services vendus / prestations", 7, "income"),
    )


@transaction.atomic
def comptabiliser(affaire, jour, user):
    from accounting_kernel.models import AccountMove, AccountMoveLine, Journal
    from accounting_kernel.services import period_for_date, post_move, reverse_move
    from commercial.models import Affaire

    from .models import ReconnaissanceRevenu

    affaire = Affaire.objects.select_for_update(of=("self",)).get(pk=affaire.pk)
    calc = calculer(affaire, jour)
    if not calc["ca_reference"]:
        raise ValidationError(f"Affaire {affaire.code} sans montant de contrat : rien à reconnaître.")
    dernier = (ReconnaissanceRevenu.objects.select_for_update(of=("self",))
               .filter(affaire=affaire, statut=ReconnaissanceRevenu.Statut.EN_VIGUEUR).order_by("-date_arrete").first())
    if dernier and dernier.date_arrete > jour:
        raise ValidationError(f"Une reconnaissance plus récente existe déjà ({dernier.code} au {dernier.date_arrete:%d/%m/%Y}).")
    if dernier:
        if dernier.move_id and dernier.move.status == AccountMove.Status.POSTED:
            reverse_move(dernier.move, user=user, date=jour, reference=f"Extourne {dernier.code}",
                         label=f"Extourne reconnaissance {dernier.code}")
        dernier.statut = ReconnaissanceRevenu.Statut.EXTOURNEE
        dernier.save(update_fields=["statut"])
    move = None
    ecart = calc["ecart"]
    if ecart:
        c418, c477, c706 = _comptes()
        journal = Journal.objects.filter(code="OD").first() or Journal.objects.get(code="VTE")
        libelle = (f"{'Produits à recevoir' if ecart > 0 else 'Produits constatés d avance'} {affaire.code} "
                   f"au {jour:%d/%m/%Y} ({calc['pct_avancement']} %)")
        move = AccountMove.objects.create(
            journal=journal, period=period_for_date(jour), date=jour, reference=f"RAV-{affaire.code}"[:120],
            label=libelle[:200], source="M10", source_ref=f"RAV/{affaire.code}"[:60], created_by=user,
        )
        montant = abs(ecart)
        produit = dict(account=c706, analytic_account=affaire.analytic, label=libelle[:200])
        if ecart > 0:
            AccountMoveLine.objects.create(move=move, account=c418, debit=montant, order=0, label=libelle[:200])
            AccountMoveLine.objects.create(move=move, credit=montant, order=1, **produit)
        else:
            AccountMoveLine.objects.create(move=move, debit=montant, order=0, **produit)
            AccountMoveLine.objects.create(move=move, account=c477, credit=montant, order=1, label=libelle[:200])
        move = post_move(move, user=user)
    from .services import parametres_provisoires

    return ReconnaissanceRevenu.objects.create(
        affaire=affaire, date_arrete=jour, methode=calc["methode"], pct_avancement=calc["pct_avancement"],
        ca_reference=calc["ca_reference"], revenu_cumule=calc["revenu_cumule"], facture_cumule=calc["facture_cumule"],
        ecart=ecart, detail=calc["detail"], methode_provisoire=parametres_provisoires(["REVENU_METHODE"]),
        move=move, cree_par=user,
    )
