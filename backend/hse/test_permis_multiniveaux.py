"""Lot 12 (2026-10-17) — permis de travail multi-niveaux émetteur → superviseur → HSE → DG (CDC M7 §9.4 / §9.5).

Circuit paramétrable (`HSE_PERMIS_NIVEAUX`, défaut superviseur → hse → dg — EX-G-02 / CL-OM « règles de validation
paramétrées ») ; chaque niveau a ses signataires ; le demandeur ne signe aucun niveau, une même personne ne signe pas deux
niveaux ; chaque niveau peut refuser ; le permis n'est valide qu'à la dernière signature.
"""

from datetime import date

from django.test import override_settings
from rest_framework.test import APITestCase

from users.models import User

from .models import PermisTravail


def user(email, role):
    return User.objects.create_user(email=email, password="x-Audit-2026", role=role, first_name=email[:3])


class PermisMultiNiveauxTests(APITestCase):
    def setUp(self):
        self.emetteur = user("emet@etls.ga", User.Role.CHEF_ATELIER)
        self.superviseur = user("sup@etls.ga", User.Role.DIRECTEUR_OPERATIONS)
        self.hse = user("hse@etls.ga", User.Role.HSE)
        self.dg = user("dg@etls.ga", User.Role.PDG)
        self.permis = PermisTravail.objects.create(type_permis="chaud", emplacement="Rack 4", description="Soudure",
                                                   demandeur=self.emetteur, date_debut=date.today())

    def valider(self, who, **data):
        self.client.force_authenticate(who)
        return self.client.post(f"/api/hse/permis/{self.permis.pk}/valider/", data, format="json")

    def test_circuit_complet_dans_l_ordre(self):
        for who, niveau_suivant in ((self.superviseur, "hse"), (self.hse, "dg")):
            r = self.valider(who)
            self.assertEqual(r.status_code, 200, r.content)
            self.assertEqual(r.data["statut"], "demande")
            self.assertEqual(r.data["prochain_niveau"], niveau_suivant)
        r = self.valider(self.dg)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["statut"], "valide")
        self.permis.refresh_from_db()
        self.assertEqual((self.permis.visa_superviseur_par, self.permis.visa_hse_par, self.permis.visa_dg_par),
                         (self.superviseur, self.hse, self.dg))

    def test_niveau_hors_ordre_refuse(self):
        r = self.valider(self.hse)  # le superviseur n'a pas encore signé
        self.assertEqual(r.status_code, 403, r.content)
        self.assertIn("superviseur", str(r.data).lower())

    def test_demandeur_ne_signe_aucun_niveau(self):
        self.assertEqual(self.valider(self.emetteur).status_code, 403)  # chef d'atelier = rôle superviseur, mais demandeur

    def test_meme_personne_ne_signe_pas_deux_niveaux(self):
        admin = User.objects.create_user(email="adm@etls.ga", password="x-Audit-2026", role=User.Role.ADMIN, is_staff=True)
        self.assertEqual(self.valider(admin).status_code, 200)  # superviseur
        r = self.valider(admin)  # tenterait aussi le niveau HSE
        self.assertEqual(r.status_code, 403, r.content)

    def test_un_niveau_peut_refuser(self):
        self.valider(self.superviseur)
        r = self.valider(self.hse, accept=False, motif="Zone non consignée")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["statut"], "refuse")

    @override_settings(HSE_PERMIS_NIVEAUX=["hse"])
    def test_circuit_parametrable(self):
        r = self.valider(self.hse)
        self.assertEqual(r.data["statut"], "valide", r.content)
