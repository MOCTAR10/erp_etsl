"""Droits métier M4 (RF-ERP-30…33) + stats parc logistique / GLOBAL RENTAL.

Écriture : Logistique, Maintenance, Chefs d'atelier / chantier, Direction des
Opérations, Projets (M1), Direction (circuit administratif-financier W1).
Montants (prestations GR, refacturation 618) : restreints hors rôles
autorisés (RF-59, pattern RF-ERP-33).
"""

from django.db.models import Q, Sum
from rest_framework.permissions import BasePermission

from users.models import User

from .models import EquipementParc, LocationGR

LOGISTIQUE_WRITE_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.DIRECTEUR_PROJETS,
    User.Role.DIRECTEUR_OPERATIONS,
    User.Role.LOGISTIQUE,
    User.Role.MAINTENANCE,
    User.Role.CHEF_ATELIER,
    User.Role.DIRECTION,
)

LOGISTIQUE_AMOUNT_ROLES = (
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


def can_manage_logistique(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in LOGISTIQUE_WRITE_ROLES


def can_see_amount(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in LOGISTIQUE_AMOUNT_ROLES


class CanManageLogistique(BasePermission):
    """Écriture réservée aux rôles Logistique / Opérations / Direction."""

    def has_permission(self, request, view):
        return can_manage_logistique(getattr(request, "user", None))


def stats_parc():
    """Mosaïque parc logistique interne ETSL (RF-ERP-30/32/33).

    Parc ventilé par statut, part GLOBAL RENTAL, locations actives avec
    consommation (compteurs) et montant estimé, dernière lecture par location.
    """
    equipements = EquipementParc.objects.all()
    locations = (
        LocationGR.objects.filter(~Q(statut=LocationGR.Statut.ANNULEE))
        .select_related("partenaire", "equipement", "affaire", "devise")
    )
    actives = locations.filter(statut=LocationGR.Statut.ACTIVE)
    statuts = {
        k: equipements.filter(statut=v).count()
        for k, v in EquipementParc.Statut.choices[0:-1]
    }
    gr = equipements.filter(is_global_rental=True).count()
    active_rows = []
    for loc in actives:
        active_rows.append(
            {
                "code": loc.code,
                "equipement": loc.equipement.label,
                "partenaire": loc.partenaire.name if loc.partenaire else None,
                "affaire_code": loc.affaire.code if loc.affaire else None,
                "montant_estime": float(loc.montant_estime),
                "devise": loc.devise.code if loc.devise else None,
                "consommation": float(loc.consommation or 0),
                "lecture_finale": float(loc.lecture_finale or 0),
                "fin": loc.date_fin,
            }
        )
    return {
        "parc": {
            "total": equipements.count(),
            "par_statut": statuts,
            "global_rental": gr,
            "propre": equipements.filter(is_global_rental=False).count(),
        },
        "locations": {
            "actives": actives.count(),
            "total_montant_estime": float(
                actives.aggregate(t=Sum("montant_estime"))["t"] or 0
            ),
            "rows": active_rows,
        },
    }