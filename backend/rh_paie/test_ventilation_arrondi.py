"""Ventilation analytique de la paie : les arrondis ne produisent jamais de ligne négative (écriture refusée sinon)."""

from decimal import Decimal

from django.test import SimpleTestCase

from rh_paie.compta_m9b import _ventiler


class VentilationArrondiTests(SimpleTestCase):
    def test_excedent_d_arrondi_repris_sur_la_derniere_affaire(self):
        tiers = Decimal(1) / Decimal(3)
        lignes = _ventiler(Decimal("150296.54"), [("A", tiers), ("B", tiers), ("C", tiers)])
        self.assertTrue(all(m > 0 for _, m in lignes))
        self.assertEqual(sum(m for _, m in lignes), Decimal("150296.54"))
        self.assertNotIn(None, [a for a, _ in lignes])

    def test_heures_hors_affaire_restent_sans_axe(self):
        lignes = _ventiler(Decimal("1000"), [("A", Decimal("0.6"))])
        self.assertEqual(lignes, [("A", Decimal("600.00")), (None, Decimal("400.00"))])
