"""Import du grand livre : imputation analytique, fichiers XML, gabarit SAGE transitoire paramétrable (H-04).

Aucun connecteur API : la reprise SAGE se fait par FICHIER d'export (CSV / texte délimité), lu selon un gabarit
`GabaritImport` modifiable par ETSL (séparateur, encodage, format de date, décimale, correspondance des colonnes).
Le gabarit par défaut `SAGE_GL` est PROVISOIRE (export « Écritures comptables » de SAGE 100 supposé) tant qu'ETSL ne
l'a pas confirmé sur un export réel. Les lignes d'une même pièce (journal + date + n° de pièce) forment UNE
écriture équilibrée ; idempotence : empreinte du fichier + clé (journal, date, pièce).
"""

import csv
import io
import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import Decimal, InvalidOperation
from config.i18n import tr

ZERO = Decimal("0")

CHAMPS_SAGE = ("journal", "date", "piece", "compte", "libelle", "debit", "credit", "analytique", "tiers")
CHAMPS_OBLIGATOIRES = ("journal", "date", "piece", "compte", "debit", "credit")

GABARIT_SAGE_DEFAUT = {
    "label": "Export SAGE 100 — écritures comptables (gabarit transitoire)",
    "separateur": ";",
    "encodage": "cp1252",
    "format_date": "%d/%m/%Y",
    "separateur_decimal": ",",
    "colonnes": {
        "journal": "Code journal",
        "date": "Date",
        "piece": "N° pièce",
        "compte": "N° compte général",
        "libelle": "Libellé écriture",
        "debit": "Débit",
        "credit": "Crédit",
        "analytique": "Section analytique",
        "tiers": "N° compte tiers",
    },
}


def gabarit_sage():
    from .models import GabaritImport

    defaults = {k: v for k, v in GABARIT_SAGE_DEFAUT.items()}
    return GabaritImport.objects.get_or_create(code="SAGE_GL", defaults=defaults)[0]


# ------------------------------------------------------------------------------------------- analytique
def resoudre_analytique(code_analytique="", code_affaire=""):
    """Compte analytique d'une ligne : `AXE:CODE` ou `CODE` (unique parmi les valeurs actives), sinon affaire."""
    from referentiels.models import AnalyticAccount

    from .importers import RowError

    code_analytique = (code_analytique or "").strip()
    code_affaire = (code_affaire or "").strip()
    if code_analytique:
        if ":" in code_analytique:
            axe, code = (p.strip() for p in code_analytique.split(":", 1))
            compte = AnalyticAccount.objects.filter(axis__code=axe, code=code, is_active=True).first()
            if compte is None:
                raise RowError(tr("compte analytique inconnu : %(code_analytique)s") % {"code_analytique": code_analytique})
            return compte
        candidats = list(AnalyticAccount.objects.filter(code=code_analytique, is_active=True)[:2])
        if not candidats:
            raise RowError(tr("compte analytique inconnu : %(code_analytique)s") % {"code_analytique": code_analytique})
        if len(candidats) > 1:
            raise RowError(tr("compte analytique ambigu : %(code_analytique)s (préciser AXE:CODE)") % {"code_analytique": code_analytique})
        return candidats[0]
    if code_affaire:
        from commercial.models import Affaire

        affaire = Affaire.objects.filter(code=code_affaire).first()
        if affaire is None:
            raise RowError(tr("affaire inconnue : %(code_affaire)s") % {"code_affaire": code_affaire})
        return affaire.analytic or affaire.assurer_compte_analytique()
    return None


def cible_analytique(comptes):
    """Index de la ligne qui porte l'analytique : la première en classe 6 ou 7, sinon la première ligne."""
    for i, compte in enumerate(comptes):
        if str(compte.code)[:1] in ("6", "7"):
            return i
    return 0


# ------------------------------------------------------------------------------------------- XML
def parse_xml(content):
    """XML « une écriture par élément » : attributs ou sous-éléments = colonnes. DTD / entités refusées."""
    texte = content.decode("utf-8-sig")
    if "<!DOCTYPE" in texte.upper() or "<!ENTITY" in texte.upper():
        raise ValueError("XML avec DTD ou entités refusé (sécurité).")
    racine = ET.fromstring(texte)
    rows = []
    for el in racine:
        row = dict(el.attrib)
        for enfant in el:
            row[enfant.tag] = (enfant.text or "").strip()
        rows.append(row)
    fieldnames = sorted({k for r in rows for k in r})
    return rows, fieldnames


def est_xml(filename, content):
    return (filename or "").lower().endswith(".xml") or content.lstrip()[:1] == b"<"


# ------------------------------------------------------------------------------------------- SAGE
class SageConnector:
    """Écritures SAGE (fichier d'export) lues selon le gabarit ; une écriture par pièce."""

    def __init__(self, gabarit):
        self.gabarit = gabarit
        self.colonnes = {**GABARIT_SAGE_DEFAUT["colonnes"], **(gabarit.colonnes or {})}

    def parse(self, content, filename=""):
        texte = content.decode(self.gabarit.encodage or "utf-8", errors="strict").lstrip("﻿")
        reader = csv.DictReader(io.StringIO(texte), delimiter=self.gabarit.separateur or ";")
        rows = list(reader)
        return rows, reader.fieldnames

    def validate_headers(self, fieldnames):
        from .importers import ImportError

        manquantes = [self.colonnes[c] for c in CHAMPS_OBLIGATOIRES if self.colonnes.get(c) not in (fieldnames or ())]
        if manquantes:
            raise ImportError(tr("Colonnes du gabarit absentes du fichier : %(liste)s.") % {"liste": ", ".join(manquantes)})

    def _v(self, row, champ):
        col = self.colonnes.get(champ)
        return (row.get(col) or "").strip() if col else ""

    def _montant(self, brut):
        from .importers import RowError

        brut = (brut or "").replace("\xa0", "").replace(" ", "")
        if not brut:
            return ZERO
        if self.gabarit.separateur_decimal == ",":
            brut = brut.replace(".", "").replace(",", ".")
        try:
            return Decimal(brut)
        except InvalidOperation:
            raise RowError(tr("montant invalide : %(brut)s") % {"brut": brut})

    def prepare(self, rows):
        """Regroupe les lignes par pièce (journal, date, n° de pièce), dans l'ordre du fichier."""
        groupes = {}
        for row in rows:
            cle = (self._v(row, "journal").upper(), self._v(row, "date"), self._v(row, "piece"))
            groupes.setdefault(cle, []).append(row)
        return [{"journal": j, "date": d, "piece": p, "lignes": lignes} for (j, d, p), lignes in groupes.items()]

    def handle_row(self, groupe):
        from accounting_kernel.models import AccountMove, AccountMoveLine, Journal
        from accounting_kernel.services import period_for_date, post_move
        from referentiels.models import Account, Partner

        from .importers import RowError

        journal = Journal.objects.filter(code=groupe["journal"]).first()
        if journal is None:
            raise RowError(tr("journal inconnu : %(journal)s") % {"journal": groupe['journal']})
        try:
            jour = datetime.strptime(groupe["date"], self.gabarit.format_date or "%d/%m/%Y").date()
        except ValueError:
            raise RowError(tr("date invalide (format du gabarit %(gabarit_format_date)s) : %(date)s") % {"gabarit_format_date": self.gabarit.format_date, "date": groupe['date']})
        reference = groupe["piece"] or f"sage-{jour.isoformat()}"
        if AccountMove.objects.filter(journal=journal, date=jour, reference=reference).exists():
            return ("duplicate", reference)
        lignes, comptes = [], []
        for row in groupe["lignes"]:
            code = self._v(row, "compte")
            compte = Account.objects.filter(code=code).first()
            if compte is None:
                raise RowError(tr("compte inconnu : %(code)s (pièce %(reference)s)") % {"code": code, "reference": reference})
            debit, credit = self._montant(self._v(row, "debit")), self._montant(self._v(row, "credit"))
            if debit < 0 or credit < 0 or (debit and credit) or not (debit or credit):
                raise RowError(tr("ligne invalide (débit OU crédit positif attendu) : pièce %(reference)s, compte %(code)s") % {"reference": reference, "code": code})
            analytic = resoudre_analytique(self._v(row, "analytique"))
            tiers = self._v(row, "tiers")
            partner = Partner.objects.filter(code=tiers).first() if tiers else None
            lignes.append((compte, debit, credit, analytic, partner, self._v(row, "libelle")))
            comptes.append(compte)
        if sum(l[1] for l in lignes) != sum(l[2] for l in lignes):
            raise RowError(tr("pièce %(reference)s déséquilibrée (débit ≠ crédit)") % {"reference": reference})
        move = AccountMove.objects.create(
            journal=journal, period=period_for_date(jour), date=jour, reference=reference[:120],
            label=(lignes[0][5] or f"Reprise SAGE {reference}")[:200], source="integrations",
            source_ref=f"sage/{reference}"[:60],
        )
        for i, (compte, debit, credit, analytic, partner, libelle) in enumerate(lignes):
            AccountMoveLine.objects.create(
                move=move, account=compte, debit=debit, credit=credit, analytic_account=analytic, partner=partner,
                label=libelle[:200], order=i,
            )
        post_move(move)
        return ("created", reference)
