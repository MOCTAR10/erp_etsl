from django.core.management.base import BaseCommand
from django.utils import timezone

from referentiels.models import Annexe

from registres.models import Registre

# kind -> code d'annexe du MANUEL (§10.4) quand le registre est explicitement codifié.
ANNEXE_BY_KIND = {
    Registre.Kind.COURRIER: "ANN-R-ADM-001",
}


class Command(BaseCommand):
    """Crée les 9 registres / tableaux de suivi pour l'exercice courant."""

    help = "Peuple les 9 modules de registres (proposition §6.5, via MANUEL ch.10)."

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, default=None)

    def handle(self, *args, **options):
        year = options["year"] or timezone.now().year
        created = 0
        for kind, label in Registre.Kind.choices:
            code = ANNEXE_BY_KIND.get(kind)
            annexe = Annexe.objects.filter(code=code).first() if code else None
            _, was_created = Registre.objects.get_or_create(
                kind=kind,
                year=year,
                defaults={"label": label, "annexe": annexe, "is_active": True},
            )
            created += was_created
        self.stdout.write(
            self.style.SUCCESS(f"Terminé — {created} registre(s) créé(s) pour {year}.")
        )
