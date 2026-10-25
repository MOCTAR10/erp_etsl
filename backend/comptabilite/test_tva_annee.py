"""KPI TVA (audit premium B05) : les déclarations du mois sont calculées sur les écritures 443 / 445.

Le seed créait une déclaration jamais calculée : le KPI « TVA nette à payer » restait à 0 FCFA alors que la
balance portait de la TVA collectée. `calculer_declarations_annee` crée et calcule les déclarations des mois
mouvementés, sans jamais toucher aux écritures ni recalculer une déclaration déposée.
"""

from datetime import date
from decimal import Decimal

from accounting_kernel.models import AccountMove
from referentiels.models import Account

from .fiscal import calculer_declarations_annee
from .models import DeclarationTva
from .test_cloture_m10 import M10Base


class CalculDeclarationsAnneeTests(M10Base):
    def setUp(self):
        super().setUp()
        self.taux = self._taux_tva()
        self.collectee = Account.objects.get(code="443000")
        self.deductible = Account.objects.get(code="445000")

    def test_mois_mouvementes_calcules_sur_ecritures(self):
        self.move(date(2026, 3, 10), self.client_acc, self.collectee, "180000")
        self.move(date(2026, 3, 20), self.deductible, self.banque, "45000")
        self.move(date(2026, 5, 5), self.client_acc, self.collectee, "90000")
        nb_ecritures = AccountMove.objects.count()

        declarations = calculer_declarations_annee(2026)

        self.assertEqual([d.mois for d in declarations], [date(2026, 3, 1), date(2026, 5, 1)])
        mars = DeclarationTva.objects.get(mois=date(2026, 3, 1))
        self.assertEqual(mars.tva_collectee, Decimal("180000.00"))
        self.assertEqual(mars.tva_deductible, Decimal("45000.00"))
        self.assertEqual(mars.net_a_payer, Decimal("135000.00"))
        self.assertEqual(mars.source_calcul, DeclarationTva.SourceCalcul.ECRITURES)
        self.assertEqual(AccountMove.objects.count(), nb_ecritures)  # lecture seule

    def test_idempotent_et_declaration_deposee_intacte(self):
        self.move(date(2026, 3, 10), self.client_acc, self.collectee, "180000")
        calculer_declarations_annee(2026)
        mars = DeclarationTva.objects.get(mois=date(2026, 3, 1))
        DeclarationTva.objects.filter(pk=mars.pk).update(statut=DeclarationTva.Statut.DEPOSEE)
        self.move(date(2026, 3, 25), self.client_acc, self.collectee, "18000")

        calculer_declarations_annee(2026)

        self.assertEqual(DeclarationTva.objects.filter(mois=date(2026, 3, 1)).count(), 1)
        mars.refresh_from_db()
        self.assertEqual(mars.tva_collectee, Decimal("180000.00"))

    def test_brouillon_non_comptabilise_ignore(self):
        self.move(date(2026, 4, 10), self.client_acc, self.collectee, "180000", post=False)
        self.assertEqual(calculer_declarations_annee(2026), [])
