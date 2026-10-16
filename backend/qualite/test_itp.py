"""ITP : points d'arrêt (hold) et d'observation (witness) — CL-OM-07.

Un plan d'inspection et d'essais est une suite ordonnée de points ; un POINT D'ARRÊT bloque la suite
des travaux tant qu'il n'est pas levé (par la personne habilitée : QA/QC, client, organisme).
"""

from rest_framework import status
from rest_framework.test import APITestCase

from users.models import User

from .models import ControleQualite, PointInspection


def user(email, role):
    return User.objects.create_user(email=email, password="x-Audit-2026", role=role, first_name=email[:3])


class ItpBase(APITestCase):
    def setUp(self):
        self.qaqc = user("qaqc@etls.ga", User.Role.QAQC)
        self.chef = user("atelier@etls.ga", User.Role.CHEF_ATELIER)
        self.itp = ControleQualite.objects.create(
            type_controle=ControleQualite.TypeControle.ITP, point_controle="ITP soudure ligne A",
            statut=ControleQualite.Statut.EN_COURS,
        )

    def point(self, ordre, type_point="arret", controle=None, **kw):
        return PointInspection.objects.create(
            controle=controle or self.itp, ordre=ordre, description=f"Point {ordre}",
            type_point=type_point, **kw,
        )

    def lever(self, p, who=None, resultat="conforme", commentaire=""):
        self.client.force_authenticate(who or self.qaqc)
        return self.client.post(
            f"/api/qualite/points-inspection/{p.pk}/lever/",
            {"resultat": resultat, "commentaire": commentaire}, format="json",
        )


class PointsItpTests(ItpBase):
    def test_creation_via_api_uniquement_sur_un_itp(self):
        visuel = ControleQualite.objects.create(type_controle="visuel", point_controle="v")
        self.client.force_authenticate(self.qaqc)
        r = self.client.post(
            "/api/qualite/points-inspection/",
            {"controle": str(visuel.pk), "ordre": 1, "description": "x", "type_point": "arret"},
            format="json",
        )
        self.assertEqual(r.status_code, 400, r.content)
        r = self.client.post(
            "/api/qualite/points-inspection/",
            {"controle": str(self.itp.pk), "ordre": 1, "description": "Fit-up", "type_point": "arret"},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["statut"], "en_attente")

    def test_levee_trace_qui_quand(self):
        p = self.point(1)
        r = self.lever(p, commentaire="Fit-up conforme")
        self.assertEqual(r.status_code, 200, r.content)
        p.refresh_from_db()
        self.assertEqual(p.statut, PointInspection.Statut.LEVE)
        self.assertEqual(p.leve_par, self.qaqc)
        self.assertIsNotNone(p.leve_le)

    def test_levee_dans_l_ordre_pour_les_points_d_arret(self):
        p1, p2 = self.point(1), self.point(2)
        self.assertEqual(self.lever(p2).status_code, 400)  # le point 1 (arrêt) n'est pas levé
        self.assertEqual(self.lever(p1).status_code, 200)
        self.assertEqual(self.lever(p2).status_code, 200)

    def test_point_d_observation_ne_bloque_pas_la_suite(self):
        self.point(1, type_point="observation")
        p2 = self.point(2)
        self.assertEqual(self.lever(p2).status_code, 200)

    def test_levee_reservee_au_qaqc_et_hierarchie(self):
        p = self.point(1)
        self.assertEqual(self.lever(p, who=self.chef).status_code, 403)
        p.refresh_from_db()
        self.assertEqual(p.statut, PointInspection.Statut.EN_ATTENTE)

    def test_point_leve_non_relevable_ni_modifiable(self):
        p = self.point(1)
        self.lever(p)
        self.assertEqual(self.lever(p).status_code, 400)
        self.client.force_authenticate(self.qaqc)
        r = self.client.patch(f"/api/qualite/points-inspection/{p.pk}/", {"statut": "en_attente"}, format="json")
        p.refresh_from_db()
        self.assertEqual(p.statut, PointInspection.Statut.LEVE)

    def test_non_conforme_enregistre(self):
        p = self.point(1)
        self.assertEqual(self.lever(p, resultat="non_conforme", commentaire="Soudure rejetée").status_code, 200)
        p.refresh_from_db()
        self.assertEqual(p.statut, PointInspection.Statut.NON_CONFORME)


class ValidationItpTests(ItpBase):
    def valider(self):
        self.client.force_authenticate(self.qaqc)
        return self.client.patch(
            f"/api/qualite/controles/{self.itp.pk}/", {"statut": "valide"}, format="json"
        )

    def test_itp_non_validable_avec_point_d_arret_en_attente(self):
        self.point(1)
        r = self.valider()
        self.assertEqual(r.status_code, 400, r.content)
        self.itp.refresh_from_db()
        self.assertEqual(self.itp.statut, ControleQualite.Statut.EN_COURS)

    def test_itp_non_validable_avec_point_non_conforme(self):
        p = self.point(1)
        self.lever(p, resultat="non_conforme")
        self.assertEqual(self.valider().status_code, 400)

    def test_itp_validable_quand_tous_les_arrets_sont_leves(self):
        p1 = self.point(1)
        self.point(2, type_point="observation")  # une observation en attente ne bloque pas
        self.lever(p1)
        r = self.valider()
        self.assertEqual(r.status_code, 200, r.content)

    def test_controle_non_itp_inchange(self):
        v = ControleQualite.objects.create(type_controle="visuel", point_controle="v", statut="en_cours")
        self.client.force_authenticate(self.qaqc)
        r = self.client.patch(f"/api/qualite/controles/{v.pk}/", {"statut": "valide"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)

    def test_serializer_expose_les_points_et_la_progression(self):
        p1 = self.point(1)
        self.point(2)
        self.lever(p1)
        self.client.force_authenticate(self.qaqc)
        r = self.client.get(f"/api/qualite/controles/{self.itp.pk}/")
        self.assertEqual(len(r.data["points"]), 2)
        self.assertEqual(r.data["points_arret_restants"], 1)
