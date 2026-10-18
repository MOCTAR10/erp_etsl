"""Écarts M3 de la matrice CDC × code : heures d'OF calculées depuis la gamme, équipes / affectations / registre
de présence, circuit de validation des situations (séparation des tâches)."""

from datetime import date, timedelta
from decimal import Decimal

from rest_framework.test import APITestCase

from rh_paie.models import Employe
from users.models import User

from .models import (
    AffectationEquipe,
    Equipe,
    GammeOperatoire,
    GammeOperation,
    OrdreFabrication,
    PresenceChantier,
    SituationTravaux,
)


class _Base(APITestCase):
    def setUp(self):
        self.dir = User.objects.create_user(email="dir@etls.ga", password="x-Ecarts-2026", role=User.Role.DIRECTEUR_OPERATIONS)
        self.chef = User.objects.create_user(email="chef@etls.ga", password="x-Ecarts-2026", role=User.Role.CHEF_ATELIER)
        self.client.force_authenticate(self.dir)


class HeuresGammeTests(_Base):
    def gamme(self):
        g = GammeOperatoire.objects.create(label="Spool DN100")
        GammeOperation.objects.create(gamme=g, sequence=1, label="Découpe", poste="decoupe", planned_hours=Decimal("10"))
        GammeOperation.objects.create(gamme=g, sequence=2, label="Soudure", poste="soudure", planned_hours=Decimal("15.5"))
        return g

    def test_heures_calculees_depuis_la_gamme_et_la_quantite(self):
        of = OrdreFabrication.objects.create(label="Lot", gamme=self.gamme(), quantity=Decimal("2"))
        self.assertEqual(of.calculated_hours, Decimal("51.00"))

    def test_heures_saisies_conservees(self):
        of = OrdreFabrication.objects.create(label="Lot", gamme=self.gamme(), calculated_hours=Decimal("40"))
        self.assertEqual(of.calculated_hours, Decimal("40"))

    def test_creation_api_avec_gamme(self):
        r = self.client.post(
            "/api/operations/ordres/", {"label": "Lot API", "gamme": str(self.gamme().pk), "scope": "atelier"}, format="json"
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Decimal(r.json()["calculated_hours"]), Decimal("25.5"))

    def test_sans_gamme_reste_a_zero(self):
        self.assertEqual(OrdreFabrication.objects.create(label="Sans gamme").calculated_hours, 0)


class EquipeAffectationTests(_Base):
    def setUp(self):
        super().setUp()
        self.of = OrdreFabrication.objects.create(label="Chantier A", scope="chantier")
        self.equipe = Equipe.objects.create(label="Soudeurs A", metier="soudeur")

    def affecter(self, **extra):
        data = {
            "equipe": str(self.equipe.pk), "ordre": str(self.of.pk), "effectif": 4,
            "date_debut": date.today().isoformat(), "date_fin": (date.today() + timedelta(days=5)).isoformat(),
        }
        data.update(extra)
        return self.client.post("/api/operations/affectations/", data, format="json")

    def test_les_huit_corps_de_metier(self):
        self.assertEqual(len(Equipe.Metier.choices), 8)

    def test_creation_code_auto_et_attestation_serveur(self):
        r = self.affecter()
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.json()["code"].startswith("AFE"))
        self.assertEqual(r.json()["statut"], "planifiee")
        self.assertEqual(r.json()["created_by"], str(self.dir.pk))

    def test_statut_non_posable_par_le_client(self):
        r = self.affecter(statut="mobilisee")
        self.assertEqual(r.json()["statut"], "planifiee")

    def test_fin_avant_debut_refusee(self):
        r = self.affecter(date_fin=(date.today() - timedelta(days=1)).isoformat())
        self.assertEqual(r.status_code, 400)

    def test_equipe_inactive_refusee(self):
        self.equipe.actif = False
        self.equipe.save()
        self.assertEqual(self.affecter().status_code, 400)

    def test_mobilisation_attestee_puis_verrouillee(self):
        aff_id = self.affecter().json()["id"]
        r = self.client.post(f"/api/operations/affectations/{aff_id}/mobiliser/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["statut"], r.json()["mobilise_par"]), ("mobilisee", str(self.dir.pk)))
        self.assertEqual(self.client.post(f"/api/operations/affectations/{aff_id}/mobiliser/", {}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(f"/api/operations/affectations/{aff_id}/", {"effectif": 9}, format="json").status_code, 400)
        self.assertEqual(self.client.delete(f"/api/operations/affectations/{aff_id}/").status_code, 400)
        fin = self.client.post(f"/api/operations/affectations/{aff_id}/terminer/", {}, format="json")
        self.assertEqual(fin.json()["statut"], "terminee")

    def test_of_clos_non_mobilisable(self):
        aff_id = self.affecter().json()["id"]
        OrdreFabrication.objects.filter(pk=self.of.pk).update(status=OrdreFabrication.Status.CLOTURE)
        self.assertEqual(self.client.post(f"/api/operations/affectations/{aff_id}/mobiliser/", {}, format="json").status_code, 400)

    def test_ecriture_refusee_au_lecteur_sans_droit(self):
        lecteur = User.objects.create_user(email="rh@etls.ga", password="x-Ecarts-2026", role=User.Role.RH)
        self.client.force_authenticate(lecteur)
        self.assertEqual(self.affecter().status_code, 403)

    def test_filtre_par_ordre(self):
        self.affecter()
        autre = OrdreFabrication.objects.create(label="Autre")
        r = self.client.get(f"/api/operations/affectations/?ordre={autre.pk}")
        self.assertEqual(len(r.json()["results"] if isinstance(r.json(), dict) else r.json()), 0)


class RegistrePresenceTests(_Base):
    def setUp(self):
        super().setUp()
        self.of = OrdreFabrication.objects.create(label="Chantier A", scope="chantier")
        self.emp = Employe.objects.create(code="EMP-P1", civilite="masculin", nom="Ndong")

    def releve(self, **extra):
        data = {"ordre": str(self.of.pk), "employe": str(self.emp.pk), "date": date.today().isoformat(), "statut": "present"}
        data.update(extra)
        return self.client.post("/api/operations/presences/", data, format="json")

    def test_releve_attribue_au_releveur(self):
        r = self.releve()
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["releve_par"], str(self.dir.pk))

    def test_une_seule_ligne_par_jour(self):
        self.releve()
        self.assertEqual(self.releve().status_code, 400)
        self.assertEqual(PresenceChantier.objects.count(), 1)

    def test_absence_exige_un_motif(self):
        self.assertEqual(self.releve(statut="absent").status_code, 400)
        self.assertEqual(self.releve(statut="absent", motif="Maladie").status_code, 201)


class CircuitSituationTests(_Base):
    def situation(self, createur, statut=SituationTravaux.Status.BROUILLON):
        return SituationTravaux.objects.create(
            label="S1", period_start=date.today() - timedelta(days=30), period_end=date.today(),
            amount=Decimal("1000000"), status=statut, created_by=createur,
        )

    def post(self, s, action):
        return self.client.post(f"/api/operations/situations/{s.pk}/{action}/", {}, format="json")

    def test_soumettre_puis_valider_par_un_tiers(self):
        s = self.situation(self.chef)
        self.assertEqual(self.post(s, "soumettre").json()["status"], "soumise")
        self.assertEqual(self.post(s, "validate").json()["status"], "validee")

    def test_createur_ne_valide_pas_sa_situation(self):
        s = self.situation(self.dir, SituationTravaux.Status.SOUMISE)
        r = self.post(s, "validate")
        self.assertEqual(r.status_code, 400)
        s.refresh_from_db()
        self.assertEqual(s.status, SituationTravaux.Status.SOUMISE)

    def test_seul_un_brouillon_se_soumet(self):
        s = self.situation(self.chef, SituationTravaux.Status.VALIDEE)
        self.assertEqual(self.post(s, "soumettre").status_code, 400)
