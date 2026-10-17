"""Lot 13 (2026-10-17) — revue d'appel d'offres, revue de commande, OF automatiques (CDC M1 §3.4 / §3.8 / §3.10-3.11).

- RAO : note pondérée des critères (poids × note / 100) → décision ≥ 75 % Go, 50-75 % Go sous réserve, < 50 % No-Go ;
  un No-Go ne se soumet pas, un Go sous réserve exige une justification.
- RC : Δ prix ≤ 5 % et Δ délai ≤ 7 j → revue légère (validable par un rôle commercial), sinon revue complète
  (Direction + commentaire) ; « blocage de l'affaire tant que la RC n'est pas validée ».
- Affaire confirmée → génération automatique de l'OF (opérations atelier / chantier).
"""

from datetime import date, timedelta
from decimal import Decimal

from rest_framework.test import APITestCase

from operations.models import OrdreFabrication
from users.models import User

from .models import Affaire, RevueCommande, TenderReview


def user(email, role):
    return User.objects.create_user(email=email, password="x-Audit-2026", role=role, first_name=email[:3])


class RaoTests(APITestCase):
    def setUp(self):
        self.commercial = user("dp@etls.ga", User.Role.DIRECTEUR_PROJETS)
        self.client.force_authenticate(self.commercial)

    def rao(self, notes):
        criteres = [{"libelle": f"Critère {i}", "poids": poids, "note": note} for i, (poids, note) in enumerate(notes)]
        r = self.client.post("/api/commercial/tender-reviews/", {"tender_ref": "AO-2026-07", "criteres": criteres}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.data

    def test_note_ponderee_et_decision(self):
        self.assertEqual(self.rao([(40, 90), (60, 70)])["score"], "78.00")
        self.assertEqual(self.rao([(40, 90), (60, 70)])["decision_rao"], "go")
        self.assertEqual(self.rao([(50, 60), (50, 60)])["decision_rao"], "go_reserve")
        self.assertEqual(self.rao([(100, 40)])["decision_rao"], "no_go")

    def test_criteres_invalides_refuses(self):
        r = self.client.post("/api/commercial/tender-reviews/",
                             {"tender_ref": "AO-X", "criteres": [{"libelle": "Technique", "poids": 50, "note": 140}]}, format="json")
        self.assertEqual(r.status_code, 400, r.content)

    def test_no_go_ne_se_soumet_pas_go_reserve_justifie(self):
        no_go = self.rao([(100, 30)])
        self.assertEqual(self.client.post(f"/api/commercial/tender-reviews/{no_go['id']}/soumettre/").status_code, 400)
        reserve = self.rao([(100, 60)])
        url = f"/api/commercial/tender-reviews/{reserve['id']}/soumettre/"
        self.assertEqual(self.client.post(url).status_code, 400)  # justification manquante
        r = self.client.post(url, {"decision": "Go sous réserve de partenariat CND agréé"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["review_status"], TenderReview.Status.SOUMIS)


class RevueCommandeTests(APITestCase):
    def setUp(self):
        self.commercial = user("dp@etls.ga", User.Role.DIRECTEUR_PROJETS)
        self.dg = user("dg@etls.ga", User.Role.PDG)
        self.client.force_authenticate(self.commercial)
        self.affaire = Affaire.objects.create(title="Pipeline Line B", affaire_type="chantier",
                                              start_date=date.today(), end_date=date.today() + timedelta(days=90))

    def rc(self, montant_commande, delai_commande):
        r = self.client.post("/api/commercial/revues-commande/", {
            "affaire": str(self.affaire.pk), "montant_offre": "100000000", "montant_commande": montant_commande,
            "delai_offre_jours": 90, "delai_commande_jours": delai_commande,
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.data

    def confirmer(self, who=None):
        self.client.force_authenticate(who or self.commercial)
        return self.client.post(f"/api/commercial/affaires/{self.affaire.pk}/confirmer/")

    def test_affaire_bloquee_sans_rc_validee(self):
        r = self.confirmer()
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("revue de commande", str(r.data).lower())

    def test_revue_legere_puis_confirmation_genere_l_of(self):
        rc = self.rc("103000000", 95)  # Δ prix 3 %, Δ délai 5 j
        self.assertEqual(rc["type_revue"], RevueCommande.Type.LEGERE)
        self.assertEqual(self.client.post(f"/api/commercial/revues-commande/{rc['id']}/valider/").status_code, 200)
        r = self.confirmer()
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["status"], Affaire.Status.CONFIRMEE)
        of = OrdreFabrication.objects.get(affaire=self.affaire)
        self.assertEqual((of.scope, of.status), (OrdreFabrication.Scope.CHANTIER, OrdreFabrication.Status.PREVU))
        self.assertEqual(self.confirmer().status_code, 400)  # déjà confirmée : pas de second OF
        self.assertEqual(OrdreFabrication.objects.filter(affaire=self.affaire).count(), 1)

    def test_revue_complete_reservee_a_la_direction_avec_commentaire(self):
        rc = self.rc("108000000", 90)  # Δ prix 8 %
        self.assertEqual(rc["type_revue"], RevueCommande.Type.COMPLETE)
        url = f"/api/commercial/revues-commande/{rc['id']}/valider/"
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_authenticate(self.dg)
        self.assertEqual(self.client.post(url).status_code, 400)  # commentaire obligatoire
        self.assertEqual(self.client.post(url, {"commentaire": "Avenant prix acier accepté"}, format="json").status_code, 200)
        self.assertEqual(self.confirmer(self.dg).status_code, 200)

    def test_delai_au_dela_de_7_jours_revue_complete(self):
        self.assertEqual(self.rc("100000000", 100)["type_revue"], RevueCommande.Type.COMPLETE)

    def test_statut_affaire_non_modifiable_par_patch(self):
        self.client.patch(f"/api/commercial/affaires/{self.affaire.pk}/", {"status": "confirmee"}, format="json")
        self.affaire.refresh_from_db()
        self.assertEqual(self.affaire.status, Affaire.Status.BROUILLON)
