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


# Approbation d'une DA (validation hiérarchique avant consultation / commande) : hiérarchie + Finance.
# Logistique et chef d'atelier SAISISSENT des DA mais ne les approuvent pas. Liste à confirmer avec ETSL.
ACHAT_APPROVAL_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.DIRECTEUR_PROJETS,
    User.Role.DIRECTEUR_OPERATIONS,
    User.Role.FINANCE,
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


def can_viser_dg(user):
    """Visa exceptionnel de dépassement budgétaire : Direction Générale uniquement (CDC Couche D §2.8)."""
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role == User.Role.PDG


def can_approve_da(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in ACHAT_APPROVAL_ROLES


class CanApproveDa(BasePermission):
    def has_permission(self, request, view):
        return can_approve_da(getattr(request, "user", None))


def can_see_amount(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in ACHAT_AMOUNT_ROLES


class CanManageAchats(BasePermission):
    """Écriture réservée aux rôles Achats / Finance / Direction."""

    def has_permission(self, request, view):
        return can_manage_achats(getattr(request, "user", None))

# Écarts M2 — agrément fournisseur : décision du service du domaine (QA/QC pour M6, HSE pour M7) ou de la Direction.
AGREMENT_QUALITE_VALIDATION_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.QAQC,
    User.Role.DIRECTION,
)

AGREMENT_HSE_VALIDATION_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.HSE,
    User.Role.DIRECTION,
)

# Demande d'agrément et règles d'inspection à réception : Achats + QA/QC + HSE.
AGREMENT_WRITE_ROLES = ACHAT_WRITE_ROLES + (User.Role.QAQC, User.Role.HSE)

# Confirmation des paramètres provisoires M2 (valeurs attendues d'ETSL).
ACHAT_PARAM_CONFIRM_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.DIRECTEUR_OPERATIONS,
    User.Role.FINANCE,
    User.Role.DIRECTION,
)
