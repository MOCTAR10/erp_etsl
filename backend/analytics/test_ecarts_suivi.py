"""Lot de suivi : destinataires des alertes calendaires Couche D paramétrables (provisoires)."""

from rest_framework.test import APITestCase

from users.models import User


class DestinatairesCalendairesTests(APITestCase):
    """Couche D : destinataires des 4 familles d'alertes calendaires = paramètres `DEST_*` (rôles, provisoires)."""

    def setUp(self):
        self.admin = User.objects.create_user(email="adm2@etls.ga", password="x-Suivi-2026", role=User.Role.ADMIN, is_staff=True)
        self.client.force_authenticate(self.admin)

    def test_defauts_modifiables_et_utilises(self):
        from analytics.cubes import destinataires_famille

        self.assertEqual(destinataires_famille("garantie"), ("maintenance", "directeur_operations"))
        self.assertEqual(destinataires_famille("revue_direction"), ("qaqc", "pdg", "dga"))
        self.assertIsNone(destinataires_famille("epi"))
        data = self.client.get("/api/analytics/cubes/parametres/?page_size=200").json()
        rows = data["results"] if isinstance(data, dict) else data
        p = next(x for x in rows if x["code"] == "DEST_AUDIT_INTERNE")
        self.assertEqual((p["texte"], p["est_provisoire"]), ("qaqc", True))
        url = f"/api/analytics/cubes/parametres/{p['id']}/"
        self.assertEqual(self.client.patch(url, {"texte": "qaqc,inconnu"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(url, {"texte": ""}, format="json").status_code, 400)
        r = self.client.patch(url, {"texte": "QAQC, direction"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(destinataires_famille("audit_interne"), ("qaqc", "direction"))
        self.assertEqual(self.client.post(f"{url}confirmer/").json()["statut_valeur"], "confirme")
