"""Droits métier M3 (RF-ERP-20…23) + plan de charge atelier.

Écriture : rôles Opérations / Direction des Opérations, Chefs d'atelier /
chantier, appui Projets (M1), QA-QC / HSE (contrôle circuit technique W2),
Logistique & Direction.
Montants (situations de travaux) : restreints hors rôles autorisés (RF-59).
"""

from django.db.models import Q, Sum
from rest_framework.permissions import BasePermission

from users.models import User

from .models import OrdreFabrication

OPERATION_WRITE_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.DIRECTEUR_PROJETS,
    User.Role.DIRECTEUR_OPERATIONS,
    User.Role.QAQC,
    User.Role.HSE,
    User.Role.LOGISTIQUE,
    User.Role.CHEF_ATELIER,
    User.Role.DIRECTION,
)

OPERATION_AMOUNT_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.DIRECTEUR_PROJETS,
    User.Role.DIRECTEUR_OPERATIONS,
    User.Role.FINANCE,
    User.Role.COMPTABLE,
    User.Role.DIRECTION,
)


def is_admin_or_staff(user):
    return user.is_authenticated and (
        user.is_staff or user.is_superuser or user.role == User.Role.ADMIN
    )


def can_manage_operations(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in OPERATION_WRITE_ROLES


def can_see_amount(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in OPERATION_AMOUNT_ROLES


class CanManageOperations(BasePermission):
    """Écriture réservée aux rôles Opérations / Direction / Projets."""

    def has_permission(self, request, view):
        return can_manage_operations(getattr(request, "user", None))


def charge_stats():
    """Plan de charge & capacité atelier (RF-ERP-23).

    Charge prévisionnelle cumulée par OF en cours/prévu : heures calculées
    (gamme) vs heures pointées réelles, ventilée atelier / chantier.
    """
    ordres = (
        OrdreFabrication.objects.filter(
            ~Q(status=OrdreFabrication.Status.ANNULE)
        )
        .filter(
            Q(status=OrdreFabrication.Status.PREVU)
            | Q(status=OrdreFabrication.Status.LANCE)
            | Q(status=OrdreFabrication.Status.EN_COURS)
        )
        .select_related("gamme")
    )
    rows = []
    for of in ordres:
        rows.append(
            {
                "code": of.code,
                "label": of.label,
                "scope": of.scope,
                "status": of.status,
                "calculated_hours": float(of.calculated_hours),
                "pointed_hours": float(of.pointage_hours),
            }
        )
    totals = {
        "atelier": {
            "calculated": sum(r["calculated_hours"] for r in rows if r["scope"] == "atelier"),
            "pointed": sum(r["pointed_hours"] for r in rows if r["scope"] == "atelier"),
            "count": sum(1 for r in rows if r["scope"] == "atelier"),
        },
        "chantier": {
            "calculated": sum(r["calculated_hours"] for r in rows if r["scope"] == "chantier"),
            "pointed": sum(r["pointed_hours"] for r in rows if r["scope"] == "chantier"),
            "count": sum(1 for r in rows if r["scope"] == "chantier"),
        },
    }
    return {"ordres": rows, "totals": totals}