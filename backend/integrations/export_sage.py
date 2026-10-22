"""Interface transitoire M10 → SAGE (double tenue) : export des écritures comptabilisées au format d'import SAGE.

Symétrique de la reprise `SAGE_GL` (`gabarits.SageConnector`) : une ligne de fichier par ligne d'écriture, colonnes
journal / date / n° de pièce / compte général / libellé / débit / crédit / section analytique / compte tiers. Le
format (séparateur, encodage, format de date, décimale, intitulés de colonnes) est le gabarit `SAGE_EXPORT`, donnée
ETSL modifiable à l'écran et PROVISOIRE tant qu'ETSL n'a pas validé le fichier sur son SAGE 100 (H-04 : fichier,
jamais d'API). Les écritures déjà exportées sont exclues par défaut (pas de double import côté SAGE).
"""

import csv
import hashlib
import io
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from .gabarits import CHAMPS_SAGE, GABARIT_SAGE_DEFAUT

GABARIT_EXPORT_DEFAUT = {
    **GABARIT_SAGE_DEFAUT,
    "label": "Export des écritures vers SAGE 100 — double tenue (gabarit transitoire)",
}


def gabarit_export_sage():
    from .models import GabaritImport

    defaults = {k: v for k, v in GABARIT_EXPORT_DEFAUT.items()}
    return GabaritImport.objects.get_or_create(code="SAGE_EXPORT", defaults=defaults)[0]


def _montant(valeur, sep):
    return "" if not valeur else f"{Decimal(valeur):.2f}".replace(".", sep)


def deja_exportees():
    from .models import ExportEcritures

    ids = set()
    for liste in ExportEcritures.objects.values_list("moves", flat=True):
        ids.update(liste or [])
    return ids


def lignes_a_exporter(date_from, date_to, journal="", seulement_nouvelles=True):
    from accounting_kernel.models import AccountMove, AccountMoveLine

    if date_from > date_to:
        raise ValidationError({"date_to": "La date de fin précède la date de début."})
    moves = AccountMove.objects.filter(
        date__gte=date_from, date__lte=date_to, status__in=(AccountMove.Status.POSTED, AccountMove.Status.REVERSED)
    )
    if journal:
        moves = moves.filter(journal__code=journal.upper())
    ids = [str(i) for i in moves.values_list("id", flat=True)]
    if seulement_nouvelles:
        exclues = deja_exportees()
        ids = [i for i in ids if i not in exclues]
    lignes = (
        AccountMoveLine.objects.filter(move_id__in=ids)
        .select_related("move__journal", "account", "partner", "analytic_account__axis")
        .order_by("move__date", "move__journal__code", "move__number", "order")
    )
    return ids, list(lignes)


def produire(lignes, gabarit):
    colonnes = {**GABARIT_SAGE_DEFAUT["colonnes"], **(gabarit.colonnes or {})}
    sep_dec = gabarit.separateur_decimal or ","
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=gabarit.separateur or ";", lineterminator="\r\n")
    writer.writerow([colonnes[c] for c in CHAMPS_SAGE])
    for ligne in lignes:
        move = ligne.move
        analytique = ""
        if ligne.analytic_account_id:
            analytique = f"{ligne.analytic_account.axis.code}:{ligne.analytic_account.code}"
        valeurs = {
            "journal": move.journal.code,
            "date": move.date.strftime(gabarit.format_date or "%d/%m/%Y"),
            "piece": move.number or "",
            "compte": ligne.account.code,
            "libelle": (ligne.label or move.label or "")[:69],
            "debit": _montant(ligne.debit, sep_dec),
            "credit": _montant(ligne.credit, sep_dec),
            "analytique": analytique,
            "tiers": ligne.partner.code if ligne.partner_id else "",
        }
        writer.writerow([valeurs[c] for c in CHAMPS_SAGE])
    return buf.getvalue().encode(gabarit.encodage or "cp1252", errors="replace")


@transaction.atomic
def exporter(date_from, date_to, user, journal="", seulement_nouvelles=True):
    from .models import ExportEcritures

    gabarit = gabarit_export_sage()
    ids, lignes = lignes_a_exporter(date_from, date_to, journal, seulement_nouvelles)
    if not lignes:
        raise ValidationError("Aucune écriture comptabilisée à exporter sur la période (ou toutes déjà exportées).")
    contenu = produire(lignes, gabarit)
    nom = f"export_sage_{date_from:%Y%m%d}_{date_to:%Y%m%d}{('_' + journal.upper()) if journal else ''}.csv"
    return ExportEcritures.objects.create(
        date_from=date_from, date_to=date_to, journal=(journal or "").upper(), seulement_nouvelles=seulement_nouvelles,
        nb_ecritures=len(ids), nb_lignes=len(lignes),
        total_debit=sum((l.debit for l in lignes), Decimal("0")), total_credit=sum((l.credit for l in lignes), Decimal("0")),
        moves=ids, contenu=contenu, nom_fichier=nom, sha256=hashlib.sha256(contenu).hexdigest(),
        gabarit_code=gabarit.code, gabarit_provisoire=gabarit.statut_valeur != gabarit.StatutValeur.CONFIRME,
        cree_par=user,
    )
