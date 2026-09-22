"""Tests M6 — Qualité industrielle, Soudage & Contrôle Qualité / Inspection (RF-ERP-50…53)."""

from datetime import date, timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from commercial.models import Affaire
from operations.models import OrdreFabrication
from qualite.models import (
    ActionCorrective,
    ControleQualite,
    NonConformite,
    PvControle,
    QualificationSoudeur,
    Soudeur,
    WpsWpqr,
)
from referentiels.models import Article, UnitOfMeasure
from stocks.models import Depot, LotMatiere
from users.models import User


def make_user(role=User.Role.QAQC):
    return User.objects.create_user(
        email=f"{role.lower()}@etls.ga",
        password="test1234",
        first_name=role,
        last_name="Test",
        role=role,
    )


class M6BaseTest(APITestCase):
    def setUp(self):
        self.qaqc = make_user(User.Role.QAQC)
        self.dir_op = make_user(User.Role.DIRECTEUR_OPERATIONS)
        self.rh = make_user(User.Role.RH)
        self.affaire = Affaire.objects.create(title="Chantier pipeline Line A")
        self.of = OrdreFabrication.objects.create(label="Tirage TV horizontale")
        depot = Depot.objects.create(code="DEP-Q", label="Dépôt Qualité")
        unit, _ = UnitOfMeasure.objects.get_or_create(code="U", defaults={"label": "Unité"})
        article = Article.objects.create(
            code="ART-TUY",
            label="Tube acier",
            article_type=Article.ArticleType.MATIERE,
            unit=unit,
        )
        lot = LotMatiere.objects.create(
            article=article,
            numero_lot="LOT-Q1",
            date_reception=date.today(),
            quantite_initiale=100,
            quantite_restante=100,
        )
        self.lot = lot
        self.soudeur = Soudeur.objects.create(
            nom="MBENG", prenoms="Charles", matricule="SOU-MB"
        )

    def auth(self, user=None):
        self.client.force_authenticate(user or self.qaqc)


class SequenceAndQualificationTests(M6BaseTest):
    def test_soudeur_code_sequence(self):
        s = Soudeur.objects.create(nom="NDONG")
        self.assertTrue(s.code.startswith("SOU"))

    def test_qualification_auto_code_and_statut(self):
        q = QualificationSoudeur.objects.create(
            soudeur=self.soudeur,
            norme=QualificationSoudeur.Norme.ISO_9606,
            procede=QualificationSoudeur.Procede.SMAW,
            position="6G",
            epaisseur_min=6,
            epaisseur_max=25,
            date_qualification=date.today(),
            date_validite=date.today() + timedelta(days=365),
        )
        self.assertTrue(q.code.startswith("QUAL"))
        self.assertEqual(q.statut, QualificationSoudeur.Statut.VALIDE)
        self.assertTrue(q.est_valide)

    def test_expired_qualification_invalid(self):
        q = QualificationSoudeur.objects.create(
            soudeur=self.soudeur,
            date_qualification=date.today() - timedelta(days=400),
            date_validite=date.today() - timedelta(days=20),
        )
        q.clean()
        self.assertEqual(q.statut, QualificationSoudeur.Statut.EXPIREE)
        self.assertFalse(q.est_valide)

    def test_invalid_validity_rejected(self):
        self.auth()
        resp = self.client.post(
            "/api/qualite/qualifications/",
            {
                "soudeur": str(self.soudeur.id),
                "date_qualification": "2026-09-01",
                "date_validite": "2026-08-01",
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)

    def test_qualification_list_filters(self):
        QualificationSoudeur.objects.create(
            soudeur=self.soudeur,
            date_qualification=date.today(),
            date_validite=date.today() + timedelta(days=365),
        )
        self.auth()
        resp = self.client.get("/api/qualite/qualifications/?valides=1")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)


class WpsTests(M6BaseTest):
    def test_wps_api_creation(self):
        self.auth()
        resp = self.client.post(
            "/api/qualite/wps/",
            {
                "type": WpsWpqr.Type.WPS,
                "reference": "WPS-TIG-01",
                "procede": QualificationSoudeur.Procede.GTAW,
                "materiau": "Acier carbone",
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertTrue(resp.data["code"].startswith("WPS"))

    def test_wps_validation_sets_date_and_validator(self):
        self.auth()
        resp = self.client.post(
            "/api/qualite/wps/",
            {
                "type": WpsWpqr.Type.WPS,
                "statut": WpsWpqr.Statut.VALIDE,
                "reference": "WPS-RX-01",
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        # le statut est fourni tel quel en création (create ne déclenche pas perform_update)
        wps = WpsWpqr.objects.get(pk=resp.data["id"])
        self.assertEqual(wps.statut, WpsWpqr.Statut.VALIDE)


class ControleQualiteTests(M6BaseTest):
    def test_controle_creation_with_cnd_organisme(self):
        self.auth()
        resp = self.client.post(
            "/api/qualite/controles/",
            {
                "type_controle": ControleQualite.TypeControle.CND,
                "organisme": ControleQualite.OrganismeCnd.ORGANISME_AGREE,
                "organisme_libelle": "Bureau Veritas Gabon",
                "affaire": str(self.affaire.id),
                "lot": str(self.lot.id),
                "point_controle": "Joint 4",
                "resultat": ControleQualite.Resultat.CONFORME,
                "date_controle": "2026-09-22",
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertTrue(resp.data["code"].startswith("CTR"))
        self.assertEqual(
            resp.data["organisme_label"], "Organisme agréé"
        )
        self.assertEqual(resp.data["lot_code"], self.lot.code)

    def test_rh_cannot_create_controle(self):
        self.auth(self.rh)
        resp = self.client.post("/api/qualite/controles/", {})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.content)

    def test_read_is_authenticated(self):
        ControleQualite.objects.create(
            type_controle=ControleQualite.TypeControle.VISUEL,
            affaire=self.affaire,
            created_by=self.qaqc,
        )
        self.auth(self.rh)
        resp = self.client.get("/api/qualite/controles/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)


class NonConformiteTests(M6BaseTest):
    def test_nc_flow_traiter_puis_cloturer(self):
        self.auth()
        nc_resp = self.client.post(
            "/api/qualite/non-conformites/",
            {
                "source": NonConformite.Source.CONTROLE,
                "gravite": NonConformite.Gravite.MAJEURE,
                "description": "Porosités sur joint 4",
                "traitement": NonConformite.Traitement.REPRISE,
            },
        )
        self.assertEqual(nc_resp.status_code, status.HTTP_201_CREATED, nc_resp.content)
        nc_id = nc_resp.data["id"]

        resp = self.client.post(f"/api/qualite/non-conformites/{nc_id}/traiter/", {})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        nc = NonConformite.objects.get(pk=nc_id)
        self.assertEqual(nc.statut, NonConformite.Statut.EN_TRAITEMENT)
        self.assertEqual(nc.decided_by, self.qaqc)

        capa_resp = self.client.post(
            "/api/qualite/actions-correctives/",
            {
                "non_conformite": nc_id,
                "type": ActionCorrective.TypeAction.CORRECTIVE,
                "description": "Reprise + re-contrôle",
                "echeance": "2026-10-01",
            },
        )
        self.assertEqual(capa_resp.status_code, status.HTTP_201_CREATED, capa_resp.content)
        self.assertTrue(capa_resp.data["code"].startswith("CAP"))
        capa_id = capa_resp.data["id"]

        resp = self.client.post(
            f"/api/qualite/actions-correctives/{capa_id}/cloturer/",
            {"efficace": True},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.assertEqual(resp.data["statut"], ActionCorrective.Statut.CLOTUREE)
        self.assertTrue(resp.data["efficace"])

        resp = self.client.post(f"/api/qualite/non-conformites/{nc_id}/cloturer/", {})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        nc.refresh_from_db()
        self.assertEqual(nc.statut, NonConformite.Statut.CLOTUREE)
        self.assertTrue(nc.archive)

    def test_nc_reject_archives(self):
        nc = NonConformite.objects.create(
            description="Fissure longitudinale",
            gravite=NonConformite.Gravite.CRITIQUE,
        )
        self.auth()
        resp = self.client.post(
            f"/api/qualite/non-conformites/{nc.id}/traiter/",
            {"traitement": NonConformite.Traitement.REJET},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        nc.refresh_from_db()
        self.assertEqual(nc.statut, NonConformite.Statut.CLOTUREE)
        self.assertTrue(nc.archive)

    def test_nc_invalid_traitement(self):
        nc = NonConformite.objects.create(description="Défaut de peinture")
        self.auth()
        resp = self.client.post(
            f"/api/qualite/non-conformites/{nc.id}/traiter/",
            {"traitement": "inconnu"},
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)

    def test_nc_requires_description(self):
        self.auth()
        resp = self.client.post("/api/qualite/non-conformites/", {})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)


class PvControleTests(M6BaseTest):
    def test_pv_sequence_and_creation(self):
        self.auth()
        resp = self.client.post(
            "/api/qualite/pvs/",
            {
                "intitule": "Réception interne tirage TV",
                "affaire": str(self.affaire.id),
                "date_pv": "2026-09-22",
                "retention_years": 10,
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertTrue(resp.data["code"].startswith("PV"))

    def test_levee_reserve_rf51(self):
        pv = PvControle.objects.create(
            intitule="PV tuyauterie line A",
            affaire=self.affaire,
        )
        self.auth()
        resp = self.client.post(
            f"/api/qualite/pvs/{pv.id}/levee-reserve/",
            {"reserve": True, "motif": "Contrôle CND en cours"},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        pv.refresh_from_db()
        self.assertEqual(pv.statut, PvControle.Statut.RESERVE)
        self.assertEqual(pv.resultat, ControleQualite.Resultat.RESERVE)

        resp = self.client.post(f"/api/qualite/pvs/{pv.id}/levee-reserve/", {"reserve": False})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        pv.refresh_from_db()
        self.assertEqual(pv.statut, PvControle.Statut.RECEPTIONNE)
        self.assertIsNotNone(pv.levee_reserve)
        self.assertEqual(pv.validated_by, self.qaqc)

    def test_pv_rejected_cannot_clear(self):
        pv = PvControle.objects.create(intitule="PV rejeté")
        PvControle.objects.filter(pk=pv.id).update(statut=PvControle.Statut.REJETE)
        self.auth()
        resp = self.client.post(f"/api/qualite/pvs/{pv.id}/levee-reserve/", {})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)

    def test_pv_validation_reserved_to_roles(self):
        pv = PvControle.objects.create(intitule="PV réservé")
        self.auth(self.rh)
        resp = self.client.post(f"/api/qualite/pvs/{pv.id}/levee-reserve/", {})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.content)

    def test_pv_retention_years_default(self):
        pv = PvControle.objects.create(intitule="PV archivage 10 ans")
        self.assertEqual(pv.retention_years, 10)

    def test_rh_cannot_create_pv(self):
        self.auth(self.rh)
        resp = self.client.post("/api/qualite/pvs/", {"intitule": "PV interdit RH"})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.content)


class QualiteWorkflowPermissionsTests(M6BaseTest):
    def test_qaqc_can_write_everything(self):
        self.auth(self.qaqc)
        resp = self.client.post("/api/qualite/soudeurs/", {"nom": "OBIANG", "prenoms": "Sylvie"})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

    def test_ops_direction_can_write(self):
        self.auth(self.dir_op)
        resp = self.client.post("/api/qualite/soudeurs/", {"nom": "NTCH", "prenoms": "Paul"})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)