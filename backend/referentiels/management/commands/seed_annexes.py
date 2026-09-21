from django.core.management.base import BaseCommand
from django.db import transaction

from referentiels.models import Annexe

# Répartition des 270 annexes du MANUEL (ch.10) : nature × domaine.
# Totaux nature : F 108 / R 56 / M 55 / TS 51.
# Totaux domaine : ADM 35 · FIN 35 · TEC 54 · COM 32 · RH 42 · JUR 30 · HSE 42.
DISTRIBUTION = {
    Annexe.Kind.FORMULAIRE: {"ADM": 15, "FIN": 14, "TEC": 22, "COM": 13, "RH": 17, "JUR": 12, "HSE": 15},
    Annexe.Kind.REGISTRE: {"ADM": 8, "FIN": 8, "TEC": 11, "COM": 7, "RH": 9, "JUR": 6, "HSE": 7},
    Annexe.Kind.MODELE: {"ADM": 7, "FIN": 7, "TEC": 10, "COM": 6, "RH": 8, "JUR": 9, "HSE": 8},
    Annexe.Kind.TABLEAU: {"ADM": 5, "FIN": 6, "TEC": 11, "COM": 6, "RH": 8, "JUR": 3, "HSE": 12},
}

# Les 10 intitulés explicitement codifiés dans le MANUEL §10.4.
KNOWN_LABELS = {
    ("F", "ADM"): "Formulaire administratif",
    ("F", "FIN"): "Formulaire financier",
    ("F", "TEC"): "Formulaire technique",
    ("F", "COM"): "Formulaire commercial",
    ("F", "RH"): "Formulaire RH",
    ("F", "JUR"): "Formulaire juridique",
    ("F", "HSE"): "Formulaire HSE",
    ("R", "ADM"): "Registre administratif",
    ("M", "ADM"): "Modèle administratif",
    ("TS", "ADM"): "Tableau de suivi administratif",
}

KIND_LABELS = dict(Annexe.Kind.choices)
DOMAIN_LABELS = dict(Annexe.Domain.choices)


class Command(BaseCommand):
    """Crée / met à jour les 270 annexes du MANUEL (idempotent)."""

    help = "Seed des 270 annexes du MANUEL DE PROCEDURE ETSL (ch.10, §10.4)."

    @transaction.atomic
    def handle(self, *args, **options):
        created = updated = 0
        total = 0
        for kind, domains in DISTRIBUTION.items():
            for domain, count in domains.items():
                for index in range(1, count + 1):
                    code = f"ANN-{kind}-{domain}-{index:03d}"
                    base = KNOWN_LABELS.get(
                        (kind, domain),
                        f"{KIND_LABELS[kind]} {DOMAIN_LABELS[domain].lower()}",
                    )
                    label = base if index == 1 else f"{base} {index:03d}"
                    _, was_created = Annexe.objects.update_or_create(
                        code=code,
                        defaults={
                            "label": label,
                            "kind": kind,
                            "domain": domain,
                            "source_ref": f"MANUEL ch.10 (§10.4) — {code}",
                        },
                    )
                    created += int(was_created)
                    updated += int(not was_created)
                    total += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Annexes : {total} traitées ({created} créées, {updated} mises à jour)."
            )
        )
