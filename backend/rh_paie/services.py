"""Droits métier M9 — RH & Paie (RF-ERP-80…83).

RH : cercle personnel (contrats, congés, formations, sanctions, habilitations).
Paie : cercle restreint (bulletins, salaires) — la paie est sensible (RF-33).
Montants (salaire, brut, net) masqués hors rôles autorisés (pattern RF-59).
"""

from rest_framework.permissions import BasePermission

from users.models import User

RH_WRITE_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.SECRETAIRE_GENERAL,
    User.Role.DIRECTEUR_PROJETS,
    User.Role.DIRECTEUR_OPERATIONS,
    User.Role.RH,
    User.Role.CHEF_ATELIER,
    User.Role.DIRECTION,
)

# Paie = cercle restreint : RH (pivot), Finance/Compta, Direction.
PAIE_WRITE_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.RH,
    User.Role.FINANCE,
    User.Role.DIRECTION,
)

PAIE_AMOUNT_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.RH,
    User.Role.FINANCE,
    User.Role.COMPTABLE,
    User.Role.DIRECTION,
)


def is_admin_or_staff(user):
    return user.is_authenticated and (
        user.is_staff or user.is_superuser or user.role == User.Role.ADMIN
    )


def can_manage_rh(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in RH_WRITE_ROLES


def can_manage_paie(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in PAIE_WRITE_ROLES


def can_see_amount(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in PAIE_AMOUNT_ROLES


class CanManageRh(BasePermission):
    """Lecture authentifiée, écriture réservée au cercle RH (can_manage_rh)."""

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return bool(getattr(request, "user", None) and request.user.is_authenticated)
        return can_manage_rh(getattr(request, "user", None))


class CanManagePaie(BasePermission):
    """Endpoint paie (bulletins/temps) — cercle restreint RH / Finance / Direction."""

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return can_manage_paie(getattr(request, "user", None))
        return can_manage_paie(getattr(request, "user", None))