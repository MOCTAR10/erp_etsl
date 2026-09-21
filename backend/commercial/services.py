"""Droits métier M1 et calculs de pilotage pipeline (RF-ERP-01/04).

Lectures : tout utilisateur authentifié. Écriture : rôles porteurs du module
(proc. MANUEL 6.3-6.9 → circuit commercial, Direction des Projets). Montants/marge :
volontairement restreints (même logique que RF-59 dans `documents`).
"""

from django.db.models import Count, Q, Sum

from rest_framework.permissions import BasePermission

from users.models import User

from .models import Affaire, Opportunity

# Écriture sur le module Commercial (circuit commercial, MANUEL ch.2).
COMM_WRITE_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.SECRETAIRE_GENERAL,
    User.Role.DIRECTEUR_PROJETS,
    User.Role.DIRECTION,
)

# Montants / marge visibles (chef_service volontairement exclu, pattern RF-59).
COMM_AMOUNT_ROLES = (
    User.Role.ADMIN,
    User.Role.COMPTABLE,
    User.Role.FINANCE,
    User.Role.DIRECTION,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.DIRECTEUR_PROJETS,
)


def is_admin_or_staff(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser or user.role == User.Role.ADMIN)


def can_manage_commercial(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in COMM_WRITE_ROLES


def can_see_amount(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in COMM_AMOUNT_ROLES


class CanManageCommercial(BasePermission):
    """Écriture réservée aux rôles commerciaux (commercial + admin)."""

    def has_permission(self, request, view):
        return can_manage_commercial(getattr(request, "user", None))


def pipeline_stats():
    """Pilotage M1.4 — pipeline par étape, taux de conversion, marge par segment."""
    active = Q(is_active=True)
    stages = (
        Opportunity.objects.filter(active)
        .values("stage")
        .annotate(
            count=Count("id"),
            total=Sum("amount"),
        )
        .order_by("stage")
    )
    by_stage = {row["stage"]: {"count": row["count"], "total": float(row["total"] or 0)} for row in stages}

    won = (
        Opportunity.objects.filter(active, stage="gagne")
        .aggregate(count=Count("id"), total=Sum("amount"))
    )
    lost = (
        Opportunity.objects.filter(active, stage="perdu")
        .aggregate(count=Count("id"))
    )
    closed = (won["count"] or 0) + (lost["count"] or 0)
    conversion_rate = round((won["count"] or 0) / closed, 4) if closed else 0.0

    margins = (
        Affaire.objects.filter(status__in=[Affaire.Status.EN_COURS, Affaire.Status.CLOTUREE])
        .exclude(client__isnull=True)
        .values("client__segment")
        .annotate(
            count=Count("id"),
            total_margin=Sum("margin"),
            total_amount=Sum("contract_amount"),
        )
    )
    margin_by_segment = {
        row["client__segment"] or "autre": {
            "count": row["count"],
            "total_margin": float(row["total_margin"] or 0),
            "total_amount": float(row["total_amount"] or 0),
        }
        for row in margins
    }

    return {
        "by_stage": by_stage,
        "conversion_rate": conversion_rate,
        "won_total": float(won["total"] or 0),
        "margin_by_segment": margin_by_segment,
    }