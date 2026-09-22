"""Droits métier M8 — Maintenance & GMAO (RF-ERP-70…73).

Écriture : Maintenance (pivot 5.9.3), Opérations / Chef d'atelier, Logistique
(compteurs GR lecture seule), Projets, Direction. Montants (cost tracking)
masqués hors rôles autorisés (pattern RF-59, comme M2/M4/M5). Lecture :
tous utilisateurs authentifiés.
"""

from rest_framework.permissions import BasePermission

from users.models import User

MAINTENANCE_WRITE_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.DIRECTEUR_PROJETS,
    User.Role.DIRECTEUR_OPERATIONS,
    User.Role.MAINTENANCE,
    User.Role.LOGISTIQUE,
    User.Role.CHEF_ATELIER,
    User.Role.DIRECTION,
)

MAINTENANCE_AMOUNT_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.DIRECTEUR_PROJETS,
    User.Role.DIRECTEUR_OPERATIONS,
    User.Role.FINANCE,
    User.Role.COMPTABLE,
    User.Role.MAINTENANCE,
    User.Role.DIRECTION,
)


def is_admin_or_staff(user):
    return user.is_authenticated and (
        user.is_staff or user.is_superuser or user.role == User.Role.ADMIN
    )


def can_manage_maintenance(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in MAINTENANCE_WRITE_ROLES


def can_see_amount(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in MAINTENANCE_AMOUNT_ROLES


class CanManageMaintenance(BasePermission):
    """Lecture authentifiée, écriture réservée rôles Maintenance / opérationnels."""

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return bool(getattr(request, "user", None) and request.user.is_authenticated)
        return can_manage_maintenance(getattr(request, "user", None))