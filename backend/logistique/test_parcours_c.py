"""Recette « parcours démo » lot C : GR (grille versionnée, retour en retard, préventif M8), qualité M6, HSE M7, stocks —
tout rejoué par l'API réelle depuis `seed_all_demo`."""

from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase

from hse.models import AuditHse, Duer, ExigenceHabilitation, PlanUrgence
from logistique.models import LocationGR, TarifGR
from maintenance.models import OrdreTravail, PlanPreventif
from operations.models import OrdreFabrication
from qualite.models import ControleQualite, EpreuvePression, InstrumentMesure, JointSoude
from stocks.models import MouvementStock


def _etat():
    return {
        "tarifs": TarifGR.objects.count(), "locations": LocationGR.objects.count(), "plans": PlanPreventif.objects.count(),
        "ot": OrdreTravail.objects.count(), "controles": ControleQualite.objects.count(), "joints": JointSoude.objects.count(),
        "instruments": InstrumentMesure.objects.count(), "duer": Duer.objects.count(), "audits": AuditHse.objects.count(),
        "exigences": ExigenceHabilitation.objects.count(), "plans_urgence": PlanUrgence.objects.count(),
        "mvts": MouvementStock.objects.count(),
    }


class ParcoursDemoLotCTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_all_demo", verbosity=0)

    def test_grille_gr_versionnee_et_retour_en_retard_penalise(self):
        self.assertEqual(sorted(TarifGR.objects.values_list("version", flat=True)), [1, 2])
        loc = LocationGR.objects.get(equipement__code="PAR00009")
        self.assertEqual(loc.statut, LocationGR.Statut.TERMINEE)
        self.assertEqual(loc.tarif_gr.version, 2)  # version en vigueur a la date de debut
        self.assertEqual(loc.jours_retard, 3)
        self.assertEqual(loc.penalite, 3 * loc.tarif_gr.penalite_jour)
        self.assertTrue(loc.imputation_618)

    def test_retour_gr_declenche_l_ot_preventif_m8(self):
        plan = PlanPreventif.objects.get(actif__equipement_gr__code="PAR00009")
        ot = OrdreTravail.objects.get(plan=plan)
        self.assertEqual((ot.type_ot, ot.statut), ("preventif", "planifie"))
        self.assertEqual(plan.actif.compteur_lecture, Decimal("900.00"))

    def test_of_atelier_libere_apres_itp_joints_cnd_et_epreuve(self):
        of = OrdreFabrication.objects.get(affaire__title__icontains="supports")
        self.assertEqual(of.status, OrdreFabrication.Status.CLOTURE)
        itp = ControleQualite.objects.get(ordre=of, type_controle="itp")
        self.assertIsNotNone(itp.approuve_le)
        self.assertEqual(set(itp.points.values_list("statut", flat=True)), {"leve"})
        self.assertEqual(of.joints.count(), 2)
        self.assertEqual(ControleQualite.objects.get(ordre=of, type_controle="cnd").methode_cnd, "RT")
        self.assertEqual(EpreuvePression.objects.get(ordre=of).resultat, "conforme")

    def test_instruments_en_service_a_echeance_proche_et_bloque(self):
        statuts = set(InstrumentMesure.objects.filter(numero_serie__contains="DEMO").values_list("statut", flat=True))
        self.assertEqual(statuts, {"actif", "bloque"})

    def test_hse_exigences_duer_approuve_audit_cloture_et_plan_urgence(self):
        self.assertTrue(ExigenceHabilitation.objects.filter(type_permis="chaud", mot_cle="soudage").exists())
        self.assertEqual(Duer.objects.get(perimetre__contains="demo").statut, Duer.Statut.APPROUVE)
        self.assertEqual(set(AuditHse.objects.filter(zone__contains="demo").values_list("statut", flat=True)), {"cloture", "planifie"})
        self.assertTrue(PlanUrgence.objects.get(intitule__contains="demo").exercices.exists())

    def test_stocks_transfert_et_consommation_imputee_a_l_of(self):
        conso = MouvementStock.objects.get(document_reference="Parcours demo - consommation")
        self.assertEqual((conso.type_mouvement, conso.executed), ("consommation", True))
        self.assertTrue(conso.ordre_id)
        self.assertTrue(MouvementStock.objects.get(document_reference="Parcours demo - transfert").executed)

    def test_seed_rejouable_sans_doublon(self):
        avant = _etat()
        call_command("seed_all_demo", verbosity=0)
        self.assertEqual(_etat(), avant)
