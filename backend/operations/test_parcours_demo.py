"""Recette « parcours démo » lot A : le seed rejoue le workflow M1 -> M3 -> M9 par l'API réelle, sans saisie préalable."""

from django.core.management import call_command
from django.test import TestCase

from commercial.models import Affaire
from hse.models import PermisTravail
from operations.cloture import alertes_surcharge
from operations.models import AffectationEquipe, OrdreFabrication, PointageChantier, PresenceChantier
from rh_paie.models import SaisieTemps


def _etat():
    return {
        "affaires": Affaire.objects.count(), "of": OrdreFabrication.objects.count(),
        "pointages": PointageChantier.objects.count(), "presences": PresenceChantier.objects.count(),
        "affectations": AffectationEquipe.objects.count(), "temps": SaisieTemps.objects.count(),
    }


class ParcoursDemoLotATests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_all_demo", verbosity=0)

    def test_affaires_confirmees_generent_un_of_par_type(self):
        for titre, scope in (("atelier", "atelier"), ("chantier", "chantier")):
            affaire = Affaire.objects.get(title__startswith="Parcours demo", title__icontains=titre)
            self.assertEqual(affaire.status, Affaire.Status.EN_COURS)  # revue validée + CRRL tenu + démarrage
            self.assertEqual(OrdreFabrication.objects.get(affaire=affaire).scope, scope)
        gr = Affaire.objects.get(title__icontains="GLOBAL RENTAL")
        self.assertTrue(gr.is_global_rental)
        self.assertEqual(OrdreFabrication.objects.get(affaire=gr).status, OrdreFabrication.Status.LANCE)

    def test_of_chantier_demarre_grace_a_un_permis_hse_signe(self):
        of = OrdreFabrication.objects.get(affaire__title__icontains="chantier", scope="chantier")
        self.assertEqual(of.status, OrdreFabrication.Status.EN_COURS)
        permis = PermisTravail.objects.get(ordre=of)
        self.assertEqual(permis.statut, PermisTravail.Statut.ACTIF)
        self.assertEqual(len({permis.visa_superviseur_par_id, permis.visa_hse_par_id, permis.visa_dg_par_id}), 3)

    def test_pointages_dans_chaque_etat_dont_transfert_en_paie(self):
        statuts = set(PointageChantier.objects.filter(ordre__affaire__title__startswith="Parcours demo").values_list("status", flat=True))
        self.assertEqual(statuts, {"saisi", "valide", "transfere"})
        transfere = PointageChantier.objects.get(status="transfere")
        self.assertEqual(transfere.saisie_temps.heures, transfere.hours)

    def test_equipes_affectations_et_presences(self):
        self.assertTrue(AffectationEquipe.objects.filter(statut=AffectationEquipe.Statut.MOBILISEE).exists())
        self.assertEqual({p.statut for p in PresenceChantier.objects.filter(ordre__affaire__title__startswith="Parcours demo")},
                         {"present", "retard", "absent"})

    def test_surcharge_de_capacite_visible(self):
        self.assertTrue(any(a["scope"] == "atelier" and a["overload_pct"] > 0 for a in alertes_surcharge()))

    def test_seed_rejouable_sans_doublon(self):
        avant = _etat()
        call_command("seed_all_demo", verbosity=0)
        self.assertEqual(_etat(), avant)
