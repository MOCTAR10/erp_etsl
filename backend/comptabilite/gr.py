"""Écriture 618 des prestations GLOBAL RENTAL émises par M4 (fil rouge 618).

À la clôture (retour) d'une location GR, le coût de la prestation (tarif × durée ou compteurs, + pénalités de
retard) est comptabilisé au journal des achats : Dr 618000 (analytique de l'affaire) / Cr 401100 (fournisseur
intra-groupe GLOBAL RENTAL). Une seule écriture par location (source « M4 », réf. = code de la location).

Pas de double charge : une location rattachée à un bon de commande GLOBAL RENTAL (M2, `PurchaseOrder.location_gr`)
est facturée et comptabilisée au 618 par le circuit achats (facture fournisseur) ; elle est exclue d'ici.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from accounting_kernel.models import AccountMove, AccountMoveLine, Journal
from accounting_kernel.services import period_for_date, post_move
from referentiels.models import Account

CENT = Decimal("0.01")
SOURCE_GR = "M4"


def ecriture_location(location):
    return (
        AccountMove.objects.filter(source=SOURCE_GR, source_ref=location.code)
        .exclude(status=AccountMove.Status.DRAFT).order_by("created_at").first()
    )


def montant_location(location):
    from logistique.services import _cout_location, get_param_logistique

    fin = location.date_retour or location.date_fin
    cout = Decimal("0")
    if location.date_debut and fin:
        calc = _cout_location(location, location.date_debut, fin, get_param_logistique("JOURS_PAR_MOIS"))
        cout = calc[1] if calc else Decimal("0")
    return (cout + (location.penalite or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def _compte(code):
    try:
        return Account.objects.get(code=code)
    except Account.DoesNotExist:
        raise ValidationError(f"Compte {code} absent du plan comptable (seed_referentiels).")


@transaction.atomic
def comptabiliser_location_gr(location, user=None):
    from logistique.models import LocationGR

    location = LocationGR.objects.select_for_update(of=("self",)).select_related("partenaire", "affaire", "equipement").get(pk=location.pk)
    if location.statut != LocationGR.Statut.TERMINEE:
        raise ValidationError("Seule une location GR terminée (retour enregistré) est comptabilisée.")
    if not location.partenaire.is_global_rental:
        raise ValidationError("Le partenaire n'est pas GLOBAL RENTAL : pas d'imputation au compte 618.")
    if not location.imputation_618:
        raise ValidationError("La prestation n'est pas imputée au compte 618.")
    if ecriture_location(location):
        raise ValidationError("Location GR déjà comptabilisée.")
    if bc_lie(location):
        raise ValidationError(
            "Location rattachée à un bon de commande GLOBAL RENTAL : la charge 618 passe par sa facture d'achat (M2)."
        )
    montant = montant_location(location)
    if montant <= 0:
        raise ValidationError("Montant de la prestation nul : rien à comptabiliser (tarif ou compteurs manquants).")
    try:
        journal = Journal.objects.get(code="ACH")
    except Journal.DoesNotExist:
        raise ValidationError("Journal des achats ACH absent (seed_accounting).")
    jour = location.date_retour or location.date_fin
    analytic = location.affaire.assurer_compte_analytique() if location.affaire_id else None
    move = AccountMove.objects.create(
        journal=journal, period=period_for_date(jour), date=jour, reference=location.reference_bc or location.code,
        label=f"Location GR {location.code} — {location.equipement.label}"[:200], source=SOURCE_GR,
        source_ref=location.code, created_by=user,
    )
    AccountMoveLine.objects.create(
        move=move, account=_compte("618000"), partner=location.partenaire, analytic_account=analytic,
        label=f"Prestation GR {location.code}", debit=montant, order=0,
    )
    AccountMoveLine.objects.create(
        move=move, account=_compte("401100"), partner=location.partenaire,
        label=f"GLOBAL RENTAL {location.code}", credit=montant, order=1,
    )
    return post_move(move, user=user)


def comptabiliser_location_gr_auto(location, user=None):
    """Appel non bloquant depuis M4 : si la comptabilisation est impossible (période, montant…), la location
    reste dans la liste « à comptabiliser » de M10."""
    try:
        with transaction.atomic():
            return comptabiliser_location_gr(location, user)
    except ValidationError:
        return None


def locations_a_comptabiliser():
    from logistique.models import LocationGR

    faites = set(
        AccountMove.objects.filter(source=SOURCE_GR).exclude(status=AccountMove.Status.DRAFT).values_list("source_ref", flat=True)
    )
    qs = LocationGR.objects.filter(
        statut=LocationGR.Statut.TERMINEE, partenaire__is_global_rental=True, imputation_618=True,
    ).select_related("partenaire", "equipement", "affaire").prefetch_related("lectures")
    return [loc for loc in qs if loc.code not in faites and not bc_lie(loc)]


def bc_lie(location):
    """BC achats GLOBAL RENTAL (non annulé) rattaché à la location : la charge 618 passe par sa facture (M2)."""
    from achats.models import PurchaseOrder

    return PurchaseOrder.objects.filter(location_gr=location).exclude(status=PurchaseOrder.Status.ANNULEE).exists()
