"""Droits métier M12 — Juridique & GED (RF-ERP-B0...B4).

Écriture : Secrétariat Général (GED, bureau d'ordre — RF-ERP-B1), Finance /
Contrôle de gestion (visa des contrats, circuit RF-ERP-W1), Projets, Opérations,
Direction, admin. Actions d'engagement (signer une convention, lever/appeler une
caution, clôturer un contentieux, résilier une assurance) réservées au cercle
restreint `CanValidateJuridique`. Montants masqués hors rôles autorisés
(pattern RF-59). Lecture : tous utilisateurs authentifiés.

`compute_alertes` agrège les échéances J-90 / J-60 / J-30 / EXPIRÉES des
conventions, cautions & assurances (RF-ERP-B0 : alertes J-90 / J-60 / J-30).
"""

from django.utils import timezone

from rest_framework.permissions import BasePermission

from config.echeances import BANDES as EXPIRY_LABELS  # noqa: F401 (réexport)
from config.echeances import bande as _band
from users.models import User
from users.rbac import can_read_app

JURIDIQUE_WRITE_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.SECRETAIRE_GENERAL,
    User.Role.DIRECTEUR_PROJETS,
    User.Role.DIRECTEUR_OPERATIONS,
    User.Role.FINANCE,
    User.Role.COMPTABLE,
    User.Role.DIRECTION,
)

JURIDIQUE_VALIDATE_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.SECRETAIRE_GENERAL,
    User.Role.FINANCE,
    User.Role.DIRECTION,
)

JURIDIQUE_AMOUNT_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.SECRETAIRE_GENERAL,
    User.Role.FINANCE,
    User.Role.COMPTABLE,
    User.Role.DIRECTION,
)


def is_admin_or_staff(user):
    return user.is_authenticated and (
        user.is_staff or user.is_superuser or user.role == User.Role.ADMIN
    )


def can_manage_juridique(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in JURIDIQUE_WRITE_ROLES


def can_validate_juridique(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in JURIDIQUE_VALIDATE_ROLES


def can_see_amount(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in JURIDIQUE_AMOUNT_ROLES


class CanManageJuridique(BasePermission):
    """Lecture authentifiée ; écriture réservée aux rôles juridique / admin."""

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return can_read_app(getattr(request, "user", None), "juridique")
        return can_manage_juridique(getattr(request, "user", None))


def can_validate_dg(user):
    """Actes qui engagent la société sur une caution / assurance : Direction Générale (CDC M12 §14.8)."""
    if is_admin_or_staff(user):
        return True
    return bool(user and user.is_authenticated and user.role == User.Role.PDG)


class CanValidateDg(BasePermission):
    message = "Validation réservée à la Direction Générale (CDC M12 §14.8)."

    def has_permission(self, request, view):
        return can_validate_dg(getattr(request, "user", None))


class CanValidateJuridique(BasePermission):
    """Actions d'engagement juridique : cercle restreint (RF-ERP-W1)."""

    message = "Rôle non autorisé à réaliser cette action d'engagement."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return can_validate_juridique(user)




def compute_alertes():
    """Alertes J-90 / J-60 / J-30 / expirées sur conventions, cautions, assurances.

    Renvoie un dict `clés -> liste` : `conventions`, `cautions`, `assurances`,
    chacun filtré sur les échéances <= 90 jours, plus un compteur par bande.
    """
    from .models import Assurance, Caution, Convention

    today = timezone.localdate()
    horizon = today + timezone.timedelta(days=90)

    alertes = {"conventions": [], "cautions": [], "assurances": []}

    for conv in Convention.objects.filter(date_fin__lte=horizon):
        alertes["conventions"].append(
            {
                "type": "convention",
                "code": conv.code,
                "libelle": conv.titre,
                "date_echeance": conv.date_fin,
                "bande": _band(conv.days_left),
                "jours": conv.days_left,
                "statut": conv.statut,
            }
        )
    for caution in Caution.objects.filter(date_echeance__lte=horizon).exclude(
        statut__in=[Caution.Statut.LEVEE, Caution.Statut.EXPIREE]
    ):
        alertes["cautions"].append(
            {
                "type": "caution",
                "code": caution.code,
                "libelle": f"{caution.get_type_display()} — {caution.beneficiaire}",
                "date_echeance": caution.date_echeance,
                "bande": _band(caution.days_left),
                "jours": caution.days_left,
                "statut": caution.statut,
            }
        )
    for assurance in Assurance.objects.filter(date_echeance__lte=horizon).exclude(
        statut=Assurance.Statut.RESILIEE
    ):
        alertes["assurances"].append(
            {
                "type": "assurance",
                "code": assurance.code,
                "libelle": f"{assurance.get_type_display()} — {assurance.numero_police}",
                "date_echeance": assurance.date_echeance,
                "bande": _band(assurance.days_left),
                "jours": assurance.days_left,
                "statut": assurance.statut,
            }
        )

    compteurs = {band: 0 for band in EXPIRY_LABELS}
    for liste in alertes.values():
        for item in liste:
            if item["bande"] in compteurs:
                compteurs[item["bande"]] += 1

    alertes["compteurs"] = compteurs
    alertes["total"] = sum(compteurs.values())
    return alertes


def compute_stats():
    """KPIs du tableau de bord M12 (RF-ERP-B0...B4)."""
    from .models import (
        Assurance,
        Caution,
        Contentieux,
        Convention,
        Courrier,
        DossierGlobalRental,
        Reunion,
    )

    return {
        "courriers": Courrier.objects.count(),
        "courriers_a_classer": Courrier.objects.filter(statut__in=["recu", "enregistre"]).count(),
        "conventions": Convention.objects.filter(
            statut__in=[Convention.Statut.SIGNE, Convention.Statut.EN_SIGNATURE]
        ).count(),
        "conventions_a_renouveler": Convention.objects.filter(statut=Convention.Statut.SIGNE).filter(
            date_fin__lte=timezone.localdate() + timezone.timedelta(days=90)
        ).count(),
        "contentieux_ouverts": Contentieux.objects.filter(
            statut__in=[Contentieux.Statut.OUVERT, Contentieux.Statut.EN_INSTRUCTION]
        ).count(),
        "cautions_en_cours": Caution.objects.filter(statut=Caution.Statut.EN_COURS).count(),
        "assurances": Assurance.objects.filter(
            statut__in=[Assurance.Statut.ACTIVE, Assurance.Statut.A_RENOUVELER]
        ).count(),
        "assurances_a_renouveler": Assurance.objects.filter(statut=Assurance.Statut.A_RENOUVELER).count(),
        "reunions_planifiees": Reunion.objects.filter(statut=Reunion.Statut.PLANIFIEE).count(),
        "dossiers_gr_ouverts": DossierGlobalRental.objects.filter(
            statut=DossierGlobalRental.Statut.OUVERT
        ).count(),
    }