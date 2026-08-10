from django.core.management.base import BaseCommand

from documents.models import DocumentType


class Command(BaseCommand):
    """Crée les types de documents ETSL avec leurs durées de rétention (spec §3.1)."""

    help = "Peuple la table des types de documents (durées de rétention du spec §3.1)."

    TYPES = [
        ("factures_fournisseurs", "Factures fournisseurs", 10, False),
        ("devis_bons_de_commande", "Devis / Bons de commande", 5, False),
        ("contrats", "Contrats clients / fournisseurs / prêts", 5, False),
        ("bulletins_de_paie", "Bulletins de paie", 3, True),
        ("documents_rh", "Documents RH (CV, contrats, absences)", 1, True),
        ("courriers", "Courriers entrants / sortants", None, False),
        ("comptes_rendus_reunion", "Comptes rendus de réunion", None, False),
        ("documents_techniques_plans", "Documents techniques / plans", 5, False),
        ("documents_qualite_iso", "Documents qualité / ISO", 5, False),
        ("documents_juridiques", "Documents juridiques (actes, statuts, PV)", 10, False),
        ("documents_bancaires", "Documents bancaires (relevés, traites)", 10, False),
        ("documents_douaniers_transport", "Documents douaniers / transport", 10, False),
        ("bordereaux_caisse_tickets", "Bordereaux de caisse / tickets", 10, False),
    ]

    def handle(self, *args, **options):
        created = 0
        for code, label, retention_years, restricted_rh in self.TYPES:
            _, was_created = DocumentType.objects.get_or_create(
                code=code,
                defaults={
                    "label": label,
                    "retention_years": retention_years,
                    "is_restricted_rh": restricted_rh,
                },
            )
            created += was_created
        self.stdout.write(
            self.style.SUCCESS(f"Terminé — {created} type(s) de document créé(s).")
        )
