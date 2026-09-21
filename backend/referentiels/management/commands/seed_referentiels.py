from django.core.management.base import BaseCommand

from referentiels.models import (
    Account,
    AnalyticAxis,
    Article,
    Currency,
    Partner,
    UnitOfMeasure,
)

CURRENCIES = [
    ("XAF", "Franc CFA (BEAC)", "FCFA", 0),
    ("EUR", "Euro", "€", 2),
    ("USD", "Dollar américain", "$", 2),
]

UNITS = [
    ("U", "Unité"),
    ("ENS", "Ensemble"),
    ("KG", "Kilogramme"),
    ("T", "Tonne"),
    ("M", "Mètre"),
    ("M2", "Mètre carré"),
    ("M3", "Mètre cube"),
    ("L", "Litre"),
    ("H", "Heure"),
    ("J", "Jour"),
    ("FF", "Forfait"),
]

# Plan de comptes SYSCOHADA révisée — extrait opérationnel (comptes usuels ETSL).
# (code, intitulé, classe, nature)
ACCOUNTS = [
    ("101000", "Capital social", 1, Account.AccountType.EQUITY),
    ("106000", "Réserves", 1, Account.AccountType.EQUITY),
    ("110000", "Report à nouveau", 1, Account.AccountType.EQUITY),
    ("162000", "Emprunts", 1, Account.AccountType.LIABILITY),
    ("220000", "Terrains", 2, Account.AccountType.ASSET),
    ("230000", "Bâtiments", 2, Account.AccountType.ASSET),
    ("240000", "Matériel et outillage", 2, Account.AccountType.ASSET),
    ("244000", "Matériel de transport", 2, Account.AccountType.ASSET),
    ("310000", "Stocks de marchandises", 3, Account.AccountType.ASSET),
    ("320000", "Matières premières", 3, Account.AccountType.ASSET),
    ("330000", "Autres approvisionnements", 3, Account.AccountType.ASSET),
    ("401000", "Fournisseurs", 4, Account.AccountType.LIABILITY),
    ("401100", "Fournisseurs intra-groupe GLOBAL RENTAL", 4, Account.AccountType.LIABILITY),
    ("411000", "Clients", 4, Account.AccountType.ASSET),
    ("411100", "Clients intra-groupe GLOBAL RENTAL", 4, Account.AccountType.ASSET),
    ("421000", "Personnel — rémunérations dues", 4, Account.AccountType.LIABILITY),
    ("431000", "Sécurité sociale (CNSSG)", 4, Account.AccountType.LIABILITY),
    ("443000", "TVA collectée", 4, Account.AccountType.LIABILITY),
    ("445000", "TVA déductible", 4, Account.AccountType.ASSET),
    ("447000", "État et collectivités", 4, Account.AccountType.LIABILITY),
    ("512000", "Banques", 5, Account.AccountType.ASSET),
    ("571000", "Caisse", 5, Account.AccountType.ASSET),
    ("601000", "Achats de marchandises", 6, Account.AccountType.EXPENSE),
    ("602000", "Achats de matières premières", 6, Account.AccountType.EXPENSE),
    ("618000", "Refacturations intra-groupe GLOBAL RENTAL", 6, Account.AccountType.EXPENSE),
    ("624000", "Entretien et réparations", 6, Account.AccountType.EXPENSE),
    ("631000", "Frais bancaires", 6, Account.AccountType.EXPENSE),
    ("641000", "Impôts et taxes", 6, Account.AccountType.EXPENSE),
    ("661000", "Charges de personnel", 6, Account.AccountType.EXPENSE),
    ("681000", "Dotations aux amortissements", 6, Account.AccountType.EXPENSE),
    ("701000", "Ventes de produits", 7, Account.AccountType.INCOME),
    ("706000", "Services vendus / prestations", 7, Account.AccountType.INCOME),
    ("707000", "Produits accessoires", 7, Account.AccountType.INCOME),
    ("718000", "Refacturations intra-groupe (produit)", 7, Account.AccountType.INCOME),
    ("811000", "Valeurs comptables des cessions", 8, Account.AccountType.EXPENSE),
    ("821000", "Produits des cessions", 8, Account.AccountType.INCOME),
]

# Axes analytiques (M11) — référentiel multi-axes.
AXES = [
    ("AX-PROJ", "Projet / affaire", AnalyticAxis.AxisType.PROJET),
    ("AX-CHANT", "Chantier", AnalyticAxis.AxisType.CHANTIER),
    ("AX-CC", "Centre de coût", AnalyticAxis.AxisType.CENTRE_COUT),
    ("AX-SITE", "Site", AnalyticAxis.AxisType.SITE),
]


class Command(BaseCommand):
    """Peuple le noyau partagé : devises, unités, plan SYSCOHADA, axes, tiers GR."""

    help = "Seed du référentiel transverse (PLAN §10.3, incrément 14)."

    def handle(self, *args, **options):
        counters = {"devises": 0, "unités": 0, "comptes": 0, "axes": 0, "tiers": 0}

        for code, label, symbol, decimals in CURRENCIES:
            _, created = Currency.objects.update_or_create(
                code=code,
                defaults={"label": label, "symbol": symbol, "decimals": decimals},
            )
            counters["devises"] += created

        for code, label in UNITS:
            _, created = UnitOfMeasure.objects.update_or_create(
                code=code, defaults={"label": label}
            )
            counters["unités"] += created

        for code, label, account_class, account_type in ACCOUNTS:
            _, created = Account.objects.update_or_create(
                code=code,
                defaults={
                    "label": label,
                    "account_class": account_class,
                    "account_type": account_type,
                },
            )
            counters["comptes"] += created

        for code, label, axis_type in AXES:
            _, created = AnalyticAxis.objects.update_or_create(
                code=code, defaults={"label": label, "axis_type": axis_type}
            )
            counters["axes"] += created

        xaf = Currency.objects.filter(code="XAF").first()
        _, created = Partner.objects.update_or_create(
            code="GR-0001",
            defaults={
                "name": "GLOBAL RENTAL",
                "kind": Partner.Kind.BOTH,
                "currency": xaf,
                "is_global_rental": True,
            },
        )
        counters["tiers"] += created

        self.stdout.write(
            self.style.SUCCESS(
                "Terminé — "
                + ", ".join(f"{value} {name}" for name, value in counters.items())
                + f" créé(s) (articles : {Article.objects.count()} en base)."
            )
        )
