"""Audit lot 8 (2026-10-17) — le déclarant d'un incident est l'utilisateur authentifié (traçabilité MANUEL §9.6/§9.9)."""

from django.utils import timezone
from rest_framework.test import APITestCase

from users.models import User

from .models import Incident


class DeclarantTests(APITestCase):
    def test_declared_by_impose_par_le_serveur(self):
        hse = User.objects.create_user(email="hse@etls.ga", password="x-Audit-2026", role=User.Role.HSE)
        autre = User.objects.create_user(email="autre@etls.ga", password="x-Audit-2026", role=User.Role.HSE)
        self.client.force_authenticate(hse)
        r = self.client.post(
            "/api/hse/incidents/",
            {"type_incident": "quasi_accident", "gravite": "mineure", "date_evenement": timezone.now().isoformat(),
             "lieu": "Atelier 2", "description": "Chute d'outil", "declared_by": str(autre.pk)},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Incident.objects.get(pk=r.data["id"]).declared_by, hse)


class ClotureIncidentTests(APITestCase):
    """MANUEL §9.6 : déclaration → enquête → rapport → clôture ; la clôture engage le HSE (comme l'enquête)."""

    def setUp(self):
        self.hse = User.objects.create_user(email="hse@etls.ga", password="x-Audit-2026", role=User.Role.HSE)
        self.logistique = User.objects.create_user(
            email="log@etls.ga", password="x-Audit-2026", role=User.Role.LOGISTIQUE
        )

    def incident(self, **kw):
        base = {"type_incident": "accident", "gravite": "majeure", "date_evenement": timezone.now(),
                "lieu": "Chantier B", "description": "Chute de hauteur", "declared_by": self.hse}
        base.update(kw)
        return Incident.objects.create(**base)

    def cloturer(self, who, inc, data=None):
        self.client.force_authenticate(who)
        return self.client.post(f"/api/hse/incidents/{inc.pk}/cloturer/", data or {}, format="json")

    def test_cloture_reservee_au_hse(self):
        inc = self.incident(gravite="mineure", type_incident="quasi_accident")
        self.assertEqual(self.cloturer(self.logistique, inc).status_code, 403)

    def test_accident_sans_rapport_non_cloturable(self):
        inc = self.incident()
        r = self.cloturer(self.hse, inc)
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("rapport", str(r.data).lower())
        self.assertEqual(self.cloturer(self.hse, inc, {"rapport": "Garde-corps absent ; CAPA ouverte."}).status_code, 200)

    def test_date_rapport_invalide_400(self):
        inc = self.incident(gravite="mineure", type_incident="quasi_accident")
        self.assertEqual(self.cloturer(self.hse, inc, {"date_rapport": "31/31/2026"}).status_code, 400)
