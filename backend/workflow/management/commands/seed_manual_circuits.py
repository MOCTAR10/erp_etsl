from django.core.management.base import BaseCommand

from workflow.models import Circuit, CircuitStep

# 4 circuits de validation du MANUEL (ch.2) — cf. SPEC §8.4 (RF-ERP-W1 à RF-ERP-W4).
# Les étapes seront déclinées finement par processus métier dans les incréments modules.
CIRCUITS = [
    (
        "circuit_adm_fin",
        "Circuit administratif-financier (RF-ERP-W1)",
        5,
        [
            (1, "Réception / enregistrement", "secretaire_general", 1),
            (2, "Contrôle budgétaire et comptable", "finance", 2),
            (3, "Approbation", "dga", 2),
        ],
    ),
    (
        "circuit_technique",
        "Circuit technique (RF-ERP-W2)",
        8,
        [
            (1, "Préparation technique", "directeur_projets", 2),
            (2, "Contrôle qualité / soudage", "qaqc", 2),
            (3, "Validation opérations", "directeur_operations", 2),
        ],
    ),
    (
        "circuit_commercial",
        "Circuit commercial (RF-ERP-W3)",
        6,
        [
            (1, "Élaboration de l'offre", "directeur_projets", 2),
            (2, "Validation des conditions financières", "finance", 2),
            (3, "Approbation", "dga", 2),
        ],
    ),
    (
        "circuit_rh",
        "Circuit RH (RF-ERP-W4)",
        6,
        [
            (1, "Instruction du dossier", "rh", 2),
            (2, "Contrôle paie / budget", "finance", 2),
            (3, "Validation", "dga", 2),
        ],
    ),
]


class Command(BaseCommand):
    """Crée les 4 circuits de validation du MANUEL (RF-ERP-W1 à RF-ERP-W4)."""

    help = "Peuple les 4 circuits du MANUEL (administratif-financier, technique, commercial, RH)."

    def handle(self, *args, **options):
        created = 0
        for code, label, max_days, steps in CIRCUITS:
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
