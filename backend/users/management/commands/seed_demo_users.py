from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    """Crée des utilisateurs de démonstration, un par rôle ETSL (RF-62)."""

    help = "Crée un utilisateur de démonstration par rôle ETSL."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="Etls#Demo2026",
            help="Mot de passe commun des comptes de démonstration.",
        )

    def handle(self, *args, **options):
        password = options["password"]
        accounts = [
            ("admin@etls.local", "Admin", "ETSL", User.Role.ADMIN, True),
            ("direction@etls.local", "Direction", "ETSL", User.Role.DIRECTION, False),
            ("service@etls.local", "Chef", "Service", User.Role.CHEF_SERVICE, False),
            ("compta@etls.local", "Comptable", "ETSL", User.Role.COMPTABLE, False),
            ("rh@etls.local", "RH", "ETSL", User.Role.RH, False),
        ]
        created = 0
        for email, first_name, last_name, role, is_staff in accounts:
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
