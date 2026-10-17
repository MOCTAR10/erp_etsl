"""Lot 15b (2026-10-17) — délégation temporaire des validations (CDC EX-G-02).

Un titulaire absent (congé, mission) délègue ses validations à un collègue sur une période datée :
- pendant la période, les nouvelles tâches de circuit qui lui reviendraient sont assignées au délégataire,
  avec une trace « par délégation » ;
- le délégataire peut aussi agir sur les tâches déjà assignées au titulaire ;
- hors période ou après annulation, plus aucun effet ;
- pas d'auto-délégation, pas de chevauchement de deux délégations du même titulaire, période cohérente.
"""

from datetime import date, timedelta

from django.core.exceptions import PermissionDenied
from rest_framework.test import APITestCase

from documents.models import Document
from users.models import User

from .models import Circuit, CircuitStep, Delegation, TaskComment
from .services import complete_task

PWD = "x-Audit-2026"


class DelegationTests(APITestCase):
    def setUp(self):
        self.auteur = User.objects.create_user(email="auteur@etls.ga", password=PWD, role=User.Role.SECRETAIRE_GENERAL)
        self.dga = User.objects.create_user(email="dga@etls.ga", password=PWD, role=User.Role.DGA)
        self.interim = User.objects.create_user(email="interim@etls.ga", password=PWD, role=User.Role.DIRECTEUR_PROJETS)
        self.autre = User.objects.create_user(email="autre@etls.ga", password=PWD, role=User.Role.HSE)
        circuit = Circuit.objects.create(code="c_dga", label="Visa DGA", max_days=5)
        CircuitStep.objects.create(circuit=circuit, order=1, name="Visa DGA", actor_role=User.Role.DGA, max_days=2)
        self.circuit = circuit

    def demarrer(self):
        from workflow import services

        doc = Document.objects.create(title="Note de service", status=Document.Status.DRAFT)
        return services._create_task(doc, self.circuit, self.circuit.steps.get(), self.auteur)

    def deleguer(self, debut=None, fin=None, **kw):
        return Delegation.objects.create(delegant=self.dga, delegataire=self.interim,
                                         date_debut=debut or date.today(), date_fin=fin or date.today() + timedelta(days=7),
                                         motif="Congés annuels", **kw)

    def test_nouvelle_tache_assignee_au_delegataire_avec_trace(self):
        delegation = self.deleguer()
        task = self.demarrer()
        self.assertEqual(task.assigned_to, self.interim)
        self.assertTrue(TaskComment.objects.filter(task=task, text__icontains=delegation.code).exists())

    def test_delegataire_agit_sur_une_tache_deja_assignee_au_titulaire(self):
        task = self.demarrer()
        self.assertEqual(task.assigned_to, self.dga)
        with self.assertRaises(PermissionDenied):
            complete_task(task, self.interim)
        self.deleguer()
        complete_task(task, self.interim)
        task.refresh_from_db()
        self.assertEqual(task.status, "done")

    def test_sans_effet_hors_periode_ou_annulee(self):
        self.deleguer(debut=date.today() + timedelta(days=3), fin=date.today() + timedelta(days=9))
        self.assertEqual(self.demarrer().assigned_to, self.dga)
        Delegation.objects.all().delete()
        delegation = self.deleguer()
        delegation.annuler(self.dga)
        self.assertEqual(self.demarrer().assigned_to, self.dga)

    def test_regles_de_coherence_via_api(self):
        self.client.force_authenticate(self.dga)
        url = "/api/workflow/delegations/"
        base = {"delegataire": str(self.interim.pk), "date_debut": str(date.today()), "date_fin": str(date.today() + timedelta(days=5)), "motif": "Mission"}
        r = self.client.post(url, base, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(str(r.data["delegant"]), str(self.dga.pk))  # le délégant est l'utilisateur connecté
        self.assertEqual(self.client.post(url, base, format="json").status_code, 400)  # chevauchement
        self.assertEqual(self.client.post(url, {**base, "delegataire": str(self.dga.pk), "date_debut": str(date.today() + timedelta(days=20)), "date_fin": str(date.today() + timedelta(days=21))}, format="json").status_code, 400)  # auto
        self.assertEqual(self.client.post(url, {**base, "date_debut": str(date.today() + timedelta(days=30)), "date_fin": str(date.today() + timedelta(days=29))}, format="json").status_code, 400)  # période
        r2 = self.client.post(f"{url}{r.data['id']}/annuler/")
        self.assertEqual(r2.status_code, 200, r2.content)
        self.assertFalse(r2.data["active"])

    def test_un_tiers_ne_peut_annuler(self):
        delegation = self.deleguer()
        self.client.force_authenticate(self.autre)
        self.assertIn(self.client.post(f"/api/workflow/delegations/{delegation.pk}/annuler/").status_code, (403, 404))
