"""Fiscalité M10 : TVA sur écritures 443 / 445, autofacturation (TVA autoliquidée), retenue à la source, liasse
fiscale et état 2460 (gabarits provisoires), conservation 10 ans des pièces fiscales en GED.

Les gabarits (`GabaritEtat`) sont des DONNÉES ETSL modifiables à l'écran, provisoires jusqu'à confirmation :
modèles officiels de la DGI (liasse, état 2460) restent à fournir par ETSL.
"""

import hashlib
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from accounting_kernel.models import AccountMove, AccountMoveLine, Journal
from accounting_kernel.services import period_for_date, post_move
from referentiels.models import Account

from .models import AutoFacture, DeclarationTva, GabaritEtat, Paiement
from config.i18n import en_francais, tr

ZERO = Decimal("0")
CENT = Decimal("0.01")
COMPTABILISEES = (AccountMove.Status.POSTED, AccountMove.Status.REVERSED)

TYPE_GED_DECLARATIONS = "declarations_fiscales"
TYPE_GED_JOURNAUX = "journaux_comptables"
TYPES_FISCAUX = (TYPE_GED_DECLARATIONS, TYPE_GED_JOURNAUX, "factures_clients")

GABARITS_DEFAUT = {
    "BILAN": ("Modèle de bilan (rubriques SYSCOHADA)", {
        "note": "Rubriques par comptes principaux (2 chiffres) ; à remplacer par le modèle officiel ETSL / DGI.",
    }),
    "RESULTAT": ("Modèle de compte de résultat", {
        "note": "Produits classes 7 et 8 (produits), charges classes 6 et 8 ; détail par compte principal.",
    }),
    "LIASSE": ("Liasse fiscale (système normal SYSCOHADA)", {
        "etats": ["bilan", "compte_resultat", "balance"],
        "note": "Gabarit provisoire : bilan + compte de résultat + balance ; formulaire officiel DGI à fournir.",
    }),
    "ETAT_2460": ("État 2460 — honoraires, commissions et rémunérations versés à des tiers", {
        "comptes": ["632", "622"],
        "seuil": "0",
        "note": "Comptes (préfixes) et seuil de déclaration provisoires ; modèle officiel DGI à fournir.",
    }),
}


def get_gabarit(code):
    label, parametres = GABARITS_DEFAUT[code]
    return GabaritEtat.objects.get_or_create(code=code, defaults={"label": label, "parametres": parametres})[0]


def tous_gabarits():
    for code in GABARITS_DEFAUT:
        get_gabarit(code)
    return GabaritEtat.objects.all()


def _compte(code):
    try:
        return Account.objects.get(code=code)
    except Account.DoesNotExist:
        raise ValidationError(tr("Compte %(code)s absent du plan comptable (seed_referentiels).") % {"code": code})


def _bornes_mois(mois):
    debut = mois.replace(day=1)
    fin = date(debut.year + 1, 1, 1) if debut.month == 12 else date(debut.year, debut.month + 1, 1)
    return debut, fin


# --------------------------------------------------------------------------------------------------
# TVA sur écritures 443 / 445
# --------------------------------------------------------------------------------------------------
def compute_declaration_tva(declaration):
    """TVA du mois depuis les écritures comptabilisées : collectée = solde créditeur 443, déductible = solde
    débiteur 445 (dont TVA autoliquidée des autofactures). À défaut d'écriture 443 / 445 dans le mois, repli sur
    les paiements validés (régime des encaissements, approche historique) — `source_calcul` le dit."""
    debut, fin = _bornes_mois(declaration.mois)
    taux = Decimal(declaration.taux_tva.taux) / 100
    lignes = AccountMoveLine.objects.filter(move__status__in=COMPTABILISEES, move__date__gte=debut, move__date__lt=fin)

    def solde(prefixe, sens):
        agg = lignes.filter(account__code__startswith=prefixe).aggregate(d=Sum("debit"), c=Sum("credit"))
        d, c = agg["d"] or ZERO, agg["c"] or ZERO
        return (c - d) if sens == "credit" else (d - c)

    retenues = lignes.filter(account__code__startswith="447", move__paiements_m10__isnull=False).aggregate(c=Sum("credit"))["c"] or ZERO
    autoliq = lignes.filter(account__code__startswith="443", move__autofactures__isnull=False).aggregate(c=Sum("credit"))["c"] or ZERO
    if lignes.filter(account__code__startswith="443").exists() or lignes.filter(account__code__startswith="445").exists():
        collectee, deductible = solde("443", "credit"), solde("445", "debit")
        base = (collectee / taux).quantize(CENT) if taux else ZERO
        source = DeclarationTva.SourceCalcul.ECRITURES
    else:
        paiements = Paiement.objects.filter(statut=Paiement.Statut.VALIDE, date__gte=debut, date__lt=fin)
        base = sum((p.montant for p in paiements.filter(sens=Paiement.Sens.ENTREE)), ZERO)
        collectee = base * taux
        deductible = sum(
            (p.montant for p in paiements.filter(sens=Paiement.Sens.SORTIE).exclude(imputation_618=True)), ZERO
        ) * taux
        source = DeclarationTva.SourceCalcul.PAIEMENTS
    declaration.base_imposable = base
    declaration.tva_collectee = collectee.quantize(CENT)
    declaration.tva_deductible = deductible.quantize(CENT)
    declaration.net_a_payer = (collectee - deductible).quantize(CENT)
    declaration.tva_autoliquidee = autoliq.quantize(CENT)
    declaration.retenues_source = retenues.quantize(CENT)
    declaration.source_calcul = source
    declaration.save(update_fields=[
        "base_imposable", "tva_collectee", "tva_deductible", "net_a_payer", "tva_autoliquidee", "retenues_source",
        "source_calcul",
    ])
    return declaration


# --------------------------------------------------------------------------------------------------
# Autofacturation (TVA autoliquidée)
# --------------------------------------------------------------------------------------------------
@transaction.atomic
def emettre_autofacture(af, user):
    """Comptabilise l'autofacture (journal ACH) : Dr charge HT · Dr 445 TVA / Cr 401 HT · Cr 443 TVA autoliquidée."""
    af = AutoFacture.objects.select_for_update(of=("self",)).select_related("fournisseur", "taux_tva", "compte_charge").get(pk=af.pk)
    if af.statut != AutoFacture.Statut.BROUILLON:
        raise ValidationError("Autofacture déjà émise.")
    if af.montant_ht is None or af.montant_ht <= 0:
        raise ValidationError("Le montant HT doit être strictement positif.")
    if af.compte_charge.account_class not in (2, 6):
        raise ValidationError("Le compte d'imputation doit être un compte de charge (6) ou d'immobilisation (2).")
    taux = af.taux_tva
    if not (taux.compte_collecte_id and taux.compte_deductible_id):
        raise ValidationError("Le taux de TVA doit porter ses comptes collectée (443) et déductible (445).")
    tva = (af.montant_ht * taux.taux / Decimal("100")).quantize(CENT)
    try:
        journal = Journal.objects.get(code="ACH")
    except Journal.DoesNotExist:
        raise ValidationError("Journal des achats ACH absent (seed_accounting).")
    fournisseur = _compte("401100" if af.fournisseur.is_global_rental else "401000")
    move = AccountMove.objects.create(
        journal=journal, period=period_for_date(af.date), date=af.date, reference=af.code,
        label=f"Autofacture {af.code} — {af.fournisseur.name}"[:200], source="M10", source_ref=af.code, created_by=user,
    )
    lignes = [
        (af.compte_charge, af.montant_ht, ZERO, af.analytic, af.fournisseur),
        (fournisseur, ZERO, af.montant_ht, None, af.fournisseur),
    ]
    if tva > 0:
        lignes += [
            (taux.compte_deductible, tva, ZERO, None, af.fournisseur),
            (taux.compte_collecte, ZERO, tva, None, af.fournisseur),
        ]
    for i, (compte, d, c, analytic, partner) in enumerate(lignes):
        AccountMoveLine.objects.create(
            move=move, account=compte, debit=d, credit=c, analytic_account=analytic, partner=partner, order=i,
            label=af.objet[:200] if af.objet else af.code,
        )
    af.move = post_move(move, user=user)
    af.montant_tva = tva
    af.statut = AutoFacture.Statut.EMISE
    af.emise_par, af.emise_le = user, timezone.now()
    af.save(update_fields=["move", "montant_tva", "statut", "emise_par", "emise_le"])
    return af


# --------------------------------------------------------------------------------------------------
# Liasse fiscale et état 2460
# --------------------------------------------------------------------------------------------------
def _bornes_exercice(exercice):
    from accounting_kernel.models import FiscalYear

    fy = FiscalYear.objects.filter(year=exercice).first()
    if fy:
        return fy.start_date, fy.end_date
    return date(exercice, 1, 1), date(exercice, 12, 31)


def liasse(exercice):
    from . import etats

    debut, fin = _bornes_exercice(exercice)
    gab = get_gabarit("LIASSE")
    morceaux = {
        "bilan": lambda: etats.bilan(fin),
        "compte_resultat": lambda: etats.compte_resultat(debut, fin),
        "balance": lambda: etats.balance(debut, fin),
    }
    tableaux = []
    for code in gab.parametres.get("etats") or list(morceaux):
        if code in morceaux:
            e = morceaux[code]()
            for tab in e["tableaux"]:
                tableaux.append({**tab, "titre": f"{e['titre']} — {tab['titre']}" if tab["titre"] != e["titre"] else tab["titre"]})
    return {
        "code": "liasse", "titre": f"Liasse fiscale {exercice}",
        "sous_titre": f"Exercice du {debut:%d/%m/%Y} au {fin:%d/%m/%Y} — système normal SYSCOHADA",
        "provisoire": gab.est_provisoire,
        "avertissement": "Gabarit de liasse provisoire — modèle officiel DGI à fournir et à confirmer par ETSL.",
        "tableaux": tableaux,
    }


def etat_2460(exercice):
    """Sommes versées à chaque tiers sur les comptes d'honoraires / commissions du gabarit, au-delà du seuil."""
    from .etats import _col

    debut, fin = _bornes_exercice(exercice)
    gab = get_gabarit("ETAT_2460")
    prefixes = [str(p).strip() for p in gab.parametres.get("comptes") or [] if str(p).strip()]
    try:
        seuil = Decimal(str(gab.parametres.get("seuil") or "0"))
    except Exception:
        seuil = ZERO
    par_tiers = {}
    if prefixes:
        from django.db.models import Q

        filtre = Q()
        for p in prefixes:
            filtre |= Q(account__code__startswith=p)
        lignes = (
            AccountMoveLine.objects.filter(filtre, move__status__in=COMPTABILISEES, move__date__gte=debut, move__date__lte=fin)
            .select_related("partner", "account", "move")
        )
        for l in lignes:
            partner = l.partner
            if partner is None:  # tiers porté par une autre ligne de la pièce (401 / 411)
                autre = l.move.lines.filter(partner__isnull=False).select_related("partner").first()
                partner = autre.partner if autre else None
            cle = partner.pk if partner else None
            row = par_tiers.setdefault(cle, {
                "code": partner.code if partner else "", "tiers": partner.name if partner else "(tiers non identifié)",
                "nif": partner.tax_id if partner else "", "adresse": (partner.address or "")[:120] if partner else "",
                "comptes": set(), "montant": ZERO,
            })
            row["comptes"].add(l.account.code)
            row["montant"] += l.debit - l.credit
    lignes_out = [
        {**r, "comptes": ", ".join(sorted(r["comptes"])), "montant": r["montant"].quantize(CENT)}
        for r in sorted(par_tiers.values(), key=lambda r: r["tiers"]) if r["montant"] > 0 and r["montant"] >= seuil
    ]
    total = sum((r["montant"] for r in lignes_out), ZERO)
    lignes_out.append({"code": "", "tiers": "TOTAL", "nif": "", "adresse": "", "comptes": "", "montant": total, "total": True})
    return {
        "code": "etat_2460", "titre": f"État 2460 — exercice {exercice}",
        "sous_titre": f"Honoraires, commissions et rémunérations versés à des tiers (comptes {', '.join(prefixes) or '—'} ; seuil {seuil:,.0f} F)".replace(",", " "),
        "provisoire": gab.est_provisoire,
        "avertissement": "Gabarit d'état 2460 provisoire — comptes, seuil et modèle officiel DGI à confirmer par ETSL.",
        "tableaux": [{
            "titre": "Bénéficiaires",
            "colonnes": [
                _col("code", "Code"), _col("tiers", "Bénéficiaire"), _col("nif", "NIF"), _col("adresse", "Adresse"),
                _col("comptes", "Comptes"), _col("montant", "Montant versé", True),
            ],
            "lignes": lignes_out,
        }],
    }


# --------------------------------------------------------------------------------------------------
# Conservation 10 ans des pièces fiscales en GED
# --------------------------------------------------------------------------------------------------
def archiver_piece(contenu, nom, titre, type_code, type_label, reference, jour, user=None, mots=()):
    """Scelle une pièce fiscale (PDF) en GED, type à conservation ≥ N ans (paramètre CONSERVATION_ANS)."""
    from django.core.files.base import ContentFile

    from documents.models import Document, DocumentType, Version

    from .services import get_param

    ans = int(get_param("CONSERVATION_ANS"))
    type_doc, _ = DocumentType.objects.get_or_create(code=type_code, defaults={"label": type_label, "retention_years": ans})
    if (type_doc.retention_years or 0) < ans:
        type_doc.retention_years = ans
        type_doc.save(update_fields=["retention_years"])
    sha = hashlib.sha256(contenu).hexdigest()
    document = Document.objects.create(
        title=titre[:200], status=Document.Status.ARCHIVED, archived_at=timezone.now(), type=type_doc,
        document_date=jour, reference=reference[:120], keywords=["fiscal", *mots], sha256=sha, created_by=user,
    )
    version = Version.objects.create(
        document=document, number=1, file=ContentFile(contenu, name=nom), sha256=sha, size=len(contenu),
        original_filename=nom, created_by=user,
    )
    document.current_version = version
    document.save(update_fields=["current_version"])
    return document


def declaration_pdf(declaration):
    from .etats import _col, to_pdf

    lignes = [
        {"rubrique": "Base imposable (HT)", "montant": declaration.base_imposable},
        {"rubrique": "TVA collectée (443)", "montant": declaration.tva_collectee},
        {"rubrique": "dont TVA autoliquidée (autofacturation)", "montant": declaration.tva_autoliquidee},
        {"rubrique": "TVA déductible (445)", "montant": declaration.tva_deductible},
        {"rubrique": "TVA nette à payer", "montant": declaration.net_a_payer, "total": True},
        {"rubrique": "Retenues à la source à reverser (447)", "montant": declaration.retenues_source},
    ]
    return to_pdf({
        "titre": f"Déclaration de TVA {declaration.code} — {declaration.mois:%m/%Y}",
        "sous_titre": f"Taux {declaration.taux_tva.taux} % — calcul sur {declaration.get_source_calcul_display() if declaration.source_calcul else '—'}",
        "provisoire": True, "avertissement": "Modèle de déclaration provisoire — formulaire officiel DGI à confirmer par ETSL.",
        "tableaux": [{"titre": "Déclaration", "colonnes": [_col("rubrique", "Rubrique"), _col("montant", "Montant", True)], "lignes": lignes}],
    })


def archiver_declaration(declaration, user=None):
    contenu = declaration_pdf(declaration)
    doc = archiver_piece(
        contenu, f"{declaration.code}.pdf", f"Déclaration de TVA {declaration.code} — {declaration.mois:%m/%Y}",
        TYPE_GED_DECLARATIONS, "Déclarations fiscales", declaration.code, declaration.mois, user, mots=("tva",),
    )
    declaration.document = doc
    declaration.save(update_fields=["document"])
    return doc


def archiver_journal_periode(period, user=None):
    """Journal (grand livre) de la période clôturée, scellé en GED 10 ans."""
    from .etats import grand_livre, to_pdf

    contenu = en_francais(lambda: to_pdf(grand_livre(period.start_date, period.end_date)))  # archive : français
    return archiver_piece(
        contenu, f"journal-{period}.pdf", f"Grand livre de la période {period}", TYPE_GED_JOURNAUX,
        "Journaux comptables", f"GL-{period}", period.end_date, user, mots=("journal", str(period)),
    )


def archiver_liasse(exercice, user=None):
    from .etats import to_pdf

    contenu = en_francais(lambda: to_pdf(liasse(exercice)))  # archive : français
    return archiver_piece(
        contenu, f"liasse-{exercice}.pdf", f"Liasse fiscale {exercice}", TYPE_GED_DECLARATIONS,
        "Déclarations fiscales", f"LIASSE-{exercice}", _bornes_exercice(exercice)[1], user, mots=("liasse", str(exercice)),
    )
