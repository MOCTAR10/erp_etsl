"""Écarts M9-C : plan de formation (catalogue, budget, coût, ROI, qualification délivrée), matrice habilitation ↔
poste, synchronisation des qualifications soudeur M6 → RH, signature des bulletins, absentéisme paramétré, alerte de
dépassement de main-d'œuvre vers M3."""

from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from documents.models import SignatureRequest
from operations.cloture import transferer_paie
from operations.models import GammeOperation, GammeOperatoire, OrdreFabrication, PointageChantier
from qualite.models import QualificationSoudeur, Soudeur
from workflow.models import Notification

from .models import (
    Absence, BulletinPaie, CatalogueFormation, ContratTravail, Formation, HabilitationPoste, ParametrePaie,
    PlanFormation, Qualification,
)
from .paie_m9a import preparer_bulletin
from .services import reporting_rh
from .tests import BASE, BaseRHTest, _auth

AUJ = timezone.localdate()


class PlanFormationTests(BaseRHTest):
    def setUp(self):
        super().setUp()
        _auth(self.client, "rh@etls.local")
        self.cat = CatalogueFormation.objects.create(
            intitule="Travaux en hauteur", organisme="APAVE", duree_heures=Decimal("14"),
            cout_session=Decimal("300000"), qualification_type="habilitation", validite_mois=36,
        )
        self.plan = PlanFormation.objects.create(annee=AUJ.year, budget=Decimal("500000"))

    def session(self, **kw):
        body = {"catalogue": str(self.cat.pk), "plan": str(self.plan.pk), "date_session": str(AUJ)}
        body.update(kw)
        return self.client.post(f"{BASE}formations/", body, format="json")

    def test_session_reprend_le_catalogue(self):
        r = self.session()
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["theme"], "Travaux en hauteur")
        self.assertEqual(Decimal(r.data["cout_prevu"]), Decimal("300000"))
        self.assertEqual(Decimal(r.data["duree_heures"]), Decimal("14"))

    def test_budget_du_plan_bloque_le_depassement(self):
        self.assertEqual(self.session().status_code, 201)
        r = self.session()
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("Budget", str(r.data))

    def test_realisation_delivre_la_qualification_et_calcule_le_roi(self):
        fid = self.session().data["id"]
        self.assertEqual(self.client.post(f"{BASE}formations/{fid}/inscrire/", {"employe": str(self.employe.pk)}, format="json").status_code, 200)
        r = self.client.post(f"{BASE}formations/{fid}/realiser/", {"cout_reel": "250000", "gain_estime": "400000", "note_evaluation": "15"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["roi_pct"], "60.00")
        self.assertEqual(r.data["nb_qualifications_delivrees"], 1)
        q = Qualification.objects.get(employe=self.employe, source="formation")
        self.assertEqual(q.type, "habilitation")
        self.assertEqual((q.date_validite.year, q.date_validite.month), (AUJ.year + 3, AUJ.month))
        synthese = self.client.get(f"{BASE}plans-formation/{self.plan.pk}/").data["synthese"]
        self.assertEqual(synthese["realise"], "250000.00")
        self.assertEqual(synthese["reste"], "250000.00")
        self.assertEqual(synthese["heures_stagiaires"], "14.00")
        self.assertEqual(synthese["roi_pct"], "60.00")
        self.assertEqual(synthese["taux_realisation_pct"], "100.00")

    def test_inscription_refusee_sur_session_realisee(self):
        fid = self.session().data["id"]
        self.client.post(f"{BASE}formations/{fid}/realiser/", {}, format="json")
        r = self.client.post(f"{BASE}formations/{fid}/inscrire/", {"employe": str(self.employe.pk)}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_theme_obligatoire_sans_catalogue(self):
        r = self.client.post(f"{BASE}formations/", {"date_session": str(AUJ)}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_catalogue_et_plan_crees_a_l_ecran(self):
        r = self.client.post(f"{BASE}catalogue-formations/", {"intitule": "SST", "cout_session": "100000"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.data["code"].startswith("CAT"))
        r = self.client.post(f"{BASE}plans-formation/", {"annee": AUJ.year + 1, "budget": "1000000"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(self.client.post(f"{BASE}plans-formation/", {"annee": 1900}, format="json").status_code, 400)


class SyncSoudeurTests(BaseRHTest):
    def test_qualification_soudeur_recopiee_puis_suspendue(self):
        soudeur = Soudeur.objects.create(nom="MBENG", employe=self.employe)
        qs = QualificationSoudeur.objects.create(
            soudeur=soudeur, procede="gtaw", position="6G", date_qualification=AUJ - timedelta(days=10),
            date_validite=AUJ + timedelta(days=300),
        )
        q = Qualification.objects.get(source="m6", source_ref=str(qs.pk))
        self.assertEqual(q.employe, self.employe)
        self.assertIn("6G", q.intitule)
        self.assertFalse(q.expiree)
        qs.statut = "suspendue"
        qs.save()
        q.refresh_from_db()
        self.assertTrue(q.expiree)
        qs.delete()
        self.assertFalse(Qualification.objects.filter(source="m6").exists())

    def test_soudeur_rattache_apres_coup(self):
        soudeur = Soudeur.objects.create(nom="NZE")
        QualificationSoudeur.objects.create(soudeur=soudeur, date_qualification=AUJ, date_validite=AUJ + timedelta(days=30))
        self.assertFalse(Qualification.objects.filter(source="m6").exists())
        soudeur.employe = self.employe
        soudeur.save()
        self.assertEqual(Qualification.objects.filter(source="m6", employe=self.employe).count(), 1)


class MatriceHabilitationTests(BaseRHTest):
    def setUp(self):
        super().setUp()
        self.employe.user = self.ouvrier
        self.employe.save()
        g = GammeOperatoire.objects.create(label="Spool")
        GammeOperation.objects.create(gamme=g, sequence=1, label="Soudure", poste="soudure", planned_hours=Decimal("10"))
        self.of = OrdreFabrication.objects.create(label="Chantier", scope="chantier", gamme=g)
        Qualification.objects.create(employe=self.employe, type="habilitation", intitule="Travaux en hauteur",
                                     date_validite=AUJ + timedelta(days=100))

    def pointer(self):
        _auth(self.client, "admin@etls.local")
        return self.client.post("/api/operations/pointages/", {
            "ordre": str(self.of.pk), "date": str(AUJ), "hours": "8", "worker": str(self.ouvrier.pk),
        }, format="json")

    def test_poste_exige_une_habilitation_precise(self):
        _auth(self.client, "rh@etls.local")
        r = self.client.post(f"{BASE}habilitations-postes/", {"poste": "soudure", "mot_cle": " soudeur "}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        r = self.pointer()
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("soudeur", str(r.data))
        Qualification.objects.create(employe=self.employe, type="certificat", intitule="Soudeur ISO 9606-1",
                                     date_validite=AUJ + timedelta(days=100))
        self.assertEqual(self.pointer().status_code, 201)

    def test_sans_exigence_pour_le_poste_regle_generale(self):
        HabilitationPoste.objects.create(poste="montage", mot_cle="élingage")
        self.assertEqual(self.pointer().status_code, 201)


class SignatureBulletinTests(BaseRHTest):
    def test_bulletin_soumis_a_signature_avancee(self):
        ContratTravail.objects.create(employe=self.employe, type="cdi", date_debut=date(2025, 1, 1), salaire_base=Decimal("300000"))
        b = BulletinPaie.objects.create(employe=self.employe, periode=date(2026, 3, 1))
        preparer_bulletin(b)
        BulletinPaie.objects.filter(pk=b.pk).update(statut="valide")
        _auth(self.client, "rh@etls.local")
        r = self.client.post(f"{BASE}bulletins/{b.pk}/signer/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["signature_statut"], "pending")
        req = SignatureRequest.objects.get()
        self.assertEqual(req.signers.get().user, self.rh)
        self.assertEqual(req.document_sha256, req.version.sha256)
        self.assertEqual(self.client.post(f"{BASE}bulletins/{b.pk}/signer/", {}, format="json").status_code, 400)

    def test_brouillon_refuse(self):
        b = BulletinPaie.objects.create(employe=self.employe, periode=date(2026, 3, 1))
        _auth(self.client, "rh@etls.local")
        self.assertEqual(self.client.post(f"{BASE}bulletins/{b.pk}/signer/", {}, format="json").status_code, 400)


class AbsenteismeTests(BaseRHTest):
    def test_absences_comptees_et_base_parametree(self):
        self.employe.date_embauche = date(2025, 1, 1)
        self.employe.save()
        Absence.objects.create(employe=self.employe, type="injustifiee", date_debut=date(2026, 3, 2), date_fin=date(2026, 3, 4), statut="validee")
        Absence.objects.create(employe=self.employe, type="maladie", date_debut=date(2026, 3, 9), date_fin=date(2026, 3, 9))
        d = reporting_rh(2026)
        self.assertEqual(d["jours_absence"], 3)
        self.assertTrue(d["jours_ouvres_provisoire"])
        ParametrePaie.objects.create(code="JOURS_OUVRES_AN", label="j", valeur=Decimal("200"), date_effet=date(2020, 1, 1))
        d = reporting_rh(2026)
        self.assertEqual(Decimal(d["jours_ouvres_an"]), Decimal("200"))


class AlerteMainOeuvreTests(BaseRHTest):
    def test_depassement_notifie_une_seule_fois(self):
        self.employe.user = self.ouvrier
        self.employe.save()
        of = OrdreFabrication.objects.create(label="Atelier", calculated_hours=Decimal("10"), responsible=self.admin)

        def pointer(h):
            p = PointageChantier.objects.create(ordre=of, worker=self.ouvrier, date=AUJ, hours=Decimal(h), status="valide")
            transferer_paie(p)

        pointer("8")
        self.assertFalse(Notification.objects.filter(user=self.admin).exists())
        pointer("4")
        pointer("4")
        self.assertEqual(Notification.objects.filter(user=self.admin, subject__contains="main-d").count(), 1)
        of.refresh_from_db()
        self.assertIsNotNone(of.alerte_mo_le)
