"""Droits métier M7 (RF-ERP-60…63) + helpers workflow HSE.

Écriture : Management HSE (pivot 9.3.3 / 9.6.3), Direction des Opérations,
appui RH (formations & EPI, 9.7.3), Logistique (déchets/BSD), Maintenance,
Chefs d'atelier/chantier, Direction, Projets (permis). Validation des permis
et enquêtes incidents = HSE + hiérarchie. Lecture : tous les utilisateurs
authentifiés. Aucun montant financier → pas de masquage.
"""

from rest_framework.permissions import BasePermission

from users.models import User

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
            return bool(getattr(request, "user", None) and request.user.is_authenticated)
        return can_manage_hse(getattr(request, "user", None))


class CanValidateHse(BasePermission):
    """Validation permis / clôture incidents : HSE + hiérarchie."""

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return bool(getattr(request, "user", None) and request.user.is_authenticated)
        return can_validate_hse(getattr(request, "user", None))