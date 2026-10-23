"""Vitrine — GED (socle), circuits de validation (workflow) et juridique (M12).

GED : documents PDF de différents types répartis sur 12 mois (version 1 avec empreinte SHA-256), soumis au circuit
de leur type par `workflow.services.start_circuit` ; les plus anciens sont menés à l'archivage par
`complete_task` (assignataire de chaque étape), les récents restent en attente (dont quelques tâches en retard).
Juridique : conventions, cautions, assurances, contentieux, courriers et dossiers GLOBAL RENTAL (ORM, comme le seed M12).
"""

import hashlib
import io
from datetime import timedelta
from decimal import Decimal

from django.core.files.base import ContentFile
from django.db import transaction

from documents.models import Document, DocumentType, Version
from juridique.models import Assurance, Caution, Contentieux, Convention, Courrier, DossierGlobalRental
from referentiels.models import Partner
from workflow.models import Task

from .outils import MOIS, ajouter_mois, alea, antidater, debut_mois, instant, jour_du_mois, ouvre

# (type GED, gabarit d'intitulé, documents par mois, contrepartie)
FLUX_GED = [
    ("factures_fournisseurs", "Facture fournisseur {fournisseur} - {mois}", 3, "fournisseur"),
    ("devis_bons_de_commande", "Devis {fournisseur} - besoin chantier {mois}", 1, "fournisseur"),
    ("courriers", "Courrier client - {client} - {mois}", 1, "client"),
    ("comptes_rendus_reunion", "Compte-rendu de réunion de chantier - {client} - {mois}", 1, "client"),
    ("documents_bancaires", "Relevé bancaire - {mois}", 1, "banque"),
    ("documents_techniques_plans", "Plans isométriques et nomenclature - {client} - {mois}", 1, "client"),
    ("documents_qualite_iso", "Rapport de contrôle CND - {client} - {mois}", 1, "client"),
    ("documents_douaniers_transport", "Déclaration en douane import matière - {mois}", 0.5, "fournisseur"),
]


def _pdf(titre, lignes):
    """Petit PDF lisible (reportlab) : la démonstration peut ouvrir et prévisualiser chaque document."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    tampon = io.BytesIO()
    page = canvas.Canvas(tampon, pagesize=A4)
    page.setFont("Helvetica-Bold", 14)
    page.drawString(56, 780, titre[:90])
    page.setFont("Helvetica", 10)
    y = 750
    for ligne in lignes + ["", "Document de démonstration (jeu vitrine ETSL) - données fictives."]:
        page.drawString(56, y, ligne[:110])
        y -= 16
    page.showPage()
    page.save()
    return tampon.getvalue()


class VitrineGed:
    def ged(self):
        auteur = self.user("admin@etls.local")
        clients = list(Partner.objects.filter(code__startswith="CLT-").order_by("code"))
        fournisseurs = list(Partner.objects.filter(code__startswith="FRN-").order_by("code"))
        types = {t.code: t for t in DocumentType.objects.all()}
        for k in range(MOIS - 1, -1, -1):
            mois = debut_mois(self.today, k)
            r = alea(f"ged-{mois}")
            for code_type, gabarit, par_mois, partie in FLUX_GED:
                nombre = int(par_mois) if par_mois >= 1 else int(k % 2 == 0)
                for n in range(nombre):
                    tiers = r.choice(clients if partie == "client" else fournisseurs)
                    titre = gabarit.format(client=tiers.name, fournisseur=tiers.name, mois=f"{mois:%m/%Y}")
                    if nombre > 1:
                        titre += f" (n°{n + 1})"
                    if Document.objects.filter(title=titre).exists():
                        continue
                    jour = ouvre(jour_du_mois(self.today, k, 3 + (n * 9 + len(code_type)) % 24))
                    with transaction.atomic():
                        self._document(titre, types.get(code_type), tiers, jour, auteur, r, k)

    def _document(self, titre, type_doc, tiers, jour, auteur, r, k):
        from workflow.services import complete_task, start_circuit

        montant = Decimal(r.randint(8, 400) * 50_000) if type_doc and "factures" in type_doc.code else None
        contenu = _pdf(titre, [f"Date : {jour:%d/%m/%Y}", f"Tiers : {tiers.name if tiers else '-'}",
                               f"Type : {type_doc.label if type_doc else 'Document'}"]
                       + ([f"Montant HT : {montant:,.0f} FCFA".replace(",", " ")] if montant else []))
        doc = Document.objects.create(
            title=titre, type=type_doc, counterparty=tiers.name if tiers else "", document_date=jour,
            reference=f"REF-{jour:%y%m%d}-{r.randint(100, 999)}", amount=montant, status=Document.Status.DRAFT,
            keywords=[type_doc.label] if type_doc else [],
        )
        version = Version.objects.create(
            document=doc, number=1, file=ContentFile(contenu, name=f"{doc.reference}.pdf"),
            sha256=hashlib.sha256(contenu).hexdigest(), size=len(contenu), original_filename=f"{doc.reference}.pdf",
            created_by=auteur,
        )
        doc.current_version = version
        doc.sha256 = version.sha256
        doc.save(update_fields=["current_version", "sha256"])
        antidater(Document, doc.pk, created_at=instant(jour, 9))
        antidater(Version, version.pk, created_at=instant(jour, 9))
        if type_doc is not None and type_doc.officiel:
            return  # type officiel : archivage soumis à signature avancée, laissé en brouillon
        # Circuit de validation : soumis puis traité ; récent = en attente (certaines tâches dépassent leur échéance).
        tache = start_circuit(doc, auteur)
        depart = instant(jour, 10)
        delai = r.randint(1, 4)
        while tache is not None:
            antidater(Task, tache.pk, created_at=depart, due_date=depart + timedelta(days=3))
            if tache.assigned_to_id is None or (k == 0 and r.random() < 0.7):
                break
            fin = depart + timedelta(days=delai, hours=r.randint(1, 6))
            if fin.month != depart.month:  # traitement dans le mois de la soumission
                fin = depart + timedelta(hours=r.randint(2, 7))
            if fin.date() >= self.today:
                break
            suivante = complete_task(tache, tache.assigned_to)
            antidater(Task, tache.pk, completed_at=fin)
            tache, depart = suivante, fin
        if tache is None:
            antidater(Document, doc.pk, archived_at=depart, submitted_at=instant(jour, 10))
        else:
            antidater(Document, doc.pk, submitted_at=instant(jour, 10))

    # -- juridique -------------------------------------------------------------------------------------------
    def juridique(self):
        banque = Partner.objects.filter(code="BANQUE-01").first() or Partner.objects.filter(kind="fournisseur").first()
        assureur = Partner.objects.filter(code="ASSUREUR-01").first() or banque
        with transaction.atomic():
            self._conventions()
            self._cautions(banque)
            self._assurances(assureur)
            self._contentieux()
            self._courriers()
            self._dossiers_gr()

    def _conventions(self):
        for i, affaire in enumerate(self.affaires_vitrine.values()):
            titre = f"Convention - {affaire.title}"[:250]
            if Convention.objects.filter(titre=titre).exists():
                continue
            fin = affaire.end_date if affaire.status != "cloturee" else affaire.end_date
            Convention.objects.create(
                type="maintenance" if affaire.affaire_type in ("maintenance", "fourniture") else "marche_travaux",
                titre=titre, partenaire=affaire.client.partner if affaire.client_id else None,
                montant=affaire.contract_amount, date_debut=affaire.start_date, date_fin=fin,
                renouvelable=affaire.affaire_type == "maintenance", affaire=affaire,
                statut="cloture" if affaire.status == "cloturee" else "signe",
            )
        bail = "Bail commercial - base logistique d'Owendo"
        if not Convention.objects.filter(titre=bail).exists():
            Convention.objects.create(type="bail", titre=bail, montant=Decimal(54_000_000), renouvelable=True,
                                      date_debut=ajouter_mois(self.today, -30), date_fin=self.today + timedelta(days=58),
                                      statut="signe", commentaire="Renouvellement à négocier avant échéance.")

    def _cautions(self, banque):
        for i, affaire in enumerate(list(self.affaires_vitrine.values())[:8]):
            objet = f"Garantie de bonne exécution - {affaire.title}"[:250]
            if Caution.objects.filter(objet=objet).exists():
                continue
            levee = affaire.status == "cloturee"
            Caution.objects.create(
                type="bonne_execution" if i % 3 else "retenue", emetteur=banque,
                beneficiaire=affaire.client.partner.name if affaire.client_id else "Maître d'ouvrage", objet=objet,
                montant=(affaire.contract_amount * Decimal("0.05")).quantize(Decimal("1")),
                numero_instrument=f"GAR-{affaire.start_date:%y}-{310 + i}", date_emission=affaire.start_date,
                date_echeance=self.today + timedelta(days=(20, 55, 85)[i % 3]) if not levee and i < 4 else ajouter_mois(affaire.end_date, 6),
                statut="levee" if levee else "en_cours",
            )
        objet = "Caution de soumission - Raccordement nouveau puits Banio Sud"
        if not Caution.objects.filter(objet=objet).exists():
            Caution.objects.create(type="bon_soumission", emetteur=banque, beneficiaire="Banio Upstream Gabon", objet=objet,
                                   montant=Decimal(13_600_000), numero_instrument="SOUM-26-118",
                                   date_emission=self.today - timedelta(days=40), date_echeance=self.today + timedelta(days=50),
                                   statut="en_cours")

    def _assurances(self, assureur):
        for i, (nature, police, prime, objets, echeance) in enumerate((
            ("rc_pro", "RCP-2026-0412", 18_500_000, "Responsabilité civile des activités de tuyauterie et soudure", 210),
            ("tous_risques", "TRC-2026-1187", 24_000_000, "Chantiers clients (sites pétroliers)", 26),
            ("flotte", "FLT-2026-0733", 9_800_000, "Véhicules légers et camions", 140),
            ("engins", "ENG-2026-0291", 12_600_000, "Grue mobile, nacelles, chariots, compresseurs", 75),
        )):
            if Assurance.objects.filter(numero_police=police).exists():
                continue
            fin = self.today + timedelta(days=echeance)
            Assurance.objects.create(type=nature, assureur=assureur, numero_police=police, prime_annuelle=Decimal(prime),
                                     date_debut=fin - timedelta(days=365), date_echeance=fin, objets_couverts=objets,
                                     statut="a_renouveler" if echeance < 60 else "active")

    def _contentieux(self):
        for objet, nature, adverse, montant, phase, statut, mois in (
            ("Retard de paiement de situations de travaux", "client", "Nyanga Energy SA", 96_000_000, "pre_contentieux", "ouvert", 2),
            ("Livraison de tubes non conformes (certificats matière)", "fournisseur", "Fournisseur de tubes (importateur)", 14_500_000, "tribunal", "en_instruction", 6),
            ("Réclamation d'un ancien sous-traitant", "fournisseur", "Sous-traitant échafaudage", 6_200_000, "pre_contentieux", "transaction", 10),
        ):
            if Contentieux.objects.filter(objet=objet).exists():
                continue
            Contentieux.objects.create(nature=nature, objet=objet, partie_adverse=adverse, montant_en_jeu=Decimal(montant),
                                       phase=phase, statut=statut, date_ouverture=ajouter_mois(self.today, -mois),
                                       juridiction="Tribunal de commerce de Port-Gentil" if phase == "tribunal" else "",
                                       probabilite="moyenne")

    def _courriers(self):
        clients = list(Partner.objects.filter(code__startswith="CLT-").order_by("code"))
        for k in range(MOIS - 1, -1, -1):
            for n, (sens, nature, objet) in enumerate((
                ("entrant", "lettre", "Ordre de service"), ("sortant", "lettre", "Transmission de situation de travaux"),
                ("entrant", "email", "Demande de prix"),
            )):
                tiers = clients[(k * 3 + n) % len(clients)]
                libelle = f"{objet} - {tiers.name} - {debut_mois(self.today, k):%m/%Y}"
                if Courrier.objects.filter(objet=libelle).exists():
                    continue
                jour = ouvre(jour_du_mois(self.today, k, 6 + 7 * n))
                c = Courrier.objects.create(
                    sens=sens, type=nature, objet=libelle, tiers=tiers, reference=f"ETSL/{jour:%y}/{400 + k * 3 + n}",
                    date_courrier=jour, date_reception=jour + timedelta(days=1) if sens == "entrant" else None,
                    statut="archive" if k >= 2 else ("enregistre" if n else "recu"),
                )
                antidater(Courrier, c.pk, created_at=instant(jour, 11))

    def _dossiers_gr(self):
        for affaire in self.affaires_vitrine.values():
            if not affaire.is_global_rental or DossierGlobalRental.objects.filter(affaire=affaire).exists():
                continue
            DossierGlobalRental.objects.create(
                partenaire_gr=self.gr, affaire=affaire, reference_contrat=affaire.code,
                objet=f"Location intra-groupe - {affaire.title}"[:250], montant_estime=affaire.contract_amount * Decimal("0.68"),
                signe_618=True, date_debut=affaire.start_date, date_fin=affaire.end_date, statut="ouvert",
                mandat_reference=f"MAND-GR-{affaire.code}", mandat_date_fin=affaire.end_date,
            )
