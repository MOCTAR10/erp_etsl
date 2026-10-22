"""Écarts transverses — circuits modifiables à chaud (EX-G-02) et courriel systématique des notifications (EX-G-05)."""

from django.core import mail
from rest_framework.test import APITestCase

from users.models import ParametreTransverse, User
from users.parametres import get_param_transverse

from .models import Circuit, CircuitStep, Notification
from .notifications import notify

PWD = "x-Ecarts-Tr-2026"


class CircuitsModifiablesTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(email="admin.wf@etls.ga", password=PWD, role=User.Role.ADMIN)
        cls.dga = User.objects.create_user(email="dga.wf@etls.ga", password=PWD, role=User.Role.DGA)
        cls.rh = User.objects.create_user(email="rh.wf@etls.ga", password=PWD, role=User.Role.RH)
        cls.circuit = Circuit.objects.create(code="c_tr", label="Circuit test", max_days=5)
        CircuitStep.objects.create(circuit=cls.circuit, order=1, name="Saisie", actor_role=User.Role.FINANCE, max_days=1)
        CircuitStep.objects.create(circuit=cls.circuit, order=2, name="Visa", actor_role=User.Role.DGA, max_days=2)

    def url(self, suffix=""):
        return f"/api/workflow/circuits/{self.circuit.pk}/{suffix}"

    def test_edition_a_chaud_par_la_direction(self):
        self.client.force_authenticate(self.rh)
        self.assertEqual(self.client.patch(self.url(), {"label": "X"}, format="json").status_code, 403)
        self.assertEqual(self.client.post(self.url("ajouter-etape/"), {"name": "X", "actor_role": "pdg"}, format="json").status_code, 403)
        self.client.force_authenticate(self.dga)
        r = self.client.patch(self.url(), {"label": "Circuit révisé", "max_days": 7}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.client.patch(self.url(), {"code": "autre"}, format="json").status_code, 400)
        r = self.client.post(self.url("ajouter-etape/"), {"name": "Approbation PDG", "actor_role": "pdg", "max_days": 3}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        etapes = r.json()["steps"]
        self.assertEqual([e["name"] for e in etapes], ["Saisie", "Visa", "Approbation PDG"])
        self.assertEqual(self.client.post(self.url("ajouter-etape/"), {"name": "X", "actor_role": "inconnu"}, format="json").status_code, 400)
        derniere = etapes[-1]["id"]
        r = self.client.post(self.url("deplacer-etape/"), {"etape": derniere, "sens": "haut"}, format="json")
        self.assertEqual([e["name"] for e in r.json()["steps"]], ["Saisie", "Approbation PDG", "Visa"])
        r = self.client.post(self.url("modifier-etape/"), {"etape": derniere, "max_days": 4, "actor_role": "dga"}, format="json")
        modifiee = [e for e in r.json()["steps"] if e["id"] == derniere][0]
        self.assertEqual((modifiee["max_days"], modifiee["actor_role"]), (4, "dga"))
        r = self.client.post(self.url("retirer-etape/"), {"etape": derniere}, format="json")
        self.assertEqual(len(r.json()["steps"]), 2)
        # Désactivation : disparaît de la liste courante, visible pour la Direction avec `?tous=1`.
        self.client.patch(self.url(), {"is_active": False}, format="json")
        self.assertNotIn(self.circuit.pk, [c["id"] for c in self.client.get("/api/workflow/circuits/").json()["results"]])
        self.assertIn(self.circuit.pk, [c["id"] for c in self.client.get("/api/workflow/circuits/?tous=1").json()["results"]])

    def test_creation_d_un_circuit(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post("/api/workflow/circuits/", {"code": "c_nouveau", "label": "Nouveau", "max_days": 3}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(self.client.post("/api/workflow/circuits/", {"code": "c_nouveau", "label": "Bis", "max_days": 3}, format="json").status_code, 400)


class CourrielNotificationsTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="agent.wf@etls.ga", password=PWD, role=User.Role.HSE)

    def test_toute_notification_part_par_courriel_une_seule_fois(self):
        Notification.objects.create(user=self.user, subject="Échéance", message="Contrat à renouveler")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.user.email, mail.outbox[0].to)
        notify(self.user, "Relance", "Tâche en retard")
        self.assertEqual(len(mail.outbox), 2)

    def test_parametre_provisoire_desactive_les_courriels(self):
        p = get_param_transverse("NOTIF_EMAIL_ACTIF")
        p.valeur = 0
        p.save()
        Notification.objects.create(user=self.user, subject="Info", message="Interne seulement")
        notify(self.user, "Relance", "Interne seulement")
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 2)
        self.assertTrue(ParametreTransverse.objects.get(code="NOTIF_EMAIL_ACTIF").est_provisoire)
