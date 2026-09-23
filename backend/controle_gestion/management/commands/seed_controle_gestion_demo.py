from datetime import date, timedelta

from django.core.management.base import BaseCommand

from accounting_kernel.models import FiscalYear, Period
from referentiels.models import AnalyticAccount, AnalyticAxis


class Command(BaseCommand):
    """Seed du module M11 — budgets, révision, clôtures, marges (RF-ERP-A0..A4)."""

    help = "Peuple le contrôle de gestion : budget annuel, révision R1, clôtures, marges."

    def handle(self, *args, **options):
        from controle_gestion.models import (
            Budget,
            BudgetLigne,
            BudgetRevision,
            ClotureGestion,
        )

        fiscal_year = FiscalYear.objects.first()
        if fiscal_year is None:
            self.stdout.write(self.style.ERROR("Exercice absent — lancez seed_accounting."))
            return

        axis_proj = AnalyticAxis.objects.filter(code="AX-PROJ").first()
        axis_cc = AnalyticAxis.objects.filter(code="AX-CC").first()

        analytic_ch = None
        if axis_cc:
            analytic_ch, _ = AnalyticAccount.objects.get_or_create(
                axis=axis_cc,
                code="CC-TOLERIE",
                defaults={"label": "Centre de coût — Tôlerie / Chaudronnerie"},
            )
        analytic_aff = None
        if axis_proj:
            analytic_aff, _ = AnalyticAccount.objects.get_or_create(
                axis=axis_proj,
                code="AFF-2026-001",
                defaults={"label": "Affaire — Maintenance pipelines 2026"},
            )

        periods = {p.number: p for p in Period.objects.filter(fiscal_year=fiscal_year)}

        budget, created = Budget.objects.get_or_create(
            code="BUD-00001",
            defaults={
                "label": "Budget charges — Centre Tôlerie 2026",
                "type_budget": Budget.TypeBudget.CHARGE,
                "fiscal_year": fiscal_year,
                "axis": axis_cc,
                "analytic": analytic_ch,
                "montant": 15000000,
                "statut": Budget.Statut.APPROUVE,
            },
        )
        if created:
            for number, period in periods.items():
                BudgetLigne.objects.get_or_create(
                    budget=budget,
                    period=period,
                    defaults={"montant": 1250000},
                )

        budget_prod, created_prod = Budget.objects.get_or_create(
            code="BUD-00002",
            defaults={
                "label": "Budget produits — Affaire Maintenance pipelines",
                "type_budget": Budget.TypeBudget.PRODUIT,
                "fiscal_year": fiscal_year,
                "axis": axis_proj,
                "analytic": analytic_aff,
                "montant": 60000000,
                "statut": Budget.Statut.APPROUVE,
            },
        )
        if created_prod:
            for number, period in periods.items():
                BudgetLigne.objects.get_or_create(
                    budget=budget_prod,
                    period=period,
                    defaults={"montant": 5000000},
                )

        # Révision R1 : hausse de 10 % du budget de charges (RF-ERP-A1).
        BudgetRevision.objects.get_or_create(
            budget=budget,
            numero=1,
            defaults={
                "date_revision": date(2026, 4, 15),
                "ancien_montant": 15000000,
                "nouveau_montant": 16500000,
                "commentaire": "Révision R1 — hausse consommables soudure",
                "statut": BudgetRevision.Statut.APPLIQUEE,
            },
        )
        if budget.montant == 15000000:
            budget.montant = 16500000
            budget.save(update_fields=["montant", "updated_at"])

        # Clôtures de gestion : janvier réalisé J+2 (conforme), février en attente.
        p1 = periods.get(1)
        if p1:
            ClotureGestion.objects.get_or_create(
                code="CLO-00001",
                defaults={
                    "period": p1,
                    "date_cloture": p1.end_date + timedelta(days=2),
                    "statut": ClotureGestion.Statut.REALISEE,
                },
            )
        p2 = periods.get(2)
        if p2:
            ClotureGestion.objects.get_or_create(
                code="CLO-00002",
                defaults={"period": p2, "statut": ClotureGestion.Statut.EN_ATTENTE},
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Contrôle de gestion seedé : "
                + f"{Budget.objects.count()} budgets, "
                + f"{BudgetRevision.objects.count()} révision(s), "
                + f"{ClotureGestion.objects.count()} clôture(s)."
            )
        )