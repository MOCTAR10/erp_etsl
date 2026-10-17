"""Audit lot 8 (2026-10-17) — circuit d'approbation des demandes d'achat (procédure achats, circuit RF-ERP-W1).

Avant : le statut d'une DA se changeait par PATCH (tout rôle d'écriture Achats pouvait « approuver » sa DA) et un BC
ou une consultation pouvait référencer une DA non approuvée.
Après : brouillon → soumise → approuvée | rejetée par actions dédiées ; approbation réservée à la hiérarchie
(ACHAT_APPROVAL_ROLES) ; BC / consultation uniquement sur DA approuvée, qui passe alors « convertie ».
"""

from rest_framework.test import APITestCase

from users.models import User

from .models import PurchaseRequest


def user(email, role):
    return User.objects.create_user(email=email, password="x-Audit-2026", role=role, first_name=email[:3])


class CircuitDaTests(APITestCase):
    def setUp(self):
        self.logistique = user("log@etls.ga", User.Role.LOGISTIQUE)
        self.atelier = user("atelier@etls.ga", User.Role.CHEF_ATELIER)
        self.finance = user("fin@etls.ga", User.Role.FINANCE)

    def da(self, who=None):
        self.client.force_authenticate(who or self.logistique)
        r = self.client.post("/api/achats/requests/", {"title": "Disques de meulage", "status": "approuvee"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return PurchaseRequest.objects.get(pk=r.data["id"])

    def act(self, who, da, action, data=None):
        self.client.force_authenticate(who)
        return self.client.post(f"/api/achats/requests/{da.pk}/{action}/", data or {}, format="json")

    def test_statut_client_ignore(self):
        da = self.da()
        self.assertEqual(da.status, PurchaseRequest.Status.BROUILLON)
        self.client.patch(f"/api/achats/requests/{da.pk}/", {"status": "approuvee"}, format="json")
        da.refresh_from_db()
        self.assertEqual(da.status, PurchaseRequest.Status.BROUILLON)

    def test_circuit_complet_et_roles(self):
        da = self.da()
        self.assertEqual(self.act(self.finance, da, "approuver").status_code, 400)  # pas encore soumise
        self.assertEqual(self.act(self.logistique, da, "soumettre").status_code, 200)
        self.assertEqual(self.act(self.atelier, da, "approuver").status_code, 403)  # saisie oui, approbation non
        self.assertEqual(self.act(self.logistique, da, "approuver").status_code, 403)
        r = self.act(self.finance, da, "approuver")
        self.assertEqual(r.status_code, 200, r.content)
        da.refresh_from_db()
        self.assertEqual(da.status, PurchaseRequest.Status.APPROUVEE)

    def test_rejet_motive(self):
        da = self.da()
        self.act(self.logistique, da, "soumettre")
        self.assertEqual(self.act(self.finance, da, "rejeter").status_code, 400)  # motif obligatoire
        self.assertEqual(self.act(self.finance, da, "rejeter", {"motif": "Stock suffisant"}).status_code, 200)
        da.refresh_from_db()
        self.assertEqual(da.status, PurchaseRequest.Status.REJETEE)
        self.assertIn("Stock suffisant", da.notes)

    def test_bc_uniquement_sur_da_approuvee_puis_convertie(self):
        da = self.da()
        self.client.force_authenticate(self.finance)
        self.assertEqual(self.client.post("/api/achats/orders/", {"request": str(da.pk)}, format="json").status_code, 400)
        self.act(self.logistique, da, "soumettre")
        self.act(self.finance, da, "approuver")
        self.client.force_authenticate(self.finance)
        r = self.client.post("/api/achats/orders/", {"request": str(da.pk)}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        da.refresh_from_db()
        self.assertEqual(da.status, PurchaseRequest.Status.CONVERTIE)
