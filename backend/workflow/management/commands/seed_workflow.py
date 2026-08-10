from django.core.management.base import BaseCommand

from workflow.models import Circuit, CircuitStep


class Command(BaseCommand):
    """Crée les 3 circuits de validation ETSL (RF-29 à 31) et leurs étapes."""

    help = "Peuple les circuits de validation (spec §2.3, RF-29 à 31)."

    CIRCUITS = [
        (
            "circuit_reception",
            "Réception / Secrétariat",
            1,
            [
                (1, "Réception", "chef_service", 1),
                (2, "Transmission au Contrôle de gestion & Achats", "comptable", 1),
            ],
        ),
        (
            "circuit_controle_gestion",
            "Contrôle de Gestion",
            4,
            [
                (1, "Réception", "chef_service", 1),
                (2, "Imputation budget", "comptable", 2),
                (3, "Code budget", "comptable", 2),
            ],
        ),
        (
            "circuit_comptabilite",
            "Comptabilité",
            5,
            [
                (1, "Réception", "chef_service", 1),
                (2, "Saisie", "comptable", 2),
                (3, "Validation saisie (chef comptable)", "admin", 2),
            ],
        ),
    ]

    def handle(self, *args, **options):
        created = 0
        for code, label, max_days, steps in self.CIRCUITS:
            circuit, was_created = Circuit.objects.get_or_create(
                code=code,
                defaults={"label": label, "max_days": max_days, "is_active": True},
            )
            created += was_created
            for order, name, role, step_days in steps:
                _, step_created = CircuitStep.objects.get_or_create(
                    circuit=circuit,
                    order=order,
                    defaults={"name": name, "actor_role": role, "max_days": step_days},
                )
                created += step_created
        self.stdout.write(
            self.style.SUCCESS(f"Terminé — {created} circuit(s)/étape(s) créé(s).")
        )
