from django.core.management.base import BaseCommand
from django.utils import timezone

from referentiels.models import Article, Currency, Partner, UnitOfMeasure
from users.models import User

from commercial.models import (
    Affaire,
    ClientProfile,
    Contract,
    ContractService,
    Estimate,
    EstimateLine,
    EstimateOption,
    Milestone,
    Opportunity,
    SoumissionEvent,
    TenderReview,
)

USER_EMAIL = "demo.projets@etls.local"
CLIENTS = [
    ("PGR-001", "PétroGabon SA", "petrole_gaz", 95, "appel_offres"),
    ("OCE-001", "OCE Gabon", "industrie", 80, "relation"),
    ("SOG-001", "SOGACOM", "construction", 65, "marche"),
]


class Command(BaseCommand):
    help = "Seed de démonstration du module Commercial (M1) — idempotent."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Réinitialise puis reseed")

    def handle(self, *args, **options):
        if options["force"]:
            for model in (SoumissionEvent, ContractService, Contract, Milestone, Affaire,
                          TenderReview, EstimateOption, EstimateLine, Estimate, Opportunity,
                          ClientProfile):
                model.objects.all().delete()

        currency, _ = Currency.objects.get_or_create(
            code="XAF", defaults={"label": "Franc CFA (BEAC)", "symbol": "FCFA", "decimals": 0}
        )
        unit, _ = UnitOfMeasure.objects.get_or_create(
            code="U", defaults={"label": "Unité"}
        )

        owner, _ = User.objects.get_or_create(
            email=USER_EMAIL, defaults={"role": User.Role.DIRECTEUR_PROJETS}
        )

        partners = {}
        profiles = {}
        for code, name, segment, scoring, origin in CLIENTS:
            partner, _ = Partner.objects.get_or_create(
                code=code, defaults={"name": name, "kind": Partner.Kind.CLIENT, "currency": currency}
            )
            profile, created = ClientProfile.objects.get_or_create(
                partner=partner,
                defaults={
                    "segment": segment,
                    "scoring": scoring,
                    "origin": origin,
                    "last_contact": timezone.localdate(),
                    "next_contact": timezone.localdate() + timezone.timedelta(days=30),
                    "contacts": {"commercial": "Stéphane M.", "technique": "J. Nkoghe"},
                },
            )
            partners[code] = partner
            profiles[code] = profile

        today = timezone.localdate()

        demo_opportunities = [
            ("Prospection — pôle Ogoué", "prospection", 25_000_000, 15, profiles["PGR-001"], "relation"),
            ("Maintenance GPL 2026", "qualification", 90_000_000, 40, profiles["OCE-001"], "marche"),
            ("Fourniture potelets Atelier 2026", "offre", 45_000_000, 70, profiles["SOG-001"], "appel_offres"),
            ("Travaux génie civil GBA", "negociation", 380_000_000, 80, profiles["PGR-001"], "appel_offres"),
            ("Renouvellement contrat soudage", "gagne", 210_000_000, 100, profiles["PGR-001"], "marche"),
        ]
        opportunities = {}
        for subject, stage, amount, prob, client, origin in demo_opportunities:
            opp, _ = Opportunity.objects.get_or_create(
                subject=subject,
                defaults={
                    "client": client,
                    "stage": stage,
                    "amount": amount,
                    "probability": prob,
                    "origin": origin,
                    "owner": owner,
                    "expected_close": today + timezone.timedelta(days=45),
                },
            )
            opportunities[opp.code] = opp

        estimate, _ = Estimate.objects.get_or_create(
            title="Travaux génie civil GBA — offre pluriannuelle",
            defaults={
                "opportunity": next(o for o in opportunities.values() if o.stage == "negociation"),
                "client": profiles["PGR-001"],
                "status": Estimate.Status.BROUILLON,
                "currency": currency,
                "total": 380_000_000,
                "margin": 42_000_000,
                "valid_until": today + timezone.timedelta(days=60),
                "created_by": owner,
            },
        )
        EstimateOption.objects.get_or_create(
            estimate=estimate,
            label="Option A — durée 24 mois",
            defaults={"amount": 380_000_000, "duration_months": 24, "is_selected": True},
        )
        EstimateOption.objects.get_or_create(
            estimate=estimate,
            label="Option B — durée 36 mois",
            defaults={"amount": 545_000_000, "duration_months": 36, "notes": "Périmètre étendu"},
        )
        article, _ = Article.objects.get_or_create(
            code="GR-0001", defaults={"label": "Location grue (GLOBAL RENTAL)",
                                      "article_type": Article.ArticleType.SERVICE, "unit": unit}
        )
        EstimateLine.objects.get_or_create(
            estimate=estimate, label="Location grue 25t", defaults={
                "article": article, "quantity": 6, "unit": unit, "unit_price": 3_500_000,
            },
        )

        TenderReview.objects.get_or_create(
            tender_ref="AO-2026-014",
            defaults={
                "estimate": estimate,
                "client": partners["PGR-001"],
                "bid_deadline": today + timezone.timedelta(days=12),
                "review_status": TenderReview.Status.EN_COURS,
                "requirements": ["Préqualification", "Plan assurance qualité", "Références 3 ans"],
                "reviewed_by": owner,
            },
        )

        won = next(o for o in opportunities.values() if o.stage == "gagne")
        affaire, _ = Affaire.objects.get_or_create(
            code="AFF-00001",
            defaults={
                "opportunity": won,
                "client": profiles["PGR-001"],
                "title": "Contrat soudage ateliers 2026",
                "affaire_type": Affaire.AffaireType.ATELIER,
                "status": Affaire.Status.EN_COURS,
                "contract_amount": 210_000_000,
                "margin": 24_000_000,
                "currency": currency,
                "start_date": today - timezone.timedelta(days=60),
                "end_date": today + timezone.timedelta(days=210),
            },
        )
        Milestone.objects.get_or_create(
            affaire=affaire, label="Mobilisation équipes",
            defaults={"planned_date": today - timezone.timedelta(days=30),
                      "actual_date": today - timezone.timedelta(days=28), "progress": 100},
        )
        Milestone.objects.get_or_create(
            affaire=affaire, label="Revue de commande",
            defaults={"planned_date": today + timezone.timedelta(days=15), "progress": 15},
        )

        contract, _ = Contract.objects.get_or_create(
            code="CTT-00001",
            defaults={
                "affaire": affaire,
                "client": profiles["PGR-001"],
                "profile": Contract.Profile.MARCHE_TRAVAUX,
                "start_date": today - timezone.timedelta(days=60),
                "end_date": today + timezone.timedelta(days=270),
                "months": 18,
                "amount_initial": 210_000_000,
                "currency": currency,
                "retenue_rate": 5,
                "indexation": True,
                "status": Contract.Status.ACTIF,
            },
        )
        ContractService.objects.get_or_create(
            contract=contract, label="Souffleuse atelier",
            defaults={"kind": ContractService.Kind.FORFAIT, "price": 2_500_000,
                      "frequency": ContractService.Frequency.MENSUEL},
        )

        SoumissionEvent.objects.get_or_create(
            estimate=estimate, kind=SoumissionEvent.Kind.CLARIFICATION,
            happened_at=today - timezone.timedelta(days=3),
            defaults={"content": "Réponse aux questions techniques transmises au client.",
                      "author": owner},
        )

        self.stdout.write(self.style.SUCCESS(
            f"Commercial M1 prêt : {len(profiles)} clients, "
            f"{Opportunity.objects.count()} opportunités, 1 affaire, 1 contrat CLM."
        ))