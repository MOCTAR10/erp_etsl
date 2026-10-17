"""Clôture M1 Commercial (2026-10-17) — tests de recette des critères CDC (cahier détaillé §3.4 à §3.11).

1. Offres versionnées : cycle par actions (soumettre / réviser / gagner / perdre), offre émise scellée, révision =
   nouvelle version (options et lignes copiées), l'ancienne passe « remplacée ».
2. Contrats : activation uniquement avec le contrat **signé électroniquement** (signature avancée CL-OM-06) et
   **archivé 10 ans** (type GED) ; contrat actif scellé, toute modification passe par un **avenant** signé
   (versioning contractuel) qui ajuste montant et échéance.
3. Affaire : responsable d'affaire, compte analytique créé à la confirmation, démarrage exigeant le **CRRL**
   (compte-rendu de réunion de lancement tenu, document en GED).
4. Pilotage : marges prévues et réelles par client, profil, affaire, responsable (montants masqués hors rôles) ;
   **pipe pondéré 90/60/25** publié vers M11 / Couche D ; jalons atteints exposés « à facturer » pour M10.
"""

import hashlib
from datetime import date, timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting_kernel.models import AccountMove, AccountMoveLine, Journal, Period
from accounting_kernel.services import post_move
from documents.models import Document, DocumentType, SignatureRequest, Version
from juridique.models import Reunion
from referentiels.models import Account, Currency, Partner
from users.models import User

from .models import Affaire, ClientProfile, Contract, Estimate, EstimateOption, Milestone, Opportunity, RevueCommande

PWD = "x-Audit-2026"


def creer(email, role):
    return User.objects.create_user(email=email, password=PWD, role=role, first_name=email[:4])


class BaseM1(APITestCase):
    def setUp(self):
        self.dp = creer("dp@etls.ga", User.Role.DIRECTEUR_PROJETS)
        self.dg = creer("dg@etls.ga", User.Role.PDG)
        self.sg = creer("sg@etls.ga", User.Role.SECRETAIRE_GENERAL)  # lit le commercial, sans les montants
        self.client.force_authenticate(self.dp)
        self.xaf, _ = Currency.objects.get_or_create(code="XAF")
        self.cli = self.client_profile("TOTAL-GA", "Total Gabon")

    def client_profile(self, code, nom):
        partner = Partner.objects.create(code=code, name=nom, kind=Partner.Kind.CLIENT)
        return ClientProfile.objects.create(partner=partner, segment="petrole_gaz")

    def document_signe(self, retention=10, signe=True):
        type_doc, _ = DocumentType.objects.get_or_create(code=f"contrats-{retention}", defaults={"label": "Contrats", "retention_years": retention})
        doc = Document.objects.create(title="Contrat signé", status=Document.Status.DRAFT, type=type_doc)
        contenu = b"contrat"
        version = Version.objects.create(document=doc, number=1, file=SimpleUploadedFile("c.pdf", contenu),
                                         sha256=hashlib.sha256(contenu).hexdigest(), size=7, original_filename="c.pdf", created_by=self.dp)
        doc.current_version = version
        doc.save(update_fields=["current_version"])
        SignatureRequest.objects.create(
            version=version, document_sha256=version.sha256, created_by=self.dp,
            status=SignatureRequest.Status.COMPLETED if signe else SignatureRequest.Status.PENDING,
            expires_at=timezone.now() + timedelta(days=5), completed_at=timezone.now() if signe else None,
        )
        return doc


class OffresVersionneesTests(BaseM1):
    def offre(self):
        r = self.client.post("/api/commercial/estimates/", {"title": "Spools line B", "client": str(self.cli.pk), "currency": self.xaf.pk}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        offre = Estimate.objects.get(pk=r.data["id"])
        EstimateOption.objects.create(estimate=offre, label="Option A", amount=Decimal("120000000"))
        return offre

    def act(self, offre, action, body=None):
        return self.client.post(f"/api/commercial/estimates/{offre.pk}/{action}/", body or {}, format="json")

    def test_statut_non_modifiable_par_patch(self):
        offre = self.offre()
        self.client.patch(f"/api/commercial/estimates/{offre.pk}/", {"status": "gagnee"}, format="json")
        offre.refresh_from_db()
        self.assertEqual(offre.status, Estimate.Status.BROUILLON)

    def test_offre_vide_non_soumissible(self):
        r = self.client.post("/api/commercial/estimates/", {"title": "Vide", "client": str(self.cli.pk)}, format="json")
        self.assertEqual(self.client.post(f"/api/commercial/estimates/{r.data['id']}/soumettre/").status_code, 400)

    def test_revision_cree_une_nouvelle_version_et_scelle_l_ancienne(self):
        v1 = self.offre()
        self.assertEqual(self.act(v1, "soumettre").status_code, 200)
        r = self.client.patch(f"/api/commercial/estimates/{v1.pk}/", {"title": "Réécrite"}, format="json")
        self.assertEqual(r.status_code, 400, r.content)  # offre émise : scellée
        r = self.act(v1, "reviser")
        self.assertEqual(r.status_code, 201, r.content)
        v2 = Estimate.objects.get(pk=r.data["id"])
        v1.refresh_from_db()
        self.assertEqual((v2.version, v2.version_precedente_id, v2.status), (2, v1.pk, Estimate.Status.BROUILLON))
        self.assertEqual(v1.status, Estimate.Status.REMPLACEE)
        self.assertEqual(v2.options.count(), 1)
        self.assertEqual(self.act(v2, "soumettre").status_code, 200)
        self.assertEqual(self.act(v2, "gagner").data["status"], Estimate.Status.GAGNEE)

    def test_perte_motivee(self):
        offre = self.offre()
        self.act(offre, "soumettre")
        self.assertEqual(self.act(offre, "perdre").status_code, 400)
        self.assertEqual(self.act(offre, "perdre", {"motif": "Prix"}).data["status"], Estimate.Status.PERDUE)


class ContratsSignesEtAvenantsTests(BaseM1):
    def contrat(self, **kw):
        data = {"client": self.cli, "profile": "maintenance", "start_date": date.today(), "end_date": date.today() + timedelta(days=730),
                "months": 24, "amount_initial": Decimal("100000000"), "currency": self.xaf}
        data.update(kw)
        return Contract.objects.create(**data)

    def test_statut_non_modifiable_par_patch(self):
        c = self.contrat()
        self.client.patch(f"/api/commercial/contracts/{c.pk}/", {"status": "actif"}, format="json")
        c.refresh_from_db()
        self.assertEqual(c.status, Contract.Status.BROUILLON)

    def test_activation_exige_un_contrat_signe_et_archive_10_ans(self):
        c = self.contrat()
        url = f"/api/commercial/contracts/{c.pk}/activer/"
        r = self.client.post(url, {}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("sign", str(r.data).lower())
        for doc, motif in ((self.document_signe(signe=False), "sign"), (self.document_signe(retention=5), "10 ans")):
            r = self.client.post(url, {"document": str(doc.pk)}, format="json")
            self.assertEqual(r.status_code, 400, r.content)
            self.assertIn(motif, str(r.data).lower())
        r = self.client.post(url, {"document": str(self.document_signe().pk)}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["status"], Contract.Status.ACTIF)
        self.assertIsNotNone(r.data["signe_le"])

    def test_contrat_actif_modifie_uniquement_par_avenant_signe(self):
        c = self.contrat()
        self.client.post(f"/api/commercial/contracts/{c.pk}/activer/", {"document": str(self.document_signe().pk)}, format="json")
        r = self.client.patch(f"/api/commercial/contracts/{c.pk}/", {"amount_initial": "1"}, format="json")
        self.assertEqual(r.status_code, 400, r.content)
        fin = date.today() + timedelta(days=1095)
        r = self.client.post("/api/commercial/avenants/", {"contract": str(c.pk), "objet": "Extension périmètre pipelines",
                                                           "delta_montant": "15000000", "nouvelle_date_fin": str(fin)}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["numero"], 1)
        avenant = r.data["id"]
        self.assertEqual(self.client.post(f"/api/commercial/avenants/{avenant}/signer/", {}, format="json").status_code, 400)
        r = self.client.post(f"/api/commercial/avenants/{avenant}/signer/", {"document": str(self.document_signe().pk)}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        c.refresh_from_db()
        self.assertEqual((c.montant_actuel, c.end_date), (Decimal("115000000"), fin))
        r = self.client.patch(f"/api/commercial/avenants/{avenant}/", {"objet": "Réécrit"}, format="json")
        self.assertEqual(r.status_code, 400, r.content)  # avenant signé : scellé
        r = self.client.post("/api/commercial/avenants/", {"contract": str(c.pk), "objet": "Indexation 2027", "delta_montant": "2000000"}, format="json")
        self.assertEqual(r.data["numero"], 2)


class AffaireTests(BaseM1):
    def affaire(self):
        opp = Opportunity.objects.create(subject="Pipelines B", client=self.cli, stage="gagne", amount=Decimal("100000000"), owner=self.dg)
        r = self.client.post("/api/commercial/affaires/", {"title": "Pipelines B", "opportunity": str(opp.pk), "client": str(self.cli.pk),
                                                          "affaire_type": "chantier"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return Affaire.objects.get(pk=r.data["id"])

    def confirmer(self, affaire):
        RevueCommande.objects.create(affaire=affaire, montant_offre=Decimal("100"), montant_commande=Decimal("101"), delai_offre_jours=90,
                                     delai_commande_jours=90, statut=RevueCommande.Statut.VALIDEE)
        return self.client.post(f"/api/commercial/affaires/{affaire.pk}/confirmer/")

    def test_responsable_par_defaut_et_compte_analytique_a_la_confirmation(self):
        affaire = self.affaire()
        self.assertEqual(affaire.responsable, self.dg)  # porteur de l'opportunité
        self.assertEqual(self.confirmer(affaire).status_code, 200)
        affaire.refresh_from_db()
        self.assertEqual((affaire.analytic.code, affaire.analytic.axis.axis_type), (affaire.code, "projet"))

    def test_demarrage_exige_le_crrl(self):
        affaire = self.affaire()
        self.confirmer(affaire)
        url = f"/api/commercial/affaires/{affaire.pk}/demarrer/"
        r = self.client.post(url)
        self.assertEqual(r.status_code, 400)
        self.assertIn("crrl", str(r.data).lower())
        reunion = Reunion.objects.create(type="lancement", objet="Lancement Pipelines B", date_reunion=timezone.now(),
                                         affaire=affaire, statut=Reunion.Statut.TENUE)
        self.assertEqual(self.client.post(url).status_code, 400)  # compte rendu non archivé
        reunion.compte_rendu = self.document_signe()
        reunion.save()
        self.assertEqual(self.client.post(url).status_code, 200)


class PilotageTests(BaseM1):
    def setUp(self):
        super().setUp()
        call_command("seed_accounting", year=date.today().year)
        self.a701, _ = Account.objects.get_or_create(code="701000", defaults={"label": "Ventes", "account_class": 7, "account_type": Account.AccountType.INCOME})
        self.a601, _ = Account.objects.get_or_create(code="601000", defaults={"label": "Achats", "account_class": 6, "account_type": Account.AccountType.EXPENSE})
        self.a512, _ = Account.objects.get_or_create(code="512000", defaults={"label": "Banque", "account_class": 5, "account_type": Account.AccountType.ASSET})

    def affaire_confirmee(self, client, responsable, montant):
        affaire = Affaire.objects.create(title=f"Affaire {montant}", client=client, affaire_type="chantier", responsable=responsable,
                                         contract_amount=Decimal(montant), margin=Decimal(montant) / 5, currency=self.xaf)
        affaire.assurer_compte_analytique()
        return affaire

    def ecriture(self, affaire, compte, debit=0, credit=0):
        move = AccountMove.objects.create(journal=Journal.objects.get(code="OD"), period=Period.objects.filter(fiscal_year__year=date.today().year).first(),
                                          date=Period.objects.filter(fiscal_year__year=date.today().year).first().start_date, reference=f"R{AccountMove.objects.count()}", source="M10")
        AccountMoveLine.objects.create(move=move, account=compte, debit=Decimal(debit), credit=Decimal(credit), analytic_account=affaire.analytic, order=1)
        AccountMoveLine.objects.create(move=move, account=self.a512, debit=Decimal(credit), credit=Decimal(debit), order=2)
        post_move(move, user=self.dg)

    def test_marges_par_client_et_par_responsable(self):
        autre = self.client_profile("PERENCO", "Perenco")
        a1 = self.affaire_confirmee(self.cli, self.dp, "100000000")
        a2 = self.affaire_confirmee(self.cli, self.dg, "50000000")
        a3 = self.affaire_confirmee(autre, self.dp, "10000000")
        self.ecriture(a1, self.a701, credit=40000000)
        self.ecriture(a1, self.a601, debit=25000000)
        self.ecriture(a2, self.a701, credit=10000000)
        self.ecriture(a3, self.a601, debit=1000000)
        r = self.client.get("/api/commercial/affaires/marges/", {"par": "client"})
        self.assertEqual(r.status_code, 200, r.content)
        total = {row["cle"]: row for row in r.data["lignes"]}["Total Gabon"]
        self.assertEqual((total["affaires"], total["ca_prevu"], total["produits"], total["charges"], total["marge_reelle"]),
                         (2, "150000000.00", "50000000.00", "25000000.00", "25000000.00"))
        par_resp = {row["cle"]: row for row in self.client.get("/api/commercial/affaires/marges/", {"par": "responsable"}).data["lignes"]}
        self.assertEqual(par_resp[self.dp.email]["marge_reelle"], "14000000.00")
        self.client.force_authenticate(self.sg)
        r = self.client.get("/api/commercial/affaires/marges/", {"par": "client"})
        self.assertIsNone(r.data["lignes"][0]["marge_reelle"])
        self.assertEqual(self.client.get("/api/commercial/affaires/marges/", {"par": "zzz"}).status_code, 400)

    def test_pipe_pondere_90_60_25(self):
        for stage in ("gagne", "offre", "prospection", "perdu"):
            Opportunity.objects.create(subject=stage, client=self.cli, stage=stage, amount=Decimal("1000000"))
        pipe = self.client.get("/api/commercial/opportunities/pipeline/").data["pipe_pondere"]
        self.assertEqual((pipe["signe"], pipe["en_cours"], pipe["prospect"], pipe["total"]), (900000.0, 600000.0, 250000.0, 1750000.0))
        self.client.force_authenticate(self.dg)
        self.assertEqual(self.client.get("/api/analytics/dashboard/").data["commercial"]["pipe_pondere"], 1750000.0)

    def test_jalons_atteints_a_facturer(self):
        affaire = self.affaire_confirmee(self.cli, self.dp, "100000000")
        fait = Milestone.objects.create(affaire=affaire, label="Préfabrication 50 %", planned_date=date.today(), actual_date=date.today(), montant=Decimal("30000000"))
        Milestone.objects.create(affaire=affaire, label="Montage", planned_date=date.today() + timedelta(days=30), montant=Decimal("40000000"))
        r = self.client.get("/api/commercial/milestones/a-facturer/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual([j["id"] for j in r.data], [str(fait.pk)])
