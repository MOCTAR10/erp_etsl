"""Recette du lot de suivi (M1) : critères RAO ENG-PR1-01, définition du BS, du prix moyen et mention des PDF
deviennent des paramètres provisoires éditables (texte + poids) et confirmables ; valeurs par défaut inchangées."""

from rest_framework.test import APITestCase

from users.models import User

from . import ecarts_m1

API = "/api/commercial/"


class ParametresTexteM1Tests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(email="adm@etls.ga", password="x-Suivi-2026", role=User.Role.ADMIN, is_staff=True)
        self.client.force_authenticate(self.admin)

    def params(self):
        data = self.client.get(f"{API}parametres/?page_size=200").json()
        rows = data["results"] if isinstance(data, dict) else data
        return {p["code"]: p for p in rows}

    def test_defauts_identiques_puis_modifiables_et_confirmables(self):
        r = self.client.get(f"{API}tender-reviews/criteres-defaut/").json()
        self.assertEqual(r["criteres"], ecarts_m1.CRITERES_RAO_DEFAUT)
        self.assertTrue(r["provisoire"])
        p = self.params()
        for code in (*ecarts_m1.CODES_CRITERES_RAO, "DEFINITION_BS", "DEFINITION_PRIX_MOYEN", "NOTE_MODELE_PDF"):
            self.assertTrue(p[code]["est_provisoire"], code)
        self.assertEqual(p["DEFINITION_BS"]["texte"], ecarts_m1.DEFINITION_BS)
        c1 = p["RAO_CRITERE_1"]
        r = self.client.patch(f"{API}parametres/{c1['id']}/", {"texte": "Références pétrolières", "valeur": "30"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        c6 = p["RAO_CRITERE_6"]
        self.client.patch(f"{API}parametres/{c6['id']}/", {"valeur": "0"}, format="json")  # critère retiré
        criteres = self.client.get(f"{API}tender-reviews/criteres-defaut/").json()["criteres"]
        self.assertEqual(len(criteres), 5)
        self.assertEqual(criteres[0], {"libelle": "Références pétrolières", "poids": 30})
        self.assertEqual(self.client.patch(f"{API}parametres/{c1['id']}/", {"valeur": "-1"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(f"{API}parametres/{c1['id']}/", {"texte": " "}, format="json").status_code, 400)
        bs = p["DEFINITION_BS"]
        self.client.patch(f"{API}parametres/{bs['id']}/", {"texte": "BS = bon de sortie validé"}, format="json")
        self.assertEqual(ecarts_m1.get_texte("DEFINITION_BS"), "BS = bon de sortie validé")
        r = self.client.post(f"{API}parametres/{bs['id']}/confirmer/")
        self.assertEqual(r.json()["statut_valeur"], "confirme")
        # Un paramètre numérique n'a pas de texte.
        go = p["RAO_SEUIL_GO"]
        self.assertEqual(self.client.patch(f"{API}parametres/{go['id']}/", {"texte": "x"}, format="json").status_code, 400)
