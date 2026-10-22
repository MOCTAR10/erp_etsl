"""Comptabilisation de la facture fournisseur (CDC M2 §5.10 « facture → écriture fournisseurs, TVA déductible, OD 618 »).

Journal ACH : Dr compte de charge (HT) · Dr TVA déductible · Cr 401 (TTC). Le compte de charge est le 618000 pour un
BC GLOBAL RENTAL (fournisseur 401100), sinon le compte de rattachement de l'article, à défaut 601000. La facture doit
être rapprochée (3-way) ; une fois comptabilisée elle est scellée et le paiement solde le 401.
"""

from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from accounting_kernel.models import AccountMove, AccountMoveLine, Journal
from accounting_kernel.services import period_for_date, post_move
from comptabilite.models import TauxTva
from referentiels.models import Account

from .models import PurchaseInvoice
from config.i18n import tr

CENT = Decimal("0.01")


def _compte(code):
    try:
        return Account.objects.get(code=code)
    except Account.DoesNotExist:
        raise ValidationError(tr("Compte %(code)s absent du plan comptable (seed_referentiels).") % {"code": code})


def taux_defaut():
    return TauxTva.objects.filter(is_active=True).order_by("-is_default", "code").first()


def taux_effectif(ligne):
    """Taux de la ligne, sinon taux actif par défaut (Comptabilité → TVA)."""
    return ligne.taux_tva or taux_defaut()


def _compte_charge(facture, ligne):
    if facture.purchase_order.is_global_rental:
        return _compte("618000")
    article = ligne.purchase_order_line.article
    if article is not None and article.account_id:
        return article.account
    return _compte("601000")


@transaction.atomic
def comptabiliser_facture(facture, user):
    facture = PurchaseInvoice.objects.select_for_update(of=("self",)).select_related("purchase_order", "supplier").get(
        pk=facture.pk
    )
    if facture.status == PurchaseInvoice.Status.COMPTABILISEE:
        raise ValidationError("Facture déjà comptabilisée.")
    if facture.status != PurchaseInvoice.Status.RAPPROCHEE:
        raise ValidationError(
            "Facture non rapprochée (3-way BR / BC / facture) : comptabilisation impossible."
        )
    lignes = list(facture.lines.select_related("purchase_order_line__article", "taux_tva"))
    if not lignes:
        raise ValidationError("Facture sans ligne : rien à comptabiliser.")

    gr = facture.purchase_order.is_global_rental or (facture.supplier is not None and facture.supplier.is_global_rental)
    ht_par_compte = defaultdict(Decimal)
    tva_par_compte = defaultdict(Decimal)
    for ligne in lignes:
        taux = taux_effectif(ligne)
        if taux is None:
            raise ValidationError("Aucun taux de TVA actif : paramétrez-le (Comptabilité → TVA).")
        ht_par_compte[_compte_charge(facture, ligne)] += ligne.price_total
        tva = (ligne.price_total * taux.taux / Decimal("100")).quantize(CENT)
        if tva:
            tva_par_compte[taux.compte_deductible or _compte("445000")] += tva

    try:
        journal = Journal.objects.get(code="ACH")
    except Journal.DoesNotExist:
        raise ValidationError("Journal ACH absent (seed_accounting).")
    analytic = facture.purchase_order.analytic
    move = AccountMove.objects.create(
        journal=journal,
        period=period_for_date(facture.invoice_date),
        date=facture.invoice_date,
        reference=facture.invoice_ref or facture.code,
        label=f"Facture fournisseur {facture.code} — BC {facture.purchase_order.code}",
        source="M2",
        source_ref=facture.code,
        status=AccountMove.Status.DRAFT,
    )
    ordre = 1
    total_ttc = Decimal("0")
    for compte, montant in ht_par_compte.items():
        AccountMoveLine.objects.create(
            move=move, account=compte, partner=facture.supplier, analytic_account=analytic,
            label=f"Achat {facture.code}", debit=montant, credit=0, order=ordre,
        )
        ordre += 1
        total_ttc += montant
    for compte, montant in tva_par_compte.items():
        AccountMoveLine.objects.create(
            move=move, account=compte, partner=facture.supplier,
            label=f"TVA déductible {facture.code}", debit=montant, credit=0, order=ordre,
        )
        ordre += 1
        total_ttc += montant
    AccountMoveLine.objects.create(
        move=move, account=_compte("401100" if gr else "401000"), partner=facture.supplier,
        label=f"Fournisseur {facture.code}", debit=0, credit=total_ttc, order=ordre,
    )
    posted = post_move(move, user=user)
    facture.move = posted
    facture.status = PurchaseInvoice.Status.COMPTABILISEE
    facture.comptabilise_par = user
    facture.comptabilise_le = timezone.now()
    facture.save(update_fields=["move", "status", "comptabilise_par", "comptabilise_le", "updated_at"])
    return facture
