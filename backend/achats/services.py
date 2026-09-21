"""Droits métier M2 (RF-ERP-10…13).

Écriture : rôles Achats/Logistique, Opérations, Finance (validation M2) + Direction.
Montants : restreints hors rôles autorisés (même logique que RF-59).
"""

from rest_framework.permissions import BasePermission

from users.models import User

ACHAT_WRITE_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.SECRETAIRE_GENERAL,
    User.Role.DIRECTEUR_PROJETS,
    User.Role.DIRECTEUR_OPERATIONS,
    User.Role.FINANCE,
    User.Role.LOGISTIQUE,
    User.Role.CHEF_ATELIER,
    User.Role.DIRECTION,
)

ACHAT_AMOUNT_ROLES = (
    User.Role.ADMIN,
    User.Role.COMPTABLE,
    User.Role.FINANCE,
    User.Role.LOGISTIQUE,
    User.Role.DIRECTEUR_PROJETS,
    User.Role.DIRECTEUR_OPERATIONS,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.DIRECTION,
)


def is_admin_or_staff(user):
    return user.is_authenticated and (
        user.is_staff or user.is_superuser or user.role == User.Role.ADMIN
    )


def can_manage_achats(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in ACHAT_WRITE_ROLES


def can_see_amount(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in ACHAT_AMOUNT_ROLES


class CanManageAchats(BasePermission):
    """Écriture réservée aux rôles Achats / Finance / Direction."""

    def has_permission(self, request, view):
        return can_manage_achats(getattr(request, "user", None))