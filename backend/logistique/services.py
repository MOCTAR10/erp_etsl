"""Droits métier M4 (RF-ERP-30…33) + stats parc logistique / GLOBAL RENTAL.

Écriture : Logistique, Maintenance, Chefs d'atelier / chantier, Direction des
Opérations, Projets (M1), Direction (circuit administratif-financier W1).
Montants (prestations GR, refacturation 618) : restreints hors rôles
autorisés (RF-59, pattern RF-ERP-33).
"""

from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework.permissions import BasePermission

from users.models import User

from .models import EquipementParc, LocationGR, TarifGR

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

def appliquer_tarif(location):
    """Prestation en brouillon : retient la version de grille GR en vigueur à la date de début (lot 14).

    Sans grille applicable, le tarif saisi est conservé. Au démarrage, la version retenue est figée.
    """
    if location.statut != LocationGR.Statut.BROUILLON:
        return
    tarif = TarifGR.applicable(
        location.partenaire, location.equipement, location.periodicite,
        location.date_debut or timezone.localdate(),
    )
    if tarif is None:
        if location.tarif_gr_id:
            location.tarif_gr = None
            location.save(update_fields=["tarif_gr", "updated_at"])
        return
    location.tarif_gr = tarif
    location.tarif = tarif.tarif
    location.save(update_fields=["tarif_gr", "tarif", "updated_at"])


def calculer_penalite(location, date_retour):
    """Retour après la date de fin prévue : jours de retard × pénalité journalière de la version (CDC M4 §12.11)."""
    location.date_retour = date_retour
    retard = (date_retour - location.date_fin).days if location.date_fin else 0
    location.jours_retard = max(retard, 0)
    penalite_jour = location.tarif_gr.penalite_jour if location.tarif_gr_id else 0
    location.penalite = location.jours_retard * penalite_jour


def reporter_compteur(equipement, valeur):
    """Relevé GR → compteur du parc (jamais à la baisse) puis seuils préventifs M8 (CDC M4 §12.11)."""
    from maintenance.preventif import declencher_plans

    if valeur is None:
        return []
    equipement = EquipementParc.objects.select_for_update().get(pk=equipement.pk)
    if valeur > equipement.compteur_value:
        equipement.compteur_value = valeur
        equipement.save(update_fields=["compteur_value", "updated_at"])
    actifs = list(equipement.maintenance_actifs.all())
    return declencher_plans(actifs) if actifs else []
