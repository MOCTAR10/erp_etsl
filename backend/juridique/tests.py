"""Tests M12 — Module Juridique & GED (RF-ERP-B0...B4)."""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from referentiels.models import Partner
from users.models import User

from .models import (
    Assurance,
    Caution,
    Contentieux,
    Convention,
    Courrier,
    DossierGlobalRental,
    JuridiqueSequence,
    Reunion,
)
from .services import compute_alertes, compute_stats

User = get_user_model()

BASE = "/api/juridique/"


def _auth(client, email):
    r = client.post(
        "/api/users/token/", {"email": email, "password": "Etls#Demo2026"}, format="json"
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")


class BaseJuridiqueTest(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@etls.local", password="Etls#Demo2026",
            role=User.Role.ADMIN, first_name="Admin", is_staff=True,
        )
        self.secretariat = User.objects.create_user(
            email="sg@etls.local", password="Etls#Demo2026",
            role=User.Role.SECRETAIRE_GENERAL, first_name="SG",
        )
        self.finance = User.objects.create_user(
            email="finance@etls.local", password="Etls#Demo2026",
            role=User.Role.FINANCE, first_name="Finance",
        )
        self.logistique = User.objects.create_user(
            email="logi@etls.local", password="Etls#Demo2026",
            role=User.Role.LOGISTIQUE, first_name="Logi",
        )
        self.gr = Partner.objects.create(
            code="GR-X", name="GLOBAL RENTAL", kind=Partner.Kind.FOURNISSEUR,
            is_global_rental=True,
        )
        self.banque = Partner.objects.create(
            code="BQ-X", name="BGFI", kind=Partner.Kind.FOURNISSEUR,
        )

    def _courrier(self, statut=Courrier.Statut.RECU):
        return Courrier.objects.create(
            sens="entrant", type="lettre", objet="Objet courrier",
            tiers=self.gr, statut=statut,
        )

    def _convention(self, date_fin=None, statut=Convention.Statut.SIGNE):
        return Convention.objects.create(
            type="maintenance", titre="Convention test",
            partenaire=self.gr, montant=Decimal("1000000"),
            date_debut=date(2026, 1, 1),
            date_fin=date_fin or (date.today() + timedelta(days=80)),
            statut=statut,
        )

    def _contentieux(self, statut=Contentieux.Statut.OUVERT):
        return Contentieux.objects.create(
            nature="commercial", objet="Litige test", partie_adverse="STE X",
            montant_en_jeu=Decimal("500000"), statut=statut,
        )

    def _caution(self, date_echeance=None, statut=Caution.Statut.EN_COURS):
        return Caution.objects.create(
            type="bonne_execution", emetteur=self.banque, beneficiaire="CLIENT",
            objet="Garantie test", montant=Decimal("750000"),
            date_emission=date(2026, 1, 1),
            date_echeance=date_echeance or (date.today() + timedelta(days=45)),
            statut=statut,
        )

    def _assurance(self, date_echeance=None, statut=Assurance.Statut.ACTIVE):
        return Assurance.objects.create(
            type="rc_pro", assureur=self.banque, numero_police="POL-1",
            prime_annuelle=Decimal("300000"),
            date_debut=date(2026, 1, 1),
            date_echeance=date_echeance or (date.today() + timedelta(days=20)),
            statut=statut,
        )

    def _reunion(self, statut=Reunion.Statut.PLANIFIEE):
        return Reunion.objects.create(
            type="comite_direction", objet="Point comite",
            date_reunion=timezone.now(), statut=statut,
        )

    def _dossier_gr(self, statut=DossierGlobalRental.Statut.OUVERT):
        return DossierGlobalRental.objects.create(
            partenaire_gr=self.gr, objet="Location engins", signe_618=True,
            montant_estime=Decimal("2000000"),
            date_debut=date(2026, 1, 1), date_fin=date(2026, 12, 31), statut=statut,
        )


class CourrierTests(BaseJuridiqueTest):
    def test_create_courrier_auto_code(self):
        _auth(self.client, "sg@etls.local")
        resp = self.client.post(
            f"{BASE}courriers/",
            {"sens": "entrant", "type": "lettre", "objet": "Demande client",
             "tiers": self.gr.pk, "date_courrier": "2026-01-10"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertTrue(resp.data["code"].startswith("COU"))

    def test_workflow_bureau_ordre(self):
        courrier = self._courrier()
        _auth(self.client, "sg@etls.local")
        resp = self.client.post(f"{BASE}courriers/{courrier.pk}/enregistrer/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        courrier.refresh_from_db()
        self.assertEqual(courrier.statut, Courrier.Statut.ENREGISTRE)

    def test_archiver_require_enregistre(self):
        courrier = self._courrier()
        _auth(self.client, "sg@etls.local")
        resp = self.client.post(f"{BASE}courriers/{courrier.pk}/archiver/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_logistique_cannot_write(self):
        _auth(self.client, "logi@etls.local")
        resp = self.client.post(
            f"{BASE}courriers/",
            {"sens": "entrant", "type": "lettre", "objet": "x", "date_courrier": "2026-01-10"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class ConventionTests(BaseJuridiqueTest):
    def test_create_convention(self):
        _auth(self.client, "sg@etls.local")
        resp = self.client.post(
            f"{BASE}conventions/",
            {"type": "maintenance", "titre": "Contrat", "partenaire": self.gr.pk,
             "montant": "1000000", "date_debut": "2026-01-01", "date_fin": "2026-12-31"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data["expiry_status"], "en_cours")

    def test_montant_masque_pour_logistique(self):
        conv = self._convention()
        _auth(self.client, "logi@etls.local")
        resp = self.client.get(f"{BASE}conventions/{conv.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNone(resp.data["montant"])
        self.assertFalse(resp.data["has_amount_access"])

    def test_montant_visible_finance(self):
        conv = self._convention()
        _auth(self.client, "finance@etls.local")
        resp = self.client.get(f"{BASE}conventions/{conv.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(resp.data["montant"]), Decimal("1000000"))
        self.assertTrue(resp.data["has_amount_access"])

    def test_signer_reserve_cercle_restreint(self):
        conv = self._convention(statut=Convention.Statut.BROUILLON)
        _auth(self.client, "sg@etls.local")  # SG = cercle autorisé
        resp = self.client.post(f"{BASE}conventions/{conv.pk}/signer/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        conv.refresh_from_db()
        self.assertEqual(conv.statut, Convention.Statut.SIGNE)

    def test_cloturer_convention(self):
        conv = self._convention()
        _auth(self.client, "finance@etls.local")
        resp = self.client.post(f"{BASE}conventions/{conv.pk}/cloturer/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        conv.refresh_from_db()
        self.assertEqual(conv.statut, Convention.Statut.CLOTURE)


class ContentieuxTests(BaseJuridiqueTest):
    def test_cycle_open_to_closed(self):
        c = self._contentieux()
        _auth(self.client, "sg@etls.local")
        resp = self.client.post(f"{BASE}contentieux/{c.pk}/instruire/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        resp = self.client.post(
            f"{BASE}contentieux/{c.pk}/cloturer/",
            {"issue": "transaction", "decision": "Accord amiable"}, format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        c.refresh_from_db()
        self.assertEqual(c.statut, Contentieux.Statut.TRANSACTION)
        self.assertEqual(c.decision, "Accord amiable")

    def test_cloturer_issue_invalide(self):
        c = self._contentieux()
        _auth(self.client, "sg@etls.local")
        resp = self.client.post(
            f"{BASE}contentieux/{c.pk}/cloturer/", {"issue": "brouille"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_montant_enjeu_masque(self):
        c = self._contentieux()
        _auth(self.client, "logi@etls.local")
        resp = self.client.get(f"{BASE}contentieux/{c.pk}/")
        self.assertIsNone(resp.data["montant_en_jeu"])


class CautionTests(BaseJuridiqueTest):
    def test_lever_caution(self):
        caution = self._caution()
        _auth(self.client, "finance@etls.local")
        resp = self.client.post(f"{BASE}cautions/{caution.pk}/lever/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        caution.refresh_from_db()
        self.assertEqual(caution.statut, Caution.Statut.LEVEE)

    def test_appeler_caution_exige_en_cours(self):
        caution = self._caution(statut=Caution.Statut.LEVEE)
        _auth(self.client, "finance@etls.local")
        resp = self.client.post(f"{BASE}cautions/{caution.pk}/appeler/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_expiry_status_bands(self):
        self.assertEqual(self._caution(date_echeance=date.today() + timedelta(days=25)).expiry_status, "j30")
        self.assertEqual(self._caution(date_echeance=date.today() + timedelta(days=55)).expiry_status, "j60")
        self.assertEqual(self._caution(date_echeance=date.today() + timedelta(days=85)).expiry_status, "j90")


class AssuranceTests(BaseJuridiqueTest):
    def test_renouveler_assurance(self):
        a = self._assurance()
        _auth(self.client, "sg@etls.local")
        resp = self.client.post(
            f"{BASE}assurances/{a.pk}/renouveler/",
            {"date_echeance": str(date.today() + timedelta(days=365))}, format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        a.refresh_from_db()
        self.assertEqual(a.statut, Assurance.Statut.ACTIVE)

    def test_declarer_sinistre(self):
        a = self._assurance()
        _auth(self.client, "sg@etls.local")
        resp = self.client.post(
            f"{BASE}assurances/{a.pk}/declarer-sinistre/",
            {"detail": "Degats chantier"}, format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        a.refresh_from_db()
        self.assertEqual(a.nb_sinistres, 1)
        self.assertEqual(a.sinistres[0]["detail"], "Degats chantier")


class DossierGlobalRentalTests(BaseJuridiqueTest):
    def test_create_dossier_gr_avec_partenaire_non_gr_rejete(self):
        _auth(self.client, "sg@etls.local")
        normal = Partner.objects.create(code="NORM-1", name="Normal", kind=Partner.Kind.FOURNISSEUR)
        resp = self.client.post(
            f"{BASE}dossiers-gr/",
            {"partenaire_gr": normal.pk, "objet": "X", "date_debut": "2026-01-01",
             "date_fin": "2026-12-31"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)

    def test_ouvrir_cloturer(self):
        d = self._dossier_gr(statut=DossierGlobalRental.Statut.BROUILLON)
        _auth(self.client, "sg@etls.local")
        resp = self.client.post(f"{BASE}dossiers-gr/{d.pk}/ouvrir/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        d.refresh_from_db()
        self.assertEqual(d.statut, DossierGlobalRental.Statut.OUVERT)
        resp = self.client.post(f"{BASE}dossiers-gr/{d.pk}/cloturer/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)


class ReunionTests(BaseJuridiqueTest):
    def test_stats_reunions(self):
        self._reunion()
        _auth(self.client, "sg@etls.local")
        resp = self.client.get(f"{BASE}reunions/stats/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(resp.data["reunions_planifiees"], 1)

    def test_tenir_reunion(self):
        r = self._reunion()
        _auth(self.client, "sg@etls.local")
        resp = self.client.post(f"{BASE}reunions/{r.pk}/tenir/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        r.refresh_from_db()
        self.assertEqual(r.statut, Reunion.Statut.TENUE)


class SequenceSyncRegressionTests(BaseJuridiqueTest):
    """Régression Schemathesis : les seeds créent des codes explicites
    (COU00001…) sans avancer les compteurs → le prochain POST API régénère un
    code déjà pris (UniqueViolation 500). `_sync_sequences` réaligne le compteur."""

    def test_sync_repair_drift_so_next_post_creates(self):
        # Simule la dérive : 2 courriers seedés avec codes explicites, compteur à 1.
        self._courrier()
        self._courrier()
        JuridiqueSequence.objects.filter(kind="COU").update(next_number=1)
        c1 = Courrier.objects.filter(code__startswith="COU").first()
        c2 = Courrier.objects.exclude(pk=c1.pk).filter(code__startswith="COU").first()
        self.assertNotEqual(c1.code, c2.code)

        from users.management.commands.seed_all_demo import _sync_sequences

        synced = _sync_sequences()

        seq = JuridiqueSequence.objects.get(kind="COU")
        self.assertGreater(seq.next_number, 1)
        self.assertGreaterEqual(synced, 1)

        # Le prochain code servi ne colle plus avec un code existant → POST API OK.
        code = JuridiqueSequence.next_for("COU", "COU")
        self.assertFalse(
            Courrier.objects.filter(code=code).exists(),
            f"code {code} déjà pris : le POST API échouerait en 500",
        )

    def test_sync_left_counters_untouched_when_no_drift(self):
        from users.management.commands.seed_all_demo import _sync_sequences

        before = list(
            JuridiqueSequence.objects.values_list("kind", "next_number")
        )
        synced = _sync_sequences()
        after = list(
            JuridiqueSequence.objects.values_list("kind", "next_number")
        )
        self.assertEqual(before, after)
        self.assertEqual(synced, 0)


class ProtectedErrorRegressionTests(BaseJuridiqueTest):
    """Régression Schemathesis : DELETE sur un objet référencé par des FK
    protégées levait django.db.ProtectedError → 500. Le handler global
    `config.exceptions` le convertit en HTTP 409 Conflict."""

    def test_delete_partner_protege_retourne_409(self):
        self._dossier_gr()  # partenaire_gr → on_delete=PROTECT (ligne 675)
        from config.exceptions import drf_exception_handler
        from django.db.models.deletion import ProtectedError

        with self.assertRaises(ProtectedError):
            self.gr.delete()
        resp = drf_exception_handler(ProtectedError("x", {}), {})
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)

    def test_integrity_error_retourne_409(self):
        from config.exceptions import drf_exception_handler
        from django.db import IntegrityError

        resp = drf_exception_handler(IntegrityError("duplicate key"), {})
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)

    def test_other_exception_falls_back_to_drf(self):
        from config.exceptions import drf_exception_handler
        from rest_framework.exceptions import NotFound

        resp = drf_exception_handler(NotFound(), {})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class AlertesTests(BaseJuridiqueTest):
    def test_compute_alertes_bandes(self):
        self._convention(date_fin=date.today() + timedelta(days=75))
        self._caution(date_echeance=date.today() + timedelta(days=45))
        self._assurance(date_echeance=date.today() + timedelta(days=20))
        self._convention(date_fin=date.today() - timedelta(days=3), statut=Convention.Statut.SIGNE)
        alertes = compute_alertes()
        self.assertIn("conventions", alertes)
        self.assertEqual(alertes["compteurs"]["j90"], 1)
        self.assertEqual(alertes["compteurs"]["j60"], 1)
        self.assertEqual(alertes["compteurs"]["j30"], 1)
        self.assertEqual(alertes["compteurs"]["expiree"], 1)

    def test_alertas_lecture_authentifiee(self):
        _auth(self.client, "logi@etls.local")
        resp = self.client.get(f"{BASE}alertes/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("compteurs", resp.data)

    def test_compute_stats(self):
        self._courrier(Courrier.Statut.ENREGISTRE)
        self._courrier(Courrier.Statut.CLASSE)
        self._convention()
        self._contentieux()
        self._caution()
        self._assurance()
        self._dossier_gr()
        stats = compute_stats()
        self.assertGreaterEqual(stats["courriers"], 2)
        self.assertGreaterEqual(stats["courriers_a_classer"], 1)
        self.assertGreaterEqual(stats["conventions"], 1)
        self.assertGreaterEqual(stats["conventions_a_renouveler"], 1)
        self.assertGreaterEqual(stats["contentieux_ouverts"], 1)
        self.assertGreaterEqual(stats["cautions_en_cours"], 1)
        self.assertGreaterEqual(stats["assurances_a_renouveler"], 0)
        self.assertGreaterEqual(stats["dossiers_gr_ouverts"], 1)