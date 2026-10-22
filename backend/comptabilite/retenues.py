"""Retenue de garantie (M1 → M10) : écriture à l'émission de la facture, report sur la facture, libération.

Le taux vient du contrat actif de l'affaire (calcul M1 : `commercial.ecarts_m1.taux_retenue`, taux du contrat ou
paramètre `RETENUE_GARANTIE_PCT` pour un marché de travaux). À l'émission d'une facture :
    Dr 411000 (TTC − retenue) · Dr 411700 « Clients — retenues de garantie » (retenue) · Cr 706 · Cr 443.
Un avoir reprend la retenue au prorata de la facture d'origine. À l'échéance de garantie (fin du contrat + délai
`GARANTIE_DUREE_MOIS` de M1), la libération passe Dr 411000 / Cr 411700 (journal OD). Paramètres provisoires
`RETENUE_GARANTIE_ACTIVE` (1 = retenue appliquée) et `RETENUE_GARANTIE_COMPTE` (411700).
"""

from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

ZERO = Decimal("0")
CENT = Decimal("0.01")


def _param(code):
    from .services import get_param

    return get_param(code)


def actif():
    return _param("RETENUE_GARANTIE_ACTIVE") >= 1


def compte_retenue():
    """Compte 4117 (SYSCOHADA « Clients, retenues de garantie ») : créé à la volée sous le compte client s'il manque."""
    from referentiels.models import Account

    code = str(int(_param("RETENUE_GARANTIE_COMPTE")))
    compte = Account.objects.filter(code=code).first()
    if compte is None:
        parent = Account.objects.filter(code="411000").first()
        compte = Account.objects.create(
            code=code, label="Clients — retenues de garantie", account_class=4,
            account_type=Account.AccountType.ASSET, parent=parent, reconcile=True,
        )
    return compte


def contrat_affaire(affaire_id):
    from commercial.models import Contract

    if not affaire_id:
        return None
    qs = Contract.objects.filter(affaire_id=affaire_id)
    return qs.filter(status=Contract.Status.ACTIF).order_by("-created_at").first() or qs.exclude(
        status=Contract.Status.BROUILLON).order_by("-created_at").first()


def taux_facture(facture):
    """Taux de retenue applicable à la facture (0 si inactif, sans contrat ou contrat sans retenue)."""
    if not actif() or not facture.affaire_id:
        return ZERO
    contrat = contrat_affaire(facture.affaire_id)
    if contrat is None:
        return ZERO
    from commercial.ecarts_m1 import taux_retenue

    return Decimal(taux_retenue(contrat) or 0)


def calculer(facture):
    """(taux, montant) de la retenue : sur le HT pour une facture, au prorata de l'origine pour un avoir."""
    if facture.nature == facture.Nature.AVOIR:
        origine = facture.facture_origine
        if origine is None or not origine.montant_retenue or not origine.montant_ht:
            return ZERO, ZERO
        montant = (origine.montant_retenue * facture.montant_ht / origine.montant_ht).quantize(CENT, ROUND_HALF_UP)
        return origine.taux_retenue, min(montant, origine.montant_retenue)
    taux = taux_facture(facture)
    if taux <= 0:
        return ZERO, ZERO
    return taux, (facture.montant_ht * taux / Decimal("100")).quantize(CENT, ROUND_HALF_UP)


def date_liberation(affaire_id):
    from commercial.ecarts_m1 import ajouter_mois, get_param

    contrat = contrat_affaire(affaire_id)
    if contrat is None:
        return None
    fin = contrat.end_date or (ajouter_mois(contrat.start_date, contrat.months) if contrat.months and contrat.start_date else None)
    return ajouter_mois(fin, int(get_param("GARANTIE_DUREE_MOIS"))) if fin else None


def situation_affaires():
    """Par affaire : retenue cumulée (factures − avoirs émis), libérée, solde, date de libération."""
    from commercial.models import Affaire

    from .models import FactureClient, LiberationRetenue

    lignes = {}
    for f in FactureClient.objects.filter(statut=FactureClient.Statut.EMISE, montant_retenue__gt=0).exclude(affaire=None):
        signe = -1 if f.nature == FactureClient.Nature.AVOIR else 1
        row = lignes.setdefault(f.affaire_id, {"retenue": ZERO, "factures": 0})
        row["retenue"] += signe * f.montant_retenue
        row["factures"] += 1
    liberes = dict(
        LiberationRetenue.objects.values("affaire_id").annotate(t=Sum("montant")).values_list("affaire_id", "t")
    )
    affaires = Affaire.objects.in_bulk(list(lignes))
    today = timezone.localdate()
    sortie = []
    for aff_id, row in lignes.items():
        libere = liberes.get(aff_id) or ZERO
        solde = row["retenue"] - libere
        liberation = date_liberation(aff_id)
        sortie.append({
            "affaire": str(aff_id), "affaire_code": affaires[aff_id].code, "affaire_label": affaires[aff_id].title,
            "factures": row["factures"], "retenue": row["retenue"], "liberee": libere, "solde": solde,
            "date_liberation": liberation, "echue": bool(liberation and liberation <= today),
        })
    sortie.sort(key=lambda r: r["affaire_code"])
    return sortie


@transaction.atomic
def liberer(affaire, user, motif=""):
    """Libère le solde de retenue de l'affaire : Dr 411000 / Cr 411700 (journal OD). Avant l'échéance de garantie,
    un motif (ex. caution bancaire de substitution) est obligatoire."""
    from accounting_kernel.models import AccountMove, AccountMoveLine, Journal
    from accounting_kernel.services import period_for_date, post_move
    from commercial.models import Affaire

    from .facturation import _client_de_affaire, _compte
    from .models import LiberationRetenue

    affaire = Affaire.objects.select_for_update(of=("self",)).get(pk=affaire.pk)
    row = next((r for r in situation_affaires() if r["affaire"] == str(affaire.pk)), None)
    if row is None or row["solde"] <= 0:
        raise ValidationError("Aucune retenue de garantie à libérer sur cette affaire.")
    motif = (motif or "").strip()
    if not row["echue"] and not motif:
        raise ValidationError(
            "Garantie non échue (libération prévue le "
            f"{row['date_liberation']:%d/%m/%Y}) : motif obligatoire pour une libération anticipée."
            if row["date_liberation"] else "Date de libération inconnue (contrat sans fin) : motif obligatoire."
        )
    client = _client_de_affaire(affaire)
    jour = timezone.localdate()
    journal = Journal.objects.filter(code="OD").first() or Journal.objects.get(code="VTE")
    move = AccountMove.objects.create(
        journal=journal, period=period_for_date(jour), date=jour, reference=f"RG-{affaire.code}"[:40],
        label=f"Libération retenue de garantie {affaire.code}"[:200], source="M10", source_ref=f"RG/{affaire.code}",
        created_by=user,
    )
    AccountMoveLine.objects.create(move=move, account=_compte("411000"), partner=client, debit=row["solde"], order=0,
                                   label=f"Libération RG {affaire.code}")
    AccountMoveLine.objects.create(move=move, account=compte_retenue(), partner=client, credit=row["solde"], order=1,
                                   label=f"Libération RG {affaire.code}")
    post_move(move, user=user)
    return LiberationRetenue.objects.create(affaire=affaire, montant=row["solde"], move=move, motif=motif[:250],
                                            libere_par=user)
