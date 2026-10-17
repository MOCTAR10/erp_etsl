"""Audit lot 7 (2026-10-17) — auteur et demandeur d'un ordre de travail posés par le serveur."""

from rest_framework.test import APITestCase

from users.models import User

from .models import Actif, OrdreTravail


def user(email, role):
    return User.objects.create_user(email=email, password="x-Audit-2026", role=role, first_name=email[:3])


class OrdreTravailAuthorshipTests(APITestCase):
    def setUp(self):
        self.maint = user("maint@etls.ga", User.Role.MAINTENANCE)
        self.autre = user("autre@etls.ga", User.Role.MAINTENANCE)
        self.actif = Actif.objects.create(designation="Groupe de soudage", categorie=Actif.Categorie.MACHINE)

    def test_created_by_et_demandeur_imposes(self):
        self.client.force_authenticate(self.maint)
        r = self.client.post(
            "/api/maintenance/ordres/",
            {"actif": str(self.actif.pk), "description": "Fuite hydraulique", "created_by": self.autre.pk,
             "demandeur": self.autre.pk},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        ot = OrdreTravail.objects.get(pk=r.data["id"])
        self.assertEqual(ot.created_by, self.maint)
        self.assertEqual(ot.demandeur, self.maint)


class OrdreTravailTransitionsTests(APITestCase):
    """Audit lot 7 : saisies des transitions validées (400, jamais 500) ; annulation libère l'équipement."""

    def setUp(self):
        self.maint = user("maint@etls.ga", User.Role.MAINTENANCE)
        self.actif = Actif.objects.create(designation="Compresseur", categorie=Actif.Categorie.MACHINE)
        self.client.force_authenticate(self.maint)

    def ot(self, statut=OrdreTravail.Statut.EN_COURS):
        return OrdreTravail.objects.create(actif=self.actif, description="Révision", statut=statut)

    def post(self, ot, action, data=None):
        return self.client.post(f"/api/maintenance/ordres/{ot.pk}/{action}/", data or {}, format="json")

    def test_terminer_heures_invalides_400(self):
        self.assertEqual(self.post(self.ot(), "terminer", {"heures_mo": "abc"}).status_code, 400)

    def test_terminer_montants_negatifs_400(self):
        self.assertEqual(self.post(self.ot(), "terminer", {"heures_mo": "-2"}).status_code, 400)
        self.assertEqual(self.post(self.ot(), "terminer", {"cout_pieces": "-100"}).status_code, 400)

    def test_terminer_decision_hors_choix_400(self):
        ot = self.ot()
        self.assertEqual(self.post(ot, "terminer", {"decision": "zzz"}).status_code, 400)
        ot.refresh_from_db()
        self.assertEqual(ot.statut, OrdreTravail.Statut.EN_COURS)

    def test_planifier_priorite_hors_choix_400(self):
        self.assertEqual(self.post(self.ot(OrdreTravail.Statut.DEMANDE), "planifier", {"priorite": "zzz"}).status_code, 400)

    def test_annuler_un_ot_en_cours_libere_l_equipement(self):
        ot = self.ot(OrdreTravail.Statut.DEMANDE)
        self.assertEqual(self.post(ot, "demarrer").status_code, 200)
        self.actif.refresh_from_db()
        self.assertEqual(self.actif.statut, Actif.Statut.EN_MAINTENANCE)
        self.assertEqual(self.post(ot, "annuler").status_code, 200)
        self.actif.refresh_from_db()
        self.assertEqual(self.actif.statut, Actif.Statut.OPERATIONNEL)
