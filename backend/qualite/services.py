"""Droits métier M6 (RF-ERP-50…53) + helpers workflow qualité.

Écriture : Management Qualité / QA-QC (pivot), Direction des Opérations
(circuit `RF-ERP-W2`), appui Projets (M1), Chefs d'atelier/chantier,
Direction. Lecture : tous les utilisateurs authentifiés (masquage des
montants non pertinent ici — pas de montant financier dans M6).

Non-conformités : signalée → analysée → en traitement → clôturée avec CAPA ;
levée de réserve / réception interne portée par le PV (RF-ERP-51/53).
"""

from rest_framework.permissions import BasePermission

from users.models import User

QUALITE_WRITE_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.DIRECTEUR_PROJETS,
    User.Role.DIRECTEUR_OPERATIONS,
    User.Role.QAQC,
    User.Role.CHEF_ATELIER,
    User.Role.DIRECTION,
)

# Validation du PV (levée de réserve / réception interne) : QA/QC + hiérarchie.
PV_VALIDATION_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.DIRECTEUR_OPERATIONS,
    User.Role.QAQC,
    User.Role.DIRECTION,
)


def is_admin_or_staff(user):
    return user.is_authenticated and (
        user.is_staff or user.is_superuser or user.role == User.Role.ADMIN
    )


def can_manage_qualite(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in QUALITE_WRITE_ROLES


def can_validate_pv(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in PV_VALIDATION_ROLES


class CanManageQualite(BasePermission):
    """Lecture authentifiée (défaut DRF), écriture réservée rôles Qualité / Direction."""

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return bool(getattr(request, "user", None) and request.user.is_authenticated)
        return can_manage_qualite(getattr(request, "user", None))


class CanValidatePv(BasePermission):
    """Écriture du PV (levée de réserve / réception interne) : QA/QC + hiérarchie."""

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return bool(getattr(request, "user", None) and request.user.is_authenticated)
        return can_validate_pv(getattr(request, "user", None))