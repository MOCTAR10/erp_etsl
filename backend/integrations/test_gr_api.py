"""Interface GLOBAL RENTAL (CL-OM-09) : API REST à jeton, flux entrants idempotents, webhooks signés.

Flux : BCI_GR / BL_GR / retour (références de la prestation), compteurs ; événements sortants
`gr.location.demarree` / `gr.location.cloturee`. La facturation intra-groupe reste isolée au compte 618.
"""

import hashlib
import hmac
import json
from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from logistique.models import EquipementParc, LectureCompteur, LocationGR
from outbox.models import OutboxEvent
from outbox.tasks import dispatch_outbox
from referentiels.models import Partner
from users.models import User

from .gr import validate_webhook_url
from .models import ApiClient, WebhookDelivery, WebhookEndpoint

BASE = "/api/integrations/"


def make_location(statut=LocationGR.Statut.ACTIVE, **kw):
    partner = Partner.objects.create(
        code=f"GR-{LocationGR.objects.count()}", name="GLOBAL RENTAL", kind="fournisseur", is_global_rental=True
    )
    eq = EquipementParc.objects.create(label="Grue GR 25t", categorie="levage", is_global_rental=True)
    return LocationGR.objects.create(equipement=eq, partenaire=partner, statut=statut, lecture_initiale=100, **kw)


class GrBase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@etls.ga", password="x-Audit-2026", role=User.Role.ADMIN, is_staff=True
        )
        self.client_gr, self.key = ApiClient.issue(name="GLOBAL RENTAL SI", scopes=["gr:read", "gr:write"], user=self.admin)
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION=f"Api-Key {self.key}")


class ApiKeyAuthTests(GrBase):
    def test_cle_valide_lit_les_locations(self):
        make_location()
        r = self.api.get(f"{BASE}gr/locations/")
        self.assertEqual(r.status_code, 200, r.content)

    def test_cle_absente_ou_invalide_refusee(self):
        self.assertEqual(APIClient().get(f"{BASE}gr/locations/").status_code, 401)
        bad = APIClient()
        bad.credentials(HTTP_AUTHORIZATION="Api-Key etsl_gr_nimportequoi")
        self.assertEqual(bad.get(f"{BASE}gr/locations/").status_code, 401)

    def test_cle_revoquee_refusee(self):
        self.client_gr.is_active = False
        self.client_gr.save()
        self.assertEqual(self.api.get(f"{BASE}gr/locations/").status_code, 401)

    def test_scope_insuffisant_refuse(self):
        _, read_only = ApiClient.issue(name="lecture seule", scopes=["gr:read"], user=self.admin)
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Api-Key {read_only}")
        loc = make_location()
        r = c.post(f"{BASE}gr/compteurs/", {"location": loc.code, "date": str(date.today()), "valeur": "150"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_cle_inutilisable_sur_le_reste_de_l_erp(self):
        for path in ("/api/logistique/locations/", "/api/users/users/", "/api/accounting/moves/", "/api/rh-paie/employes/"):
            self.assertIn(self.api.get(path).status_code, (401, 403), path)

    def test_cle_stockee_hachee_et_montree_une_fois(self):
        self.assertTrue(self.key.startswith("etsl_gr_"))
        self.assertNotIn(self.key, ApiClient.objects.get(pk=self.client_gr.pk).key_hash)
        self.assertEqual(self.client_gr.key_hash, hashlib.sha256(self.key.encode()).hexdigest())

    def test_derniere_utilisation_tracee(self):
        self.api.get(f"{BASE}gr/locations/")
        self.client_gr.refresh_from_db()
        self.assertIsNotNone(self.client_gr.last_used_at)


class CompteursEntrantsTests(GrBase):
    def post(self, loc, valeur, key=None, **kw):
        body = {"location": loc.code, "date": str(date.today()), "valeur": str(valeur), "type_lecture": "periodique"}
        body.update(kw)
        headers = {"HTTP_IDEMPOTENCY_KEY": key} if key else {}
        return self.api.post(f"{BASE}gr/compteurs/", body, format="json", **headers)

    def test_releve_cree_avec_source_gr(self):
        loc = make_location()
        r = self.post(loc, 130)
        self.assertEqual(r.status_code, 201, r.content)
        lec = LectureCompteur.objects.get()
        self.assertEqual((lec.source, lec.valeur, lec.location), ("gr", Decimal("130"), loc))

    def test_compteur_en_baisse_refuse(self):
        loc = make_location()
        self.post(loc, 130)
        self.assertEqual(self.post(loc, 120).status_code, 400)
        self.assertEqual(LectureCompteur.objects.count(), 1)

    def test_inferieur_au_compteur_initial_refuse(self):
        loc = make_location()  # lecture_initiale = 100
        self.assertEqual(self.post(loc, 90).status_code, 400)

    def test_rejeu_idempotent(self):
        loc = make_location()
        r1 = self.post(loc, 130, key="gr-1")
        r2 = self.post(loc, 130, key="gr-1")
        self.assertEqual(r1.data["id"], r2.data["id"])
        self.assertEqual(LectureCompteur.objects.count(), 1)

    def test_location_inconnue_ou_inactive(self):
        loc = make_location(statut=LocationGR.Statut.TERMINEE)
        self.assertEqual(self.post(loc, 130).status_code, 400)
        loc2 = make_location()
        self.assertEqual(self.api.post(f"{BASE}gr/compteurs/", {"location": "LOC99999", "date": str(date.today()), "valeur": "1"}, format="json").status_code, 400)
        del loc2

    def test_date_future_refusee(self):
        loc = make_location()
        self.assertEqual(self.post(loc, 130, date=str(date.today() + timedelta(days=3))).status_code, 400)


class DocumentsEntrantsTests(GrBase):
    def post(self, loc, type_, ref):
        return self.api.post(f"{BASE}gr/documents/", {"location": loc.code, "type": type_, "reference": ref}, format="json")

    def test_references_enregistrees(self):
        loc = make_location()
        self.assertEqual(self.post(loc, "bci_gr", "BCI-2026-001").status_code, 200)
        self.assertEqual(self.post(loc, "bl_gr", "BL-778").status_code, 200)
        self.assertEqual(self.post(loc, "retour_gr", "RET-12").status_code, 200)
        loc.refresh_from_db()
        self.assertEqual((loc.reference_bc, loc.reference_bl, loc.reference_retour), ("BCI-2026-001", "BL-778", "RET-12"))

    def test_meme_reference_rejouable_autre_valeur_en_conflit(self):
        loc = make_location()
        self.post(loc, "bl_gr", "BL-1")
        self.assertEqual(self.post(loc, "bl_gr", "BL-1").status_code, 200)
        self.assertEqual(self.post(loc, "bl_gr", "BL-2").status_code, 409)
        loc.refresh_from_db()
        self.assertEqual(loc.reference_bl, "BL-1")

    def test_type_ou_reference_invalides(self):
        loc = make_location()
        self.assertEqual(self.post(loc, "facture", "X").status_code, 400)
        self.assertEqual(self.post(loc, "bl_gr", "x" * 60).status_code, 400)
        self.assertEqual(self.post(loc, "bl_gr", "<script>").status_code, 400)


class WebhookUrlTests(TestCase):
    def test_https_public_accepte(self):
        with mock.patch("integrations.gr._resolve", return_value=["93.184.216.34"]):
            validate_webhook_url("https://gr.example.com/hook", debug=False)

    def test_http_refuse_hors_debug_accepte_en_debug(self):
        with mock.patch("integrations.gr._resolve", return_value=["93.184.216.34"]):
            with self.assertRaises(ValueError):
                validate_webhook_url("http://gr.example.com/hook", debug=False)
            validate_webhook_url("http://gr.example.com/hook", debug=True)

    def test_adresses_internes_refusees_hors_debug(self):
        for ip in ("127.0.0.1", "10.0.0.5", "192.168.1.10", "169.254.169.254", "172.16.0.3", "::1"):
            with mock.patch("integrations.gr._resolve", return_value=[ip]):
                with self.assertRaises(ValueError, msg=ip):
                    validate_webhook_url("https://interne.example.com/x", debug=False)

    def test_schema_exotique_refuse(self):
        for url in ("ftp://x.example.com", "file:///etc/passwd", "javascript:alert(1)", "https://"):
            with self.assertRaises(ValueError, msg=url):
                validate_webhook_url(url, debug=True)


@override_settings(DEBUG=True)
class WebhooksSortantsTests(GrBase):
    def setUp(self):
        super().setUp()
        self.endpoint = WebhookEndpoint.objects.create(
            name="GR SI", url="https://gr.example.com/hook", secret="s3cret", topics=["gr.location.demarree", "gr.location.cloturee"],
        )

    def start(self, loc):
        self.api.credentials()  # action ETSL : on passe par un utilisateur
        c = APIClient()
        c.force_authenticate(self.admin)
        return c.post(f"/api/logistique/locations/{loc.pk}/demarrer/", {"lecture_initiale": 100}, format="json")

    def test_demarrage_publie_un_evenement_et_livre_un_webhook_signe(self):
        loc = make_location(statut=LocationGR.Statut.BROUILLON)
        self.assertEqual(self.start(loc).status_code, 200)
        self.assertTrue(OutboxEvent.objects.filter(topic="gr.location.demarree").exists())
        with mock.patch("integrations.gr._resolve", return_value=["93.184.216.34"]), mock.patch(
            "integrations.gr.requests.post"
        ) as post:
            post.return_value = mock.Mock(status_code=200)
            dispatch_outbox()
        self.assertEqual(post.call_count, 1)
        args, kwargs = post.call_args
        body = kwargs["data"]
        sig = kwargs["headers"]["X-ETSL-Signature"]
        expected = "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
        self.assertTrue(hmac.compare_digest(sig, expected))
        self.assertEqual(kwargs["headers"]["X-ETSL-Event"], "gr.location.demarree")
        self.assertFalse(kwargs.get("allow_redirects", True))
        data = json.loads(body)
        self.assertEqual(data["data"]["code"], loc.code)
        d = WebhookDelivery.objects.get()
        self.assertEqual((d.status, d.response_code), ("delivered", 200))

    def test_echec_enregistre_puis_reessayable(self):
        loc = make_location(statut=LocationGR.Statut.BROUILLON)
        self.start(loc)
        with mock.patch("integrations.gr._resolve", return_value=["93.184.216.34"]), mock.patch(
            "integrations.gr.requests.post", side_effect=OSError("timeout")
        ):
            dispatch_outbox()
        d = WebhookDelivery.objects.get()
        self.assertEqual(d.status, "pending")
        self.assertEqual(d.attempts, 1)
        self.assertIn("timeout", d.last_error)
        from .gr import retry_due_deliveries

        WebhookDelivery.objects.update(next_attempt_at=None)
        with mock.patch("integrations.gr._resolve", return_value=["93.184.216.34"]), mock.patch(
            "integrations.gr.requests.post"
        ) as post:
            post.return_value = mock.Mock(status_code=204)
            retry_due_deliveries()
        d.refresh_from_db()
        self.assertEqual(d.status, "delivered")

    def test_abandon_apres_le_nombre_maximal_de_tentatives(self):
        loc = make_location(statut=LocationGR.Statut.BROUILLON)
        self.start(loc)
        from .gr import MAX_DELIVERY_ATTEMPTS, retry_due_deliveries

        with mock.patch("integrations.gr._resolve", return_value=["93.184.216.34"]), mock.patch(
            "integrations.gr.requests.post", return_value=mock.Mock(status_code=500)
        ):
            dispatch_outbox()
            for _ in range(MAX_DELIVERY_ATTEMPTS):
                WebhookDelivery.objects.update(next_attempt_at=None)
                retry_due_deliveries()
        self.assertEqual(WebhookDelivery.objects.get().status, "failed")

    def test_endpoint_inactif_ou_autre_sujet_ignore(self):
        WebhookEndpoint.objects.create(name="inactif", url="https://x.example.com", secret="a", topics=["gr.location.demarree"], is_active=False)
        WebhookEndpoint.objects.create(name="autre", url="https://y.example.com", secret="b", topics=["gr.location.cloturee"])
        loc = make_location(statut=LocationGR.Statut.BROUILLON)
        self.start(loc)
        with mock.patch("integrations.gr._resolve", return_value=["93.184.216.34"]), mock.patch(
            "integrations.gr.requests.post", return_value=mock.Mock(status_code=200)
        ):
            dispatch_outbox()
        self.assertEqual(WebhookDelivery.objects.count(), 1)  # seul l'endpoint actif abonné au sujet


class DemarrageLocationTests(TestCase):
    """Correctif d'audit : une location ne démarre qu'une fois, depuis le brouillon, avec un compteur valide."""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@etls.ga", password="x-Audit-2026", role=User.Role.ADMIN, is_staff=True
        )
        self.c = APIClient()
        self.c.force_authenticate(self.admin)

    def demarrer(self, loc, lecture):
        return self.c.post(f"/api/logistique/locations/{loc.pk}/demarrer/", {"lecture_initiale": lecture}, format="json")

    def test_depart_unique_depuis_brouillon(self):
        loc = make_location(statut=LocationGR.Statut.BROUILLON)
        self.assertEqual(self.demarrer(loc, 10).status_code, 200)
        self.assertEqual(self.demarrer(loc, 99).status_code, 400)  # déjà active
        loc.refresh_from_db()
        self.assertEqual(loc.lecture_initiale, 10)

    def test_location_terminee_ou_annulee_non_redemarrable(self):
        for st in (LocationGR.Statut.TERMINEE, LocationGR.Statut.ANNULEE):
            self.assertEqual(self.demarrer(make_location(statut=st), 10).status_code, 400)

    def test_compteur_invalide_refuse(self):
        loc = make_location(statut=LocationGR.Statut.BROUILLON)
        for bad in ("abc", -5, ""):
            self.assertEqual(self.demarrer(loc, bad).status_code, 400, bad)


class AdministrationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@etls.ga", password="x-Audit-2026", role=User.Role.ADMIN, is_staff=True
        )
        self.simple = User.objects.create_user(email="u@etls.ga", password="x-Audit-2026", role=User.Role.FINANCE)
        self.c = APIClient()
        self.c.force_authenticate(self.admin)

    def test_creation_client_renvoie_la_cle_une_seule_fois(self):
        r = self.c.post(f"{BASE}api-clients/", {"name": "GR", "scopes": ["gr:read"]}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        key = r.data["api_key"]
        self.assertTrue(key.startswith("etsl_gr_"))
        lst = self.c.get(f"{BASE}api-clients/")
        self.assertNotIn("api_key", json.dumps(lst.data["results"][0]))
        self.assertNotIn(key, json.dumps(lst.data))
        # et la clé fonctionne
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f"Api-Key {key}")
        self.assertEqual(api.get(f"{BASE}gr/equipements/").status_code, 200)

    def test_scopes_inconnus_refuses(self):
        r = self.c.post(f"{BASE}api-clients/", {"name": "GR", "scopes": ["admin:all"]}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_revocation_par_patch(self):
        r = self.c.post(f"{BASE}api-clients/", {"name": "GR", "scopes": ["gr:read"]}, format="json")
        key = r.data["api_key"]
        self.c.patch(f"{BASE}api-clients/{r.data['id']}/", {"is_active": False}, format="json")
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f"Api-Key {key}")
        self.assertEqual(api.get(f"{BASE}gr/equipements/").status_code, 401)

    def test_reserve_aux_administrateurs(self):
        self.c.force_authenticate(self.simple)
        for path in ("api-clients/", "webhooks/", "webhook-deliveries/"):
            self.assertEqual(self.c.get(f"{BASE}{path}").status_code, 403, path)

    @override_settings(DEBUG=False)
    def test_webhook_url_interne_refusee_a_la_creation(self):
        with mock.patch("integrations.gr._resolve", return_value=["10.0.0.7"]):
            r = self.c.post(
                f"{BASE}webhooks/",
                {"name": "x", "url": "https://interne.example.com/h", "topics": ["gr.location.demarree"]},
                format="json",
            )
        self.assertEqual(r.status_code, 400, r.content)

    @override_settings(DEBUG=False)
    def test_webhook_cree_secret_montre_une_fois(self):
        with mock.patch("integrations.gr._resolve", return_value=["93.184.216.34"]):
            r = self.c.post(
                f"{BASE}webhooks/",
                {"name": "GR", "url": "https://gr.example.com/h", "topics": ["gr.location.demarree"]},
                format="json",
            )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.data["secret_once"])
        lst = self.c.get(f"{BASE}webhooks/")
        self.assertNotIn("secret", lst.data["results"][0])
        self.assertTrue(WebhookEndpoint.objects.get().secret)

    def test_sujets_invalides_refuses(self):
        with mock.patch("integrations.gr._resolve", return_value=["93.184.216.34"]):
            r = self.c.post(f"{BASE}webhooks/", {"name": "x", "url": "https://a.example.com", "topics": ["<x>"]}, format="json")
        self.assertEqual(r.status_code, 400)
