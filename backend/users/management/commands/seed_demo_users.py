from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    """Crée des utilisateurs de démonstration : 12 fonctions ETSL + admin (RF-62)."""

    help = "Crée un utilisateur de démonstration par fonction ETSL (12) + admin."

    # (email, prénom, nom, rôle, is_staff)
    ACCOUNTS = [
        ("admin@etls.local", "Admin", "ETSL", User.Role.ADMIN, True),
        # 12 fonctions du MANUEL (ch.2)
        ("pdg@etls.local", "PDG", "ETSL", User.Role.PDG, False),
        ("dga@etls.local", "DGA", "ETSL", User.Role.DGA, False),
        ("secretariat@etls.local", "Secrétariat", "Général", User.Role.SECRETAIRE_GENERAL, False),
        ("projets@etls.local", "Directeur", "Projets", User.Role.DIRECTEUR_PROJETS, False),
        ("operations@etls.local", "Directeur", "Opérations", User.Role.DIRECTEUR_OPERATIONS, False),
        ("rh@etls.local", "Ressources", "Humaines", User.Role.RH, False),
        ("finance@etls.local", "Finance", "ETSL", User.Role.FINANCE, False),
        ("qaqc@etls.local", "QA", "QC", User.Role.QAQC, False),
        ("hse@etls.local", "HSE", "ETSL", User.Role.HSE, False),
        ("logistique@etls.local", "Logistique", "Magasin", User.Role.LOGISTIQUE, False),
        ("maintenance@etls.local", "Maintenance", "ETSL", User.Role.MAINTENANCE, False),
        ("atelier@etls.local", "Chef", "Atelier", User.Role.CHEF_ATELIER, False),
        # Codes hérités (rétro-compatibilité de la matrice RBAC)
        ("direction@etls.local", "Direction", "ETSL", User.Role.DIRECTION, False),
        ("service@etls.local", "Chef", "Service", User.Role.CHEF_SERVICE, False),
        ("compta@etls.local", "Comptable", "ETSL", User.Role.COMPTABLE, False),
    ]

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="Etls#Demo2026",
            help="Mot de passe commun des comptes de démonstration.",
        )

    def handle(self, *args, **options):
        password = options["password"]
        created = 0
        for email, first_name, last_name, role, is_staff in self.ACCOUNTS:
            user, was_created = User.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "role": role,
                    "is_staff": is_staff,
                },
            )
            if was_created:
                user.set_password(password)
                user.save()
                created += 1
                self.stdout.write(self.style.SUCCESS(f"Créé : {email} ({role})"))
            else:
                self.stdout.write(f"Existe déjà : {email}")
        self.stdout.write(self.style.SUCCESS(f"Terminé — {created} utilisateur(s) créé(s)."))
