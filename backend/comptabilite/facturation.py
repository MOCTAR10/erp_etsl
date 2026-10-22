"""Facturation client M10 : facture / avoir émis via le noyau comptable (411 · 706 · 443), scellés, PDF archivé 10 ans.

Sources « à facturer » : jalons réalisés (M1) et situations de travaux validées (M3). Une facture émise ne se
modifie jamais : toute correction passe par un avoir. Le modèle d'impression (en-tête, mentions) est une donnée
ETSL (`ModeleFacture`), provisoire tant qu'ETSL ne l'a pas confirmé.
"""

import hashlib
import io
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from accounting_kernel.models import AccountMove, AccountMoveLine, Journal
from accounting_kernel.services import period_for_date, post_move
from referentiels.models import Account, Partner

from .models import FactureClient, LigneFactureClient, ModeleFacture, TauxTva

TYPE_GED_FACTURE = "factures_clients"
RETENTION_FACTURE_ANS = 10

ENTETE_DEFAUT = (
    "ETSL — Entreprise de Tuyauterie, Soudure et Location\nAdresse : à renseigner, Gabon\n"
    "NIF : à renseigner · RCCM : à renseigner · Tél. / e-mail : à renseigner"
)
ANCIENNE_RAISON_SOCIALE = "Établissements Techniques et Services Logistiques"

MODELE_DEFAUT = {
    "entete": ENTETE_DEFAUT,
    "mentions_legales": "Facture soumise à la TVA au taux en vigueur. Mentions légales à confirmer par ETSL.",
    "conditions_paiement": "Paiement à réception de facture ou à l'échéance indiquée, par virement.",
    "coordonnees_bancaires": "À renseigner (banque, IBAN / numéro de compte).",
    "pied_page": "ETSL — document généré par l'ERP.",
}


def get_modele():
    """Le modèle de facture (créé à la volée avec des textes provisoires)."""
    return ModeleFacture.objects.get_or_create(code="DEFAUT", defaults=MODELE_DEFAUT)[0]


def _taux_defaut():
    taux = TauxTva.objects.filter(is_active=True).order_by("-is_default", "code").first()
    if taux is None:
        raise ValidationError("Aucun taux de TVA actif : paramétrez-le (Comptabilité → TVA).")
    return taux


def _compte(code):
    try:
        return Account.objects.get(code=code)
    except Account.DoesNotExist:
        raise ValidationError(f"Compte {code} absent du plan comptable.")


def _echeance(date):
    from datetime import timedelta

    return date + timedelta(days=get_modele().delai_paiement_jours)


def _ligne(facture, designation, montant, quantite=Decimal("1"), compte=None):
    return LigneFactureClient.objects.create(
        facture=facture, designation=designation[:250], quantite=quantite,
        prix_unitaire=Decimal(montant) / Decimal(quantite) if quantite != 1 else Decimal(montant),
        compte_produit=compte or _compte("706000"),
    )


def _client_de_affaire(affaire):
    client = getattr(affaire, "client", None)
    partner = getattr(client, "partner", None)
    if partner is None:
        raise ValidationError("L'affaire n'a pas de client (tiers) : rattachez-en un avant de facturer.")
    return partner


@transaction.atomic
def facture_depuis_jalon(jalon, user):
    from commercial.models import Milestone

    jalon = Milestone.objects.select_for_update(of=("self",)).select_related("affaire__client__partner").get(pk=jalon.pk)
    if jalon.actual_date is None:
        raise ValidationError("Le jalon n'est pas réalisé : il n'est pas facturable.")
    if jalon.montant <= 0:
        raise ValidationError("Le jalon n'a pas de montant facturable.")
    if jalon.facture_le or FactureClient.objects.filter(jalon=jalon, nature="facture").exists():
        raise ValidationError("Ce jalon est déjà facturé (ou une facture est en préparation).")
    facture = FactureClient.objects.create(
        client=_client_de_affaire(jalon.affaire), affaire=jalon.affaire, jalon=jalon, cree_par=user,
        objet=f"{jalon.affaire.code} — {jalon.label}", taux_tva=_taux_defaut(), echeance=_echeance(timezone.localdate()),
    )
    _ligne(facture, jalon.label, jalon.montant)
    facture.recalculer()
    return facture


@transaction.atomic
def facture_depuis_situation(situation, user):
    from operations.models import SituationTravaux

    situation = SituationTravaux.objects.select_for_update(of=("self",)).select_related("affaire__client__partner").get(pk=situation.pk)
    if situation.status != SituationTravaux.Status.VALIDEE:
        raise ValidationError("Seule une situation validée peut être facturée.")
    if situation.amount <= 0:
        raise ValidationError("La situation n'a pas de montant.")
    if situation.affaire is None:
        raise ValidationError("La situation n'est rattachée à aucune affaire : le client est inconnu.")
    if FactureClient.objects.filter(situation=situation, nature="facture").exists():
        raise ValidationError("Une facture est déjà en préparation pour cette situation.")
    facture = FactureClient.objects.create(
        client=_client_de_affaire(situation.affaire), affaire=situation.affaire, situation=situation, cree_par=user,
        objet=f"{situation.affaire.code} — {situation.label}", taux_tva=_taux_defaut(),
        echeance=_echeance(timezone.localdate()),
    )
    _ligne(facture, situation.label, situation.amount)
    facture.recalculer()
    return facture


def _deja_avoir(origine):
    return sum((a.montant_ht for a in origine.avoirs.all()), Decimal("0"))


@transaction.atomic
def creer_avoir(origine, user, montant_ht=None, motif=""):
    """Avoir (total ou partiel) sur une facture émise ; cumul des avoirs ≤ montant de la facture."""
    origine = FactureClient.objects.select_for_update().get(pk=origine.pk)
    if origine.nature != FactureClient.Nature.FACTURE or origine.statut != FactureClient.Statut.EMISE:
        raise ValidationError("Un avoir se rattache à une facture émise.")
    restant = origine.montant_ht - _deja_avoir(origine)
    montant = Decimal(str(montant_ht)) if montant_ht not in (None, "") else restant
    if montant <= 0:
        raise ValidationError("Le montant de l'avoir doit être strictement positif.")
    if montant > restant:
        raise ValidationError(f"Avoir supérieur au reliquat facturable ({restant}).")
    avoir = FactureClient.objects.create(
        nature=FactureClient.Nature.AVOIR, client=origine.client, affaire=origine.affaire, facture_origine=origine,
        objet=(motif or f"Avoir sur {origine.code}")[:250], taux_tva=origine.taux_tva, cree_par=user,
    )
    premiere = origine.lignes.first()
    _ligne(avoir, f"Avoir sur facture {origine.code}", montant, compte=premiere.compte_produit if premiere else None)
    avoir.recalculer()
    return avoir


@transaction.atomic
def emettre_facture(facture, user):
    """Comptabilise (journal VTE) puis scelle : Dr 411 TTC · Cr 706 HT · Cr 443 TVA (inverse pour un avoir)."""
    facture = FactureClient.objects.select_for_update(of=("self",)).select_related("client", "taux_tva", "affaire").get(pk=facture.pk)
    if facture.statut != FactureClient.Statut.BROUILLON:
        raise ValidationError("Facture déjà émise : corrigez-la par un avoir.")
    lignes = list(facture.lignes.select_related("compte_produit"))
    if not lignes:
        raise ValidationError("Une facture doit comporter au moins une ligne.")
    facture.recalculer()
    if facture.montant_ht <= 0:
        raise ValidationError("Le montant de la facture doit être strictement positif.")
    if facture.client.kind != Partner.Kind.CLIENT:
        raise ValidationError("Le tiers facturé n'est pas un client.")
    if facture.taux_tva_id is None:
        raise ValidationError("Taux de TVA manquant.")
    avoir = facture.nature == FactureClient.Nature.AVOIR
    if avoir:
        origine = FactureClient.objects.select_for_update().get(pk=facture.facture_origine_id)
        autres = sum((a.montant_ht for a in origine.avoirs.exclude(pk=facture.pk).filter(statut="emise")), Decimal("0"))
        if autres + facture.montant_ht > origine.montant_ht:
            raise ValidationError("Les avoirs cumulés dépassent le montant de la facture d'origine.")
    try:
        journal = Journal.objects.get(code="VTE")
    except Journal.DoesNotExist:
        raise ValidationError("Journal des ventes VTE absent (seed_accounting).")

    analytic = facture.affaire.analytic if facture.affaire_id and facture.affaire.analytic_id else None
    move = AccountMove.objects.create(
        journal=journal, period=period_for_date(facture.date), date=facture.date, reference=facture.code,
        label=f"{'Avoir' if avoir else 'Facture'} {facture.code} — {facture.client.name}"[:200],
        source="M10", source_ref=facture.code, created_by=user,
    )
    sens_client, sens_produit = ("credit", "debit") if avoir else ("debit", "credit")
    from . import retenues

    facture.taux_retenue, facture.montant_retenue = retenues.calculer(facture)  # M1 → M10 : retenue de garantie
    ordre = 0
    AccountMoveLine.objects.create(
        move=move, account=_compte("411000"), partner=facture.client, order=ordre, label=facture.code,
        **{sens_client: facture.montant_ttc - facture.montant_retenue},
    )
    if facture.montant_retenue > 0:
        ordre += 1
        AccountMoveLine.objects.create(
            move=move, account=retenues.compte_retenue(), partner=facture.client, order=ordre,
            label=f"Retenue de garantie {facture.taux_retenue:g} % {facture.code}",
            **{sens_client: facture.montant_retenue},
        )
    par_compte = {}
    for l in lignes:
        par_compte[l.compte_produit_id] = par_compte.get(l.compte_produit_id, Decimal("0")) + l.montant
    for compte_id, montant in par_compte.items():
        ordre += 1
        AccountMoveLine.objects.create(
            move=move, account_id=compte_id, analytic_account=analytic, order=ordre, label=facture.code,
            **{sens_produit: montant},
        )
    if facture.montant_tva > 0:
        ordre += 1
        AccountMoveLine.objects.create(
            move=move, account=facture.taux_tva.compte_collecte, order=ordre, label=f"TVA {facture.code}",
            **{sens_produit: facture.montant_tva},
        )
    posted = post_move(move, user=user)

    facture.move, facture.statut = posted, FactureClient.Statut.EMISE
    facture.emise_par, facture.emise_le = user, timezone.now()
    facture.modele_provisoire = get_modele().est_provisoire
    facture.echeance = facture.echeance or _echeance(facture.date)
    facture.save()
    if not avoir:
        _sceller_source(facture)
    archiver_facture(facture, user)
    return facture


def _sceller_source(facture):
    """Retour vers M1/M3 : le jalon / la situation reçoit la référence de la facture et est scellé."""
    jour = timezone.localdate()
    if facture.jalon_id:
        from commercial.models import Milestone

        Milestone.objects.filter(pk=facture.jalon_id).update(facture_le=jour)
    if facture.situation_id:
        from operations.models import SituationTravaux

        SituationTravaux.objects.filter(pk=facture.situation_id).update(
            status=SituationTravaux.Status.FACTUREE, facture_ref=facture.code, facture_le=jour
        )


def facture_pdf(facture):
    """PDF de la facture (reportlab) d'après le modèle ETSL ; avertissement tant que le modèle est provisoire."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    modele = get_modele()
    styles = getSampleStyleSheet()
    fm = lambda v: f"{v:,.0f}".replace(",", " ")  # noqa: E731
    avoir = facture.nature == FactureClient.Nature.AVOIR
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, title=facture.code)
    br = lambda t: t.replace("\n", "<br/>")  # noqa: E731
    story = [
        Paragraph(br(modele.entete), styles["Normal"]), Spacer(1, 6 * mm),
        Paragraph(f"{'AVOIR' if avoir else 'FACTURE'} {facture.code}", styles["Title"]),
        Paragraph(f"Date : {facture.date:%d/%m/%Y}" + (f" · Échéance : {facture.echeance:%d/%m/%Y}" if facture.echeance else ""), styles["Normal"]),
        Paragraph(f"Client : <b>{facture.client.name}</b> ({facture.client.code})", styles["Normal"]),
    ]
    if facture.facture_origine_id:
        story.append(Paragraph(f"Avoir sur la facture {facture.facture_origine.code}", styles["Normal"]))
    if facture.objet:
        story.append(Paragraph(f"Objet : {facture.objet}", styles["Normal"]))
    story.append(Spacer(1, 5 * mm))
    rows = [["Désignation", "Qté", "PU HT", "Montant HT"]]
    for l in facture.lignes.all():
        rows.append([l.designation, f"{l.quantite:g}", fm(l.prix_unitaire), fm(l.montant)])
    taux = facture.taux_tva.taux if facture.taux_tva_id else 0
    rows += [["", "", "Total HT", fm(facture.montant_ht)], ["", "", f"TVA {taux:g} %", fm(facture.montant_tva)],
             ["", "", "TOTAL TTC (FCFA)", fm(facture.montant_ttc)]]
    if facture.montant_retenue:
        rows += [["", "", f"Retenue de garantie {facture.taux_retenue:g} %", f"- {fm(facture.montant_retenue)}"],
                 ["", "", "NET À PAYER (FCFA)", fm(facture.net_a_payer)]]
    table = Table(rows, colWidths=[100 * mm, 20 * mm, 35 * mm, 30 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#12308f")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -4), 0.3, colors.grey), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    story += [table, Spacer(1, 6 * mm)]
    for texte in (modele.conditions_paiement, modele.coordonnees_bancaires, modele.mentions_legales):
        if texte:
            story.append(Paragraph(br(texte), styles["Normal"]))
    if facture.modele_provisoire or modele.est_provisoire:
        story += [Spacer(1, 5 * mm), Paragraph(
            "<font color='#d4142a'><b>AVERTISSEMENT</b> — modèle de facture provisoire : en-tête et mentions légales "
            "à confirmer par ETSL avant diffusion.</font>", styles["Normal"])]
    if modele.pied_page:
        story += [Spacer(1, 6 * mm), Paragraph(br(modele.pied_page), styles["Italic"])]
    doc.build(story)
    return buf.getvalue()


def archiver_facture(facture, user=None):
    """Scelle le PDF de la facture émise en GED (conservation ≥ 10 ans)."""
    from django.core.files.base import ContentFile

    from documents.models import Document, DocumentType, Version

    type_doc, _ = DocumentType.objects.get_or_create(
        code=TYPE_GED_FACTURE, defaults={"label": "Factures clients", "retention_years": RETENTION_FACTURE_ANS}
    )
    if (type_doc.retention_years or 0) < RETENTION_FACTURE_ANS:
        type_doc.retention_years = RETENTION_FACTURE_ANS
        type_doc.save(update_fields=["retention_years"])
    contenu = facture_pdf(facture)
    sha = hashlib.sha256(contenu).hexdigest()
    nom = f"{facture.code}.pdf"
    document = Document.objects.create(
        title=f"{'Avoir' if facture.nature == 'avoir' else 'Facture'} {facture.code} — {facture.client.name}"[:200],
        status=Document.Status.ARCHIVED, archived_at=timezone.now(), type=type_doc, document_date=facture.date,
        counterparty=facture.client.name, reference=facture.code, keywords=["facture", "client", facture.code],
        sha256=sha, created_by=user,
    )
    version = Version.objects.create(
        document=document, number=1, file=ContentFile(contenu, name=nom), sha256=sha, size=len(contenu),
        original_filename=nom, created_by=user,
    )
    document.current_version = version
    document.save(update_fields=["current_version"])
    facture.document = document
    facture.save(update_fields=["document"])
    return document
