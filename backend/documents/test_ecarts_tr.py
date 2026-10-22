"""Écarts transverses — piste d'audit inaltérable avant / après (EX-G-06), export intégral et conservation (§8.2 Audit)."""

from datetime import timedelta

from django.contrib.admin.sites import site
from django.test import RequestFactory
from django.utils import timezone
from rest_framework.test import APITestCase

from users.models import JournalAcces, User

from .models import AuditLog

PWD = "x-Ecarts-Tr-2026"


class AuditGeneriqueTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(email="admin.audit@etls.ga", password=PWD, role=User.Role.ADMIN)
        cls.hse = User.objects.create_user(email="hse.audit@etls.ga", password=PWD, role=User.Role.HSE)

    def test_creation_modification_suppression_tracees_avec_avant_apres(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post("/api/referentiels/units/", {"code": "TRX", "label": "Unité test"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        pk = str(r.json()["id"])
        cree = AuditLog.objects.get(object_type="referentiels.unitofmeasure", object_id=pk, action="create")
        self.assertEqual(cree.user, self.admin)
        self.assertEqual(cree.detail["apres"]["label"], "Unité test")
        self.client.patch(f"/api/referentiels/units/{pk}/", {"label": "Unité modifiée"}, format="json")
        maj = AuditLog.objects.get(object_type="referentiels.unitofmeasure", object_id=pk, action="update")
        self.assertEqual(maj.detail["champs"], ["label"])
        self.assertEqual(maj.detail["avant"]["label"], "Unité test")
        self.assertEqual(maj.detail["apres"]["label"], "Unité modifiée")
        self.client.delete(f"/api/referentiels/units/{pk}/")
        supprime = AuditLog.objects.get(object_type="referentiels.unitofmeasure", object_id=pk, action="delete")
        self.assertEqual(supprime.detail["avant"]["code"], "TRX")

    def test_secrets_masques_et_droits_traces(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post("/api/users/users/", {"email": "neo@etls.ga", "password": "Motdepasse#2026", "role": "hse"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        cree = AuditLog.objects.get(object_type="users.user", object_id=str(r.json()["id"]), action="create")
        self.assertEqual(cree.detail["apres"]["password"], "***")
        self.client.patch(f"/api/users/users/{r.json()['id']}/", {"role": "qaqc"}, format="json")
        maj = AuditLog.objects.get(object_type="users.user", object_id=str(r.json()["id"]), action="update")
        self.assertEqual((maj.detail["avant"]["role"], maj.detail["apres"]["role"]), ("hse", "qaqc"))

    def test_hors_requete_non_trace(self):
        from referentiels.models import UnitOfMeasure

        UnitOfMeasure.objects.create(code="SEED", label="Seed")
        self.assertFalse(AuditLog.objects.filter(object_type="referentiels.unitofmeasure").exists())

    def test_piste_inalterable(self):
        entree = AuditLog.objects.create(action="create", object_type="x.y", object_id="1")
        entree.detail = {"falsifie": True}
        with self.assertRaises(ValueError):
            entree.save()
        with self.assertRaises(ValueError):
            entree.delete()
        requete = RequestFactory().get("/")
        requete.user = self.admin
        admin = site._registry[AuditLog]
        self.assertFalse(admin.has_change_permission(requete, entree))
        self.assertFalse(admin.has_delete_permission(requete, entree))
        self.assertFalse(admin.has_add_permission(requete))

    def test_export_integral_filtres_et_purge_apres_retention(self):
        vieille = AuditLog.objects.create(action="update", object_type="stocks.lotmatiere", object_id="42")
        AuditLog.objects.filter(pk=vieille.pk).update(created_at=timezone.now() - timedelta(days=365 * 6))
        recente = AuditLog.objects.create(action="update", object_type="stocks.lotmatiere", object_id="43")
        JournalAcces.objects.create(evenement="connexion", email="x@etls.ga")
        JournalAcces.objects.filter(email="x@etls.ga").update(cree_le=timezone.now() - timedelta(days=365 * 6))
        self.client.force_authenticate(self.hse)
        self.assertEqual(self.client.get("/api/documents/audit/").status_code, 403)
        self.assertEqual(self.client.post("/api/documents/audit/purger/").status_code, 403)
        self.client.force_authenticate(self.admin)
        r = self.client.get("/api/documents/audit/?module=stocks")
        self.assertEqual(r.json()["count"], 2)
        r = self.client.get("/api/documents/audit/?module=stocks&export=xlsx")
        self.assertIn("spreadsheetml", r["Content-Type"])
        r = self.client.get("/api/documents/audit/?export=csv")
        self.assertIn("stocks.lotmatiere", r.content.decode("utf-8-sig"))
        r = self.client.get("/api/documents/audit/retention/")
        self.assertEqual((r.json()["retention_ans"], r.json()["provisoire"], r.json()["purgeables"]), (5, True, 1))
        r = self.client.post("/api/documents/audit/purger/")
        self.assertEqual((r.json()["audit_supprimees"], r.json()["journal_acces_supprimees"]), (1, 1))
        self.assertFalse(AuditLog.objects.filter(pk=vieille.pk).exists())
        self.assertTrue(AuditLog.objects.filter(pk=recente.pk).exists())
        self.assertTrue(AuditLog.objects.filter(object_type="purge_audit").exists())
