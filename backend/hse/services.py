"""Droits métier M7 (RF-ERP-60…63) + helpers workflow HSE.

Écriture : Management HSE (pivot 9.3.3 / 9.6.3), Direction des Opérations,
appui RH (formations & EPI, 9.7.3), Logistique (déchets/BSD), Maintenance,
Chefs d'atelier/chantier, Direction, Projets (permis). Validation des permis
et enquêtes incidents = HSE + hiérarchie. Lecture : tous les utilisateurs
authentifiés. Aucun montant financier → pas de masquage.
"""

from rest_framework.permissions import BasePermission

from users.models import User
from users.rbac import can_read_app

HSE_WRITE_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.DIRECTEUR_PROJETS,
    User.Role.DIRECTEUR_OPERATIONS,
    User.Role.HSE,
    User.Role.RH,
    User.Role.LOGISTIQUE,
    User.Role.MAINTENANCE,
    User.Role.CHEF_ATELIER,
    User.Role.DIRECTION,
)

# Validation permis + enquêtes : HSE + hiérarchie opérationnelle.
HSE_VALIDATION_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.DIRECTEUR_PROJETS,
    User.Role.DIRECTEUR_OPERATIONS,
    User.Role.HSE,
    User.Role.DIRECTION,
)


def is_admin_or_staff(user):
    return user.is_authenticated and (
        user.is_staff or user.is_superuser or user.role == User.Role.ADMIN
    )


def can_manage_hse(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in HSE_WRITE_ROLES


def can_validate_hse(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in HSE_VALIDATION_ROLES


class CanManageHse(BasePermission):
    """Lecture authentifiée, écriture réservée rôles HSE / opérationnels / RH."""

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return can_read_app(getattr(request, "user", None), "hse")
        return can_manage_hse(getattr(request, "user", None))


class CanValidateHse(BasePermission):
    """Validation permis / clôture incidents : HSE + hiérarchie."""

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return can_read_app(getattr(request, "user", None), "hse")
        return can_validate_hse(getattr(request, "user", None))


# Signataires de chaque niveau du permis de travail (CDC M7 §9.4). L'administrateur peut signer UN niveau.
PERMIS_SIGNATAIRES = {
    "superviseur": (User.Role.CHEF_ATELIER, User.Role.DIRECTEUR_OPERATIONS, User.Role.DIRECTEUR_PROJETS),
    "hse": (User.Role.HSE,),
    "dg": (User.Role.PDG,),
}
PERMIS_NIVEAU_LIBELLES = {"superviseur": "superviseur", "hse": "HSE", "dg": "Direction Générale"}


def peut_signer_niveau(user, niveau):
    if not (user and user.is_authenticated):
        return False
    return user.is_staff or user.role == User.Role.ADMIN or user.role in PERMIS_SIGNATAIRES.get(niveau, ())


def habilitations_manquantes(permis, jour=None):
    """Intervenants du permis sans qualification RH valide pour une exigence de son type (« aucun départ sans habilitation »).

    Retourne la liste des « Nom : mot-clé » manquants. Une qualification sans date de validité ne périme pas.
    """
    from django.db.models import Q
    from django.utils import timezone

    from .models import ExigenceHabilitation

    jour = jour or timezone.localdate()
    exigences = list(ExigenceHabilitation.objects.filter(type_permis=permis.type_permis, actif=True))
    manquantes = []
    for emp in permis.intervenants.all():
        for ex in exigences:
            ok = emp.qualifications.filter(intitule__icontains=ex.mot_cle).filter(
                Q(date_validite__isnull=True) | Q(date_validite__gte=jour)
            ).exists()
            if not ok:
                manquantes.append(f"{emp.nom_complet} : {ex.mot_cle}")
    return manquantes
