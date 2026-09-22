from django.core.management.base import BaseCommand

from commercial.models import Affaire, ClientProfile, Opportunity
from operations.models import (
    GammeOperatoire,
    GammeOperation,
    OrdreFabrication,
    PointageChantier,
    SituationTravaux,
)
from referentiels.models import Article, Currency, Partner, UnitOfMeasure
from users.models import User


class Command(BaseCommand):
    help = "Seed démo module M3 — Opérations (atelier + chantier), idempotent."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Réinitialise puis reseed")

    def handle(self, *args, **options):
        if options["force"]:
            for model in (SituationTravaux, PointageChantier, OrdreFabrication,
                          GammeOperation, GammeOperatoire):
                model.objects.all().delete()

        currency, _ = Currency.objects.get_or_create(
            code="XAF", defaults={"label": "Franc CFA (BEAC)", "symbol": "FCFA", "decimals": 0}
        )
        unit, _ = UnitOfMeasure.objects.get_or_create(code="U", defaults={"label": "Unité"})
        article, _ = Article.objects.get_or_create(
            code="TUY-6",
            defaults={
                "label": "Tuyauterie DN200 (tube 6 m)",
                "article_type": Article.ArticleType.MATIERE,
                "unit": unit,
                "is_stockable": True,
            },
        )

        partner, _ = Partner.objects.get_or_create(
            code="CL-UGBS",
            defaults={"name": "UTG Boost Services", "kind": Partner.Kind.CLIENT, "currency": currency},
        )
        client, _ = ClientProfile.objects.get_or_create(
            partner=partner,
            defaults={"segment": "petrolier", "scoring": 85},
        )

        opp, _ = Opportunity.objects.get_or_create(
            subject="Tuyauterie gaz — site de production",
            defaults={"client": client, "amount": 120_000_000},
        )

        affaire, _ = Affaire.objects.get_or_create(
            code="AFF00001",
            defaults={
                "opportunity": opp,
                "client": client,
                "title": "Tuyauterie gaz — site de production",
                "affaire_type": Affaire.AffaireType.CHANTIER,
                "currency": currency,
                "contract_amount": 120_000_000,
            },
        )

        gamme, _ = GammeOperatoire.objects.get_or_create(
            code="GAM00001",
            defaults={"label": "Montage tuyauterie DN200", "status": GammeOperatoire.Status.ACTIVE},
        )
        default_ops = [
            (1, "Découpe & préparation des tubes", GammeOperation.Poste.DECOUPE, 8),
            (2, "Montage des supports", GammeOperation.Poste.MONTAGE, 12),
            (3, "Soudure bout à bout", GammeOperation.Poste.SOUDURE, 24),
            (4, "Contrôle & essais", GammeOperation.Poste.CONTRÔLE, 6),
        ]
        for seq, label, poste, hours in default_ops:
            GammeOperation.objects.get_or_create(
                gamme=gamme, sequence=seq,
                defaults={"label": label, "poste": poste, "planned_hours": hours},
            )

        of, _ = OrdreFabrication.objects.get_or_create(
            code="OF00001",
            defaults={
                "label": "Tuyauterie DN200 — lot principal",
                "affaire": affaire,
                "gamme": gamme,
                "scope": OrdreFabrication.Scope.CHANTIER,
                "article": article,
                "quantity": 1,
                "status": OrdreFabrication.Status.EN_COURS,
                "planned_start": "2026-09-01",
                "planned_end": "2026-10-15",
                "calculated_hours": 50,
            },
        )

        chef, _ = User.objects.get_or_create(
            email="demo.atelier@etsl.local",
            defaults={"first_name": "Ali", "last_name": "Diallo", "role": User.Role.CHEF_ATELIER},
        )
        PointageChantier.objects.get_or_create(
            code="PTS00001",
            defaults={
                "ordre": of,
                "worker": chef,
                "date": "2026-09-10",
                "hours": 8,
                "status": PointageChantier.Status.VALIDE,
            },
        )

        sit, created = SituationTravaux.objects.get_or_create(
            code="SIT00001",
            defaults={
                "affaire": affaire,
                "label": "Situation n°1 — travaux préparatoires",
                "period_start": "2026-09-01",
                "period_end": "2026-09-30",
                "amount": 18_000_000,
                "progress": 15,
                "status": SituationTravaux.Status.SOUMISE,
            },
        )
        if created:
            sit.ordres.add(of)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed M3 OK : gammes={GammeOperatoire.objects.count()} "
                f"OF={OrdreFabrication.objects.count()} "
                f"pointages={PointageChantier.objects.count()} "
                f"situations={SituationTravaux.objects.count()}"
            )
        )