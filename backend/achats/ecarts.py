"""Écarts M2 (2026-10) : paramètres provisoires, agrément fournisseur M6 / M7, inspection ITP / CND à réception,
archivage GED 10 ans des pièces d'achat, avoirs fournisseurs (contre-passation comptable), dérivation affaire → DA et
location GR → BC.

Toute valeur attendue d'ETSL est un paramètre provisoire (`ParametreAchats`, `RegleInspectionReception`) modifiable à
l'écran Achats, à confirmer ou modifier par ETSL.
"""

import calendar
import hashlib
import io
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from config.i18n import tr

CENT = Decimal("0.01")

# code -> (libellé, valeur par défaut, unité, valeurs admises ou None)
PARAMETRES_ACHATS_DEFAUT = {
    "ENGAGEMENT_MESURE": (
        "Mesure de l'engagement par affaire / centre (1 = reste à facturer, 2 = total commandé)", "1", "choix", {1, 2},
    ),
    "DS_OBLIGATOIRE_GR": (
        "Référence « DS » exigée pour confirmer un BC GLOBAL RENTAL (1 = oui, 0 = non)", "0", "choix", {0, 1},
    ),
    "RETENTION_PIECES_ACHAT_ANS": ("Conservation des pièces d'achat et des litiges en GED", "10", "ans", None),
    "AGREMENT_DUREE_MOIS": ("Durée d'un agrément fournisseur (demande M2 sans date de fin et audit qualité M6)", "12", "mois", None),  # source unique (M2 + M6), à confirmer par ETSL
    "AGREMENT_ALERTE_JOURS": ("Alerte avant la fin d'un agrément fournisseur", "30", "jours", None),
}
TYPE_GED_ACHATS = "pieces-achats"


# -- Paramètres -----------------------------------------------------------------------------------------------------
def get_param(code):
    from .models import ParametreAchats

    label, valeur, unite, _ = PARAMETRES_ACHATS_DEFAUT[code]
    obj, _ = ParametreAchats.objects.get_or_create(code=code, defaults={"label": label, "valeur": Decimal(valeur), "unite": unite})
    return obj.valeur


def assurer_parametres():
    for code in PARAMETRES_ACHATS_DEFAUT:
        get_param(code)


def valider_valeur_parametre(code, valeur):
    admises = PARAMETRES_ACHATS_DEFAUT.get(code, (None, None, None, None))[3]
    if admises is not None:
        if valeur != valeur.to_integral_value() or int(valeur) not in admises:
            raise ValidationError(tr("Valeurs admises : %(liste)s.") % {"liste": ', '.join(str(v) for v in sorted(admises))})
    elif valeur <= 0:
        raise ValidationError("La valeur doit être strictement positive.")


# -- Agrément fournisseur (M6 qualité / M7 HSE) ----------------------------------------------------------------------
def ajouter_mois(jour, mois):
    m = jour.month - 1 + mois
    annee, m = jour.year + m // 12, m % 12 + 1
    return date(annee, m, min(jour.day, calendar.monthrange(annee, m)[1]))


def appliquer_agrement(agrement):
    """Reporte la décision sur la fiche tiers : date de fin d'agrément du domaine (refus = agrément retiré)."""
    from referentiels.models import Partner

    from .models import AgrementFournisseur

    champ = "agree_qualite_jusqu" if agrement.domaine == AgrementFournisseur.Domaine.QUALITE else "agree_hse_jusqu"
    valeur = agrement.date_fin if agrement.statut == AgrementFournisseur.Statut.VALIDE else None
    Partner.objects.filter(pk=agrement.fournisseur_id).update(**{champ: valeur, "updated_at": timezone.now()})


def catalogue_fournisseurs(jour=None):
    """Catalogue fournisseurs : agréments qualité / HSE (dates, alertes) et note /100 de la performance M2."""
    from referentiels.models import Partner

    from .models import AgrementFournisseur
    from .pilotage import performance_fournisseurs

    jour = jour or timezone.localdate()
    alerte = int(get_param("AGREMENT_ALERTE_JOURS"))
    perf = {p["fournisseur_id"]: p for p in performance_fournisseurs()}
    en_cours = set(
        AgrementFournisseur.objects.filter(statut=AgrementFournisseur.Statut.DEMANDE).values_list("fournisseur_id", flat=True)
    )
    rows = []
    for p in Partner.objects.filter(is_active=True, kind__in=(Partner.Kind.FOURNISSEUR, Partner.Kind.BOTH)).order_by("name"):
        echeances = [d for d in (p.agree_qualite_jusqu, p.agree_hse_jusqu) if d]
        fin = min(echeances) if len(echeances) == 2 else None
        agree = p.agrement_valide(jour)
        if p.is_global_rental:
            etat = "intra_groupe"
        elif not agree:
            etat = "non_agree"
        elif fin and (fin - jour).days <= alerte:
            etat = "a_renouveler"
        else:
            etat = "agree"
        perf_p = perf.get(p.pk, {})
        rows.append({
            "id": p.pk, "code": p.code, "nom": p.name, "is_global_rental": p.is_global_rental,
            "agree_qualite_jusqu": p.agree_qualite_jusqu, "agree_hse_jusqu": p.agree_hse_jusqu,
            "agree": agree, "etat": etat, "jours_restants": (fin - jour).days if fin else None,
            "demande_en_cours": p.pk in en_cours,
            "note": perf_p.get("note"), "commandes": perf_p.get("commandes", 0), "litiges_ouverts": perf_p.get("litiges_ouverts", 0),
        })
    return {"rows": rows, "alerte_jours": alerte}


# -- Inspection ITP / CND à réception (M6) ---------------------------------------------------------------------------
def regles_applicables(article):
    """Règle spécifique à l'article, sinon règle de sa catégorie (type d'article) ; None si aucune."""
    from .models import RegleInspectionReception

    actives = RegleInspectionReception.objects.filter(is_active=True)
    return actives.filter(article=article).first() or actives.filter(article__isnull=True, article_type=article.article_type).first()


def inspections_requises(receipt):
    """{"itp": [libellés], "cnd": [(libellé, méthode)]} selon les règles et les articles de la réception."""
    requis = {"itp": [], "cnd": []}
    for ligne in receipt.lines.select_related("purchase_order_line__article"):
        article = ligne.purchase_order_line.article
        if article is None or ligne.quantity <= 0:
            continue
        regle = regles_applicables(article)
        if regle is None:
            continue
        if regle.exige_itp:
            requis["itp"].append(article.code)
        if regle.exige_cnd:
            requis["cnd"].append((article.code, regle.methode_cnd))
    return requis


def declencher_inspections(receipt, user=None):
    """Crée (une fois) les contrôles ITP / CND exigés par les règles ; renvoie les contrôles créés."""
    from qualite.models import ControleQualite

    requis = inspections_requises(receipt)
    existants = set(
        receipt.controles_qualite.exclude(statut=ControleQualite.Statut.ANNULE).values_list("type_controle", flat=True)
    )
    crees = []
    if requis["itp"] and ControleQualite.TypeControle.ITP not in existants:
        crees.append(ControleQualite.objects.create(
            type_controle=ControleQualite.TypeControle.ITP, reception=receipt, created_by=user,
            point_controle=f"ITP réception {receipt.code} — {', '.join(sorted(set(requis['itp'])))}"[:200],
            exigence="Règle d'inspection à réception (achats M2)"[:200], statut=ControleQualite.Statut.EN_ATTENTE,
        ))
    if requis["cnd"] and ControleQualite.TypeControle.CND not in existants:
        methode = next((m for _, m in requis["cnd"] if m), "")
        crees.append(ControleQualite.objects.create(
            type_controle=ControleQualite.TypeControle.CND, reception=receipt, created_by=user, methode_cnd=methode,
            point_controle=f"CND réception {receipt.code} — {', '.join(sorted({a for a, _ in requis['cnd']}))}"[:200],
            exigence="Règle d'inspection à réception (achats M2)"[:200], statut=ControleQualite.Statut.EN_ATTENTE,
        ))
    return crees


def controles_bloquants(receipt):
    """Message de blocage si un contrôle M6 de la réception (réception, ITP, CND) n'est pas validé ou est non conforme."""
    from qualite.models import ControleQualite

    controles = list(receipt.controles_qualite.exclude(statut=ControleQualite.Statut.ANNULE).order_by("created_at"))
    if not controles:
        return "Contrôle qualité à réception (M6) non validé : réception en attente."
    for ctrl in controles:
        if ctrl.statut != ControleQualite.Statut.VALIDE:
            if ctrl.type_controle == ControleQualite.TypeControle.RECEPTION:
                return "Contrôle qualité à réception (M6) non validé : réception en attente."
            return f"Inspection {ctrl.get_type_controle_display().split(' (')[0]} {ctrl.code} (M6) non validée : réception en attente."
        if ctrl.resultat == ControleQualite.Resultat.NON_CONFORME:
            return f"Contrôle qualité {ctrl.code} non conforme : ouvrez un litige fournisseur."
    return None


# -- Archivage GED (conservation des pièces d'achat) -----------------------------------------------------------------
def _pdf(titre, lignes, tableau=None):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, title=titre)
    entete = Table([[k, v] for k, v in lignes], colWidths=[50 * mm, 130 * mm])
    entete.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 9),
                                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef1f8"))]))
    elements = [Paragraph(titre, styles["Title"]), Spacer(1, 4 * mm), entete]
    if tableau:
        detail = Table(tableau, repeatRows=1)
        detail.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 8),
                                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef1f8"))]))
        elements += [Spacer(1, 6 * mm), detail]
    doc.build(elements)
    return buf.getvalue()


def _archiver(contenu, nom, titre, reference, user, mots):
    from django.core.files.base import ContentFile

    from documents.models import Document, DocumentType, Version

    retention = int(get_param("RETENTION_PIECES_ACHAT_ANS"))
    type_doc, _ = DocumentType.objects.get_or_create(
        code=TYPE_GED_ACHATS, defaults={"label": "Pièces d'achat (BC, réceptions, litiges, avoirs)", "retention_years": retention}
    )
    if (type_doc.retention_years or 0) < retention:
        type_doc.retention_years = retention
        type_doc.save(update_fields=["retention_years"])
    sha = hashlib.sha256(contenu).hexdigest()
    document = Document.objects.create(
        title=titre[:200], status=Document.Status.ARCHIVED, archived_at=timezone.now(), type=type_doc,
        document_date=timezone.localdate(), reference=reference[:120], keywords=list(mots), sha256=sha, created_by=user,
    )
    version = Version.objects.create(document=document, number=1, file=ContentFile(contenu, name=nom), sha256=sha,
                                     size=len(contenu), original_filename=nom, created_by=user)
    document.current_version = version
    document.save(update_fields=["current_version"])
    return document


def archiver_bc(bc, user=None):
    lignes = [
        ("Bon de commande", bc.code), ("Fournisseur", bc.supplier.name if bc.supplier_id else "—"),
        ("Date", f"{bc.order_date:%d/%m/%Y}"), ("Livraison attendue", f"{bc.expected_date:%d/%m/%Y}" if bc.expected_date else "—"),
        ("GLOBAL RENTAL (618)", "oui" if bc.is_global_rental else "non"), ("Référence DS", bc.reference_ds or "—"),
        ("Affaire", bc.affaire.code if bc.affaire_id else "—"), ("Total HT", f"{bc.total:.2f}"),
    ]
    tableau = [["Désignation", "Qté", "PU", "Total"]] + [
        [l.label[:60], f"{l.quantity:g}", f"{l.unit_price:.2f}", f"{l.price_total:.2f}"] for l in bc.lines.all()
    ]
    contenu = _pdf(f"Bon de commande {bc.code}", lignes, tableau)
    return _archiver(contenu, f"{bc.code}.pdf", f"Bon de commande {bc.code}", bc.code, user, ("achats", "BC", bc.code))


def archiver_reception(receipt, user=None):
    lignes = [
        ("Réception", receipt.code), ("Bon de commande", receipt.purchase_order.code),
        ("Fournisseur", receipt.purchase_order.supplier.name if receipt.purchase_order.supplier_id else "—"),
        ("Date de réception", f"{receipt.received_at:%d/%m/%Y}"), ("Réceptionné par", str(receipt.received_by or "—")),
        ("Contrôles M6", ", ".join(f"{c.code} {c.get_resultat_display()}" for c in receipt.controles_qualite.all()) or "—"),
    ]
    tableau = [["Désignation", "Qté", "Lot", "Certificat"]] + [
        [l.purchase_order_line.label[:60], f"{l.quantity:g}", l.numero_lot or "—",
         f"{l.certificat_type.upper()} {l.numero_certificat}" if l.certificat_type else "—"]
        for l in receipt.lines.select_related("purchase_order_line")
    ]
    contenu = _pdf(f"Réception {receipt.code}", lignes, tableau)
    return _archiver(contenu, f"{receipt.code}.pdf", f"Réception {receipt.code}", receipt.code, user,
                     ("achats", "reception", receipt.code, receipt.purchase_order.code))


def archiver_litige(litige, user=None):
    lignes = [
        ("Litige", litige.code), ("Bon de commande", litige.purchase_order.code), ("Type", litige.get_type_display()),
        ("Description", litige.description[:500]), ("Relances", str(litige.nb_relances)),
        ("Contentieux M12", litige.contentieux.code if litige.contentieux_id else "—"),
        ("Résolution", litige.resolution[:500]), ("Résolu le", f"{litige.resolu_le:%d/%m/%Y}" if litige.resolu_le else "—"),
    ]
    contenu = _pdf(f"Litige fournisseur {litige.code}", lignes)
    return _archiver(contenu, f"{litige.code}.pdf", f"Litige fournisseur {litige.code}", litige.code, user,
                     ("achats", "litige", litige.code, litige.purchase_order.code))


def archiver_avoir(avoir, user=None):
    lignes = [
        ("Avoir", avoir.code), ("Facture", avoir.facture.code), ("Réf. fournisseur", avoir.reference_fournisseur or "—"),
        ("Date", f"{avoir.date_avoir:%d/%m/%Y}"), ("Montant HT", f"{avoir.montant_ht:.2f}"), ("Motif", avoir.motif[:500]),
        ("Écriture", avoir.move.number if avoir.move_id else "—"),
    ]
    contenu = _pdf(f"Avoir fournisseur {avoir.code}", lignes)
    return _archiver(contenu, f"{avoir.code}.pdf", f"Avoir fournisseur {avoir.code}", avoir.code, user,
                     ("achats", "avoir", avoir.code, avoir.facture.code))


# -- Avoir fournisseur : contre-passation au prorata de l'écriture d'achat --------------------------------------------
@transaction.atomic
def comptabiliser_avoir(avoir, user):
    from accounting_kernel.models import AccountMove, AccountMoveLine
    from accounting_kernel.services import period_for_date, post_move

    from .models import AvoirFournisseur, PurchaseInvoice

    avoir = AvoirFournisseur.objects.select_for_update(of=("self",)).select_related("facture__move").get(pk=avoir.pk)
    if avoir.statut != AvoirFournisseur.Statut.BROUILLON:
        raise ValidationError("Avoir déjà comptabilisé.")
    facture = avoir.facture
    if facture.status != PurchaseInvoice.Status.COMPTABILISEE or facture.move_id is None:
        raise ValidationError("La facture d'origine doit être comptabilisée.")
    total_ht = facture.total
    if not total_ht:
        raise ValidationError("Facture d'origine sans montant.")
    deja = sum((a.montant_ht for a in facture.avoirs.filter(statut=AvoirFournisseur.Statut.COMPTABILISE)), Decimal("0"))
    if deja + avoir.montant_ht > total_ht:
        raise ValidationError(tr("Avoirs cumulés (%(valeur)s) supérieurs au HT de la facture (%(total_ht)s).") % {"valeur": format(deja + avoir.montant_ht, '.2f'), "total_ht": format(total_ht, '.2f')})
    ratio = avoir.montant_ht / total_ht
    origine = facture.move
    move = AccountMove.objects.create(
        journal=origine.journal, period=period_for_date(avoir.date_avoir), date=avoir.date_avoir,
        reference=avoir.reference_fournisseur or avoir.code,
        label=f"Avoir fournisseur {avoir.code} — facture {facture.code}", source="M2", source_ref=avoir.code,
        status=AccountMove.Status.DRAFT,
    )
    lignes = list(origine.lines.order_by("order"))
    total_debit = Decimal("0")
    total_credit = Decimal("0")
    crees = []
    for ligne in lignes:
        debit = (ligne.credit * ratio).quantize(CENT, rounding=ROUND_HALF_UP)
        credit = (ligne.debit * ratio).quantize(CENT, rounding=ROUND_HALF_UP)
        crees.append(AccountMoveLine(
            move=move, account=ligne.account, partner=ligne.partner, analytic_account=ligne.analytic_account,
            label=f"Avoir {avoir.code} — {ligne.label}"[:200], debit=debit, credit=credit, order=ligne.order,
        ))
        total_debit += debit
        total_credit += credit
    # Arrondi : l'écart éventuel est porté par la ligne fournisseur (401), au débit.
    ecart = total_credit - total_debit
    if ecart:
        fournisseur = next((l for l in crees if l.debit > 0), None)
        if fournisseur is None:
            raise ValidationError("Écriture d'origine sans ligne fournisseur.")
        fournisseur.debit += ecart
    for ligne in crees:
        ligne.save()
    avoir.move = post_move(move, user=user)
    avoir.statut = AvoirFournisseur.Statut.COMPTABILISE
    avoir.comptabilise_par = user
    avoir.comptabilise_le = timezone.now()
    avoir.save(update_fields=["move", "statut", "comptabilise_par", "comptabilise_le", "updated_at"])
    avoir.document_ged = archiver_avoir(avoir, user)
    avoir.save(update_fields=["document_ged"])
    return avoir


# -- Dérivations amont : affaire → DA (M1), location GR → BC (M4) ----------------------------------------------------
TYPES_ACHETABLES = ("matiere", "consommable", "produit")


@transaction.atomic
def da_depuis_affaire(affaire, user):
    """DA brouillon pré-remplie : imputation analytique de l'affaire, lignes = articles achetables de l'offre gagnée."""
    from commercial.models import Affaire, Estimate

    from .models import PurchaseRequest, PurchaseRequestLine

    if affaire.status not in (Affaire.Status.CONFIRMEE, Affaire.Status.EN_COURS):
        raise ValidationError({"affaire": tr("Affaire %(affaire_code)s %(status)s : seule une affaire validée (confirmée / en cours) génère ses besoins d'achat.") % {"affaire_code": affaire.code, "status": affaire.get_status_display().lower()}})
    if PurchaseRequest.objects.filter(affaire=affaire, status=PurchaseRequest.Status.BROUILLON).exists():
        raise ValidationError({"affaire": "Une DA brouillon existe déjà pour cette affaire : complétez-la."})
    analytic = affaire.analytic or affaire.assurer_compte_analytique()
    da = PurchaseRequest.objects.create(
        title=f"Besoins d'achat — affaire {affaire.code}"[:200], requester=user, affaire=affaire, analytic=analytic,
        expected_date=affaire.start_date, department="Affaire",
        notes=f"DA générée depuis l'affaire {affaire.code} ({affaire.title}).",
    )
    offre = None
    if affaire.opportunity_id:
        offre = Estimate.objects.filter(opportunity_id=affaire.opportunity_id, status=Estimate.Status.GAGNEE).order_by("-version").first()
    n = 0
    if offre is not None:
        for ligne in offre.lines.select_related("article").filter(article__isnull=False, article__article_type__in=TYPES_ACHETABLES):
            PurchaseRequestLine.objects.create(
                request=da, article=ligne.article, label=ligne.label, quantity=ligne.quantity, unit=ligne.unit or ligne.article.unit,
                estimated_price=ligne.article.purchase_price or 0,
            )
            n += 1
    if n == 0:
        da.notes += " Aucune ligne d'offre gagnée dérivable (article matière / consommable / produit) : lignes à saisir."
        da.save(update_fields=["notes", "updated_at"])
    return da, n


@transaction.atomic
def bc_depuis_location_gr(location, user):
    """BC GLOBAL RENTAL (charge 618) généré depuis la location M4, lié à elle ; imputé à l'affaire de la location."""
    from logistique.models import LocationGR

    from .models import PurchaseOrder, PurchaseOrderLine

    if location.statut == LocationGR.Statut.ANNULEE:
        raise ValidationError({"location": "Location GR annulée."})
    if not location.partenaire.is_global_rental:
        raise ValidationError({"location": "Partenaire de la location non marqué GLOBAL RENTAL."})
    from comptabilite.gr import bc_lie, controler_liaison_bc

    if bc_lie(location):
        raise ValidationError({"location": tr("Un BC achats est déjà lié à la location %(location_code)s.") % {"location_code": location.code}})
    try:
        controler_liaison_bc(location, None)
    except ValidationError as exc:
        raise ValidationError({"location": exc.messages})
    analytic = None
    if location.affaire_id:
        analytic = location.affaire.analytic or location.affaire.assurer_compte_analytique()
    bc = PurchaseOrder.objects.create(
        supplier=location.partenaire, is_global_rental=True, location_gr=location, affaire=location.affaire,
        analytic=analytic, currency=location.devise, created_by=user,
        expected_date=location.date_debut, reference_ds=location.reference_bc[:40],
        notes=f"BC GR généré depuis la location {location.code} (M4) — imputation 618.",
    )
    PurchaseOrderLine.objects.create(
        purchase_order=bc, label=f"Location GR {location.code} — {location.equipement.label}"[:200],
        quantity=1, unit_price=location.montant_estime or 0,
    )
    # Lien unique : la location porte aussi le BC (lu par M4 et par M10 pour l'exclusion anti-double 618).
    type(location).objects.filter(pk=location.pk, bon_commande_achat__isnull=True).update(bon_commande_achat=bc)
    return bc
