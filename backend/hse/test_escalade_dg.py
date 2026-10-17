"""Lot 12 (2026-10-17) — escalade DG obligatoire pour les accidents graves (CDC M7 §9.4 / §9.8).

Accident grave = gravité critique, ou accident / blessure de gravité majeure. Escalade = notification immédiate à la
Direction Générale (PDG, DGA), tracée sur l'incident ; déclenchée aussi si la gravité est relevée après déclaration.
"""

from django.utils import timezone
from rest_framework.test import APITestCase

from users.models import User
from workflow.models import Notification

from .models import Incident


def user(email, role):
    return User.objects.create_user(email=email, password="x-Audit-2026", role=role, first_name=email[:3])


class EscaladeDgTests(APITestCase):
    def setUp(self):
        self.hse = user("hse@etls.ga", User.Role.HSE)
        self.dg = user("dg@etls.ga", User.Role.PDG)
        self.dga = user("dga@etls.ga", User.Role.DGA)
        self.client.force_authenticate(self.hse)

    def declarer(self, **kw):
        body = {"type_incident": "accident", "gravite": "majeure", "date_evenement": timezone.now().isoformat(),
                "lieu": "Chantier B", "description": "Chute de hauteur"}
        body.update(kw)
        r = self.client.post("/api/hse/incidents/", body, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return Incident.objects.get(pk=r.data["id"])

    def test_accident_majeur_escalade_au_dg_et_trace(self):
        inc = self.declarer()
        self.assertIsNotNone(inc.escalade_dg_le)
        for u in (self.dg, self.dga):
            self.assertTrue(Notification.objects.filter(user=u, kind="escalation", subject__icontains=inc.code).exists())

    def test_incident_critique_de_tout_type_escalade(self):
        self.assertIsNotNone(self.declarer(type_incident="pollution", gravite="critique").escalade_dg_le)

    def test_quasi_accident_mineur_non_escalade(self):
        inc = self.declarer(type_incident="quasi_accident", gravite="mineure")
        self.assertIsNone(inc.escalade_dg_le)
        self.assertFalse(Notification.objects.filter(user=self.dg).exists())

    def test_gravite_relevee_apres_declaration_escalade_une_seule_fois(self):
        inc = self.declarer(type_incident="incident", gravite="mineure")
        self.client.patch(f"/api/hse/incidents/{inc.pk}/", {"gravite": "critique"}, format="json")
        inc.refresh_from_db()
        self.assertIsNotNone(inc.escalade_dg_le)
        self.client.patch(f"/api/hse/incidents/{inc.pk}/", {"lieu": "Chantier B, zone 2"}, format="json")
        self.assertEqual(Notification.objects.filter(user=self.dg).count(), 1)
