"""Audit lot 7 (2026-10-17) — champs d'auteur / de validation non falsifiables par le client.

Q1 : un WPS ne naît pas « validé » et sa validation passe par l'action `valider`, réservée QA/QC + hiérarchie
     (date et validateur posés par le serveur) ; `validated_by` / `date_validation` ignorés en écriture.
Q2 : le validateur d'un PV n'est jamais saisi par le client : seule l'action `levee-reserve` le pose.
"""

from rest_framework.test import APITestCase

from users.models import User

from .models import PvControle, WpsWpqr


def user(email, role):
    return User.objects.create_user(email=email, password="x-Audit-2026", role=role, first_name=email[:3])


class WpsValidationTests(APITestCase):
    def setUp(self):
        self.qaqc = user("qa@etls.ga", User.Role.QAQC)
        self.autre_qa = user("qa2@etls.ga", User.Role.QAQC)
        self.atelier = user("atelier@etls.ga", User.Role.CHEF_ATELIER)

    def create(self, who, **extra):
        self.client.force_authenticate(who)
        body = {"type": WpsWpqr.Type.WPS, "reference": "WPS-RX-01", **extra}
        return self.client.post("/api/qualite/wps/", body, format="json")

    def test_wps_cree_en_brouillon_meme_si_le_client_envoie_valide(self):
        r = self.create(self.atelier, statut=WpsWpqr.Statut.VALIDE, validated_by=self.autre_qa.pk,
                        date_validation="2026-01-01")
        self.assertEqual(r.status_code, 201, r.content)
        wps = WpsWpqr.objects.get(pk=r.data["id"])
        self.assertEqual(wps.statut, WpsWpqr.Statut.BROUILLON)
        self.assertIsNone(wps.validated_by)
        self.assertIsNone(wps.date_validation)

    def test_patch_ne_peut_pas_valider_un_wps(self):
        wps = WpsWpqr.objects.get(pk=self.create(self.atelier).data["id"])
        self.client.force_authenticate(self.atelier)
        self.client.patch(f"/api/qualite/wps/{wps.pk}/", {"statut": "valide", "validated_by": self.qaqc.pk},
                          format="json")
        wps.refresh_from_db()
        self.assertEqual(wps.statut, WpsWpqr.Statut.BROUILLON)
        self.assertIsNone(wps.validated_by)

    def test_validation_reservee_qaqc_et_tracee_par_le_serveur(self):
        wps = WpsWpqr.objects.get(pk=self.create(self.atelier).data["id"])
        self.client.force_authenticate(self.atelier)
        self.assertEqual(self.client.post(f"/api/qualite/wps/{wps.pk}/valider/").status_code, 403)
        self.client.force_authenticate(self.qaqc)
        r = self.client.post(f"/api/qualite/wps/{wps.pk}/valider/")
        self.assertEqual(r.status_code, 200, r.content)
        wps.refresh_from_db()
        self.assertEqual(wps.statut, WpsWpqr.Statut.VALIDE)
        self.assertEqual(wps.validated_by, self.qaqc)
        self.assertIsNotNone(wps.date_validation)
        # Pas de double validation
        self.assertEqual(self.client.post(f"/api/qualite/wps/{wps.pk}/valider/").status_code, 400)


class PvValidatorTests(APITestCase):
    def setUp(self):
        self.qaqc = user("qa@etls.ga", User.Role.QAQC)
        self.autre = user("dg@etls.ga", User.Role.DGA)

    def test_validated_by_et_resultat_non_ecrits_par_le_client(self):
        self.client.force_authenticate(self.qaqc)
        r = self.client.post(
            "/api/qualite/pvs/",
            {"intitule": "PV réception spool 12", "validated_by": self.autre.pk, "resultat": "conforme",
             "levee_reserve": "2026-01-01"},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        pv = PvControle.objects.get(pk=r.data["id"])
        self.assertIsNone(pv.validated_by)
        self.assertIsNone(pv.levee_reserve)
