"""Audit métier M7 (2026-10-16) — permis de travail : test gaz, séparation des tâches, validité.

CL-OM-07 : permis de travail avec validation multi-étapes et test gaz.
H1 : démarrage impossible sans test gaz conforme (types à risque : chaud, espaces confinés, ATEX, chimique).
H2 : le demandeur ne valide pas son propre permis (hors admin) ; un permis annulé ne se « revalide » pas.
H3 : un test gaz non conforme sur un permis actif l'arrête ; permis expiré non démarrable.
"""

from django.test import override_settings
from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from users.models import User

from .models import PermisTravail


def user(email, role):
    return User.objects.create_user(email=email, password="x-Audit-2026", role=role, first_name=email[:3])


class PermisBase(APITestCase):
    def setUp(self):
        self.hse1 = user("hse1@etls.ga", User.Role.HSE)
        self.hse2 = user("hse2@etls.ga", User.Role.HSE)
        self.admin = User.objects.create_user(
            email="admin@etls.ga", password="x-Audit-2026", role=User.Role.ADMIN, is_staff=True
        )

    def permis(self, type_permis="chaud", statut=PermisTravail.Statut.DEMANDE, **kw):
        return PermisTravail.objects.create(
            type_permis=type_permis, emplacement="Zone A", description="Soudure", statut=statut,
            demandeur=kw.pop("demandeur", self.hse1), **kw,
        )

    def post(self, p, action, who, data=None):
        self.client.force_authenticate(who)
        return self.client.post(f"/api/hse/permis/{p.pk}/{action}/", data or {}, format="json")


class TestGazTests(PermisBase):
    def test_demarrage_refuse_sans_test_gaz_pour_un_permis_a_chaud(self):
        p = self.permis("chaud", PermisTravail.Statut.VALIDE)
        r = self.post(p, "demarrer", self.hse2)
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("gaz", str(r.data).lower())

    def test_demarrage_ok_apres_test_gaz_conforme(self):
        p = self.permis("confine", PermisTravail.Statut.VALIDE)
        r = self.post(p, "test-gaz", self.hse2, {"resultat": "conforme", "valeur": "LIE 0 %, O2 20,9 %"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.post(p, "demarrer", self.hse2).status_code, 200)

    def test_test_gaz_non_conforme_bloque_le_demarrage(self):
        p = self.permis("atex", PermisTravail.Statut.VALIDE)
        self.post(p, "test-gaz", self.hse2, {"resultat": "non_conforme", "valeur": "LIE 18 %"})
        self.assertEqual(self.post(p, "demarrer", self.hse2).status_code, 400)

    def test_test_gaz_perime_refuse(self):
        p = self.permis("chaud", PermisTravail.Statut.VALIDE)
        self.post(p, "test-gaz", self.hse2, {"resultat": "conforme", "valeur": "ok"})
        PermisTravail.objects.filter(pk=p.pk).update(test_gaz_date=timezone.now() - timedelta(hours=13))
        self.assertEqual(self.post(p, "demarrer", self.hse2).status_code, 400)

    def test_permis_sans_risque_gaz_demarre_sans_test(self):
        p = self.permis("hauteur", PermisTravail.Statut.VALIDE)
        self.assertEqual(self.post(p, "demarrer", self.hse2).status_code, 200)

    def test_non_conforme_sur_permis_actif_l_arrete(self):
        p = self.permis("chaud", PermisTravail.Statut.VALIDE)
        self.post(p, "test-gaz", self.hse2, {"resultat": "conforme", "valeur": "ok"})
        self.post(p, "demarrer", self.hse2)
        r = self.post(p, "test-gaz", self.hse2, {"resultat": "non_conforme", "valeur": "LIE 12 %"})
        self.assertEqual(r.status_code, 200, r.content)
        p.refresh_from_db()
        self.assertEqual(p.statut, PermisTravail.Statut.VALIDE)

    def test_test_gaz_interdit_hors_validation_ou_activite(self):
        p = self.permis("chaud", PermisTravail.Statut.DEMANDE)
        self.assertEqual(self.post(p, "test-gaz", self.hse2, {"resultat": "conforme"}).status_code, 400)

    def test_resultat_invalide_refuse(self):
        p = self.permis("chaud", PermisTravail.Statut.VALIDE)
        self.assertEqual(self.post(p, "test-gaz", self.hse2, {"resultat": "peut-etre"}).status_code, 400)


# Circuit à un niveau (HSE) : ces tests portent sur d'autres règles ; le circuit complet superviseur → HSE → DG
# est couvert par hse/test_permis_multiniveaux.py.
@override_settings(HSE_PERMIS_NIVEAUX=["hse"])
class SeparationDesTachesTests(PermisBase):
    def test_demandeur_ne_valide_pas_son_propre_permis(self):
        p = self.permis("hauteur")
        r = self.post(p, "valider", self.hse1)  # hse1 = demandeur
        self.assertEqual(r.status_code, 403, r.content)
        p.refresh_from_db()
        self.assertEqual(p.statut, PermisTravail.Statut.DEMANDE)

    def test_autre_validateur_ok(self):
        self.assertEqual(self.post(self.permis("hauteur"), "valider", self.hse2).status_code, 200)

    def test_admin_peut_valider(self):
        self.assertEqual(self.post(self.permis("hauteur"), "valider", self.admin).status_code, 200)

    def test_permis_annule_non_revalidable(self):
        p = self.permis("hauteur", PermisTravail.Statut.ANNULE)
        self.assertEqual(self.post(p, "valider", self.hse2).status_code, 400)


class ValiditeTests(PermisBase):
    def test_permis_expire_non_demarrable(self):
        hier = timezone.localdate() - timedelta(days=1)
        p = self.permis("hauteur", PermisTravail.Statut.VALIDE, date_debut=hier - timedelta(days=3), date_fin=hier)
        r = self.post(p, "demarrer", self.hse2)
        self.assertEqual(r.status_code, 400, r.content)

    def test_permis_futur_non_demarrable(self):
        demain = timezone.localdate() + timedelta(days=2)
        p = self.permis("hauteur", PermisTravail.Statut.VALIDE, date_debut=demain)
        self.assertEqual(self.post(p, "demarrer", self.hse2).status_code, 400)
