from django.core.management.base import BaseCommand

from documents.models import DocumentType


class Command(BaseCommand):
    """Crée les types de documents ETSL avec leurs durées de rétention (spec §3.1)."""

    help = "Peuple la table des types de documents (durées de rétention du spec §3.1)."

    TYPES = [
        # code, label, retention_years, restricted_rh, circuit
        ("factures_fournisseurs", "Factures fournisseurs", 10, False, "circuit_comptabilite"),
        ("devis_bons_de_commande", "Devis / Bons de commande", 5, False, "circuit_controle_gestion"),
        ("contrats", "Contrats clients / fournisseurs / prêts", 5, False, "circuit_controle_gestion"),
        ("bulletins_de_paie", "Bulletins de paie", 3, True, None),
        ("documents_rh", "Documents RH (CV, contrats, absences)", 1, True, None),
        ("courriers", "Courriers entrants / sortants", None, False, "circuit_reception"),
        ("comptes_rendus_reunion", "Comptes rendus de réunion", None, False, "circuit_reception"),
        ("documents_techniques_plans", "Documents techniques / plans", 5, False, None),
        ("documents_qualite_iso", "Documents qualité / ISO", 5, False, None),
        ("documents_juridiques", "Documents juridiques (actes, statuts, PV)", 10, False, None),
        ("documents_bancaires", "Documents bancaires (relevés, traites)", 10, False, None),
        ("documents_douaniers_transport", "Documents douaniers / transport", 10, False, None),
        ("bordereaux_caisse_tickets", "Bordereaux de caisse / tickets", 10, False, None),
    ]

    def handle(self, *args, **options):
        from workflow.models import Circuit

        created = 0
        for code, label, retention_years, restricted_rh, circuit_code in self.TYPES:
            circuit = None
            if circuit_code:
                circuit = Circuit.objects.filter(code=circuit_code).first()
            _, was_created = DocumentType.objects.get_or_create(
                code=code,
                defaults={
                    "label": label,
                    "retention_years": retention_years,
                    "is_restricted_rh": restricted_rh,
                    "circuit": circuit,
                },
            )
            created += was_created
        self.stdout.write(
            self.style.SUCCESS(f"Terminé — {created} type(s) de document créé(s).")
        )
