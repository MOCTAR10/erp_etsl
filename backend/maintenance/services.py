"""Droits métier M8 — Maintenance & GMAO (RF-ERP-70…73).

Écriture : Maintenance (pivot 5.9.3), Opérations / Chef d'atelier, Logistique
(compteurs GR lecture seule), Projets, Direction. Montants (cost tracking)
masqués hors rôles autorisés (pattern RF-59, comme M2/M4/M5). Lecture :
tous utilisateurs authentifiés.
"""

from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone
from rest_framework.permissions import BasePermission

from users.models import User
from users.rbac import can_read_app

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
            return can_read_app(getattr(request, "user", None), "maintenance")
        return can_manage_maintenance(getattr(request, "user", None))


MAINTENANCE_CONFIRM_ROLES = (
    User.Role.ADMIN, User.Role.PDG, User.Role.DGA, User.Role.DIRECTEUR_OPERATIONS, User.Role.DIRECTION,
)

# --------------------------------------------------------------------------------------------------
# Clôture M8 : paramètres provisoires, fiabilité (MTBF / MTTR / disponibilité), coûts publiés à M11
# --------------------------------------------------------------------------------------------------
PARAMETRES_DEFAUT = {
    "OBSERVATION_JOURS": ("Fiabilité : période d'observation", Decimal("365"), "jours"),
    "HEURES_PAR_JOUR": ("Fiabilité : heures de service théoriques par jour", Decimal("24"), "heures"),
}
CENT = Decimal("0.01")
COMPTE_GR = "618000"
COMPTE_ENTRETIEN = "624000"
STATUTS_FAITS = ("termine", "cloture", "archive")
TYPES_PANNE = ("correctif", "urgence")


class IsConfirmateurMaintenance(BasePermission):
    """Confirmer une valeur provisoire : direction des opérations et au-dessus."""

    def has_permission(self, request, view):
        u = getattr(request, "user", None)
        return bool(u and u.is_authenticated and (u.is_staff or u.role in MAINTENANCE_CONFIRM_ROLES))


def get_param_maintenance(code):
    """Valeur du paramètre `code` ; crée le défaut provisoire si absent."""
    from .models import ParametreMaintenance

    label, valeur, unite = PARAMETRES_DEFAUT[code]
    obj, _ = ParametreMaintenance.objects.get_or_create(
        code=code, defaults={"label": label, "valeur": valeur, "unite": unite}
    )
    return obj.valeur


def parametres_maintenance_provisoires(codes=None):
    """Vrai si l'un des paramètres n'est pas encore confirmé par ETSL."""
    from .models import ParametreMaintenance

    codes = tuple(codes or PARAMETRES_DEFAUT)
    for c in codes:
        get_param_maintenance(c)
    return ParametreMaintenance.objects.filter(code__in=codes).exclude(statut_valeur="confirme").exists()


def fiabilite_actifs(aujourdhui=None):
    """MTBF / MTTR / disponibilité par machine sur la période d'observation paramétrée (publié Couche D).

    Pannes = OT correctifs / urgences terminés dans la fenêtre ; la disponibilité retire toutes les durées
    d'intervention (préventif et inspection compris). Temps requis = jours observés × heures de service par jour,
    la fenêtre étant bornée par la mise en service de la machine.
    """
    from .models import Actif, OrdreTravail

    aujourdhui = aujourdhui or timezone.localdate()
    obs = int(get_param_maintenance("OBSERVATION_JOURS"))
    h_jour = get_param_maintenance("HEURES_PAR_JOUR")
    fin_fenetre = datetime.combine(aujourdhui, time.max, tzinfo=timezone.get_current_timezone())
    debut_fenetre = fin_fenetre - timedelta(days=obs)

    par_actif = {}
    ots = OrdreTravail.objects.filter(
        statut__in=STATUTS_FAITS, date_debut__isnull=False, date_fin__isnull=False,
        date_fin__gte=debut_fenetre, date_debut__lte=fin_fenetre,
    )
    for ot in ots:
        debut, fin = max(ot.date_debut, debut_fenetre), min(ot.date_fin, fin_fenetre)
        heures = max((fin - debut).total_seconds(), 0) / 3600
        stats = par_actif.setdefault(ot.actif_id, {"pannes": 0, "arret": Decimal("0")})
        stats["arret"] += Decimal(str(heures))
        if ot.type_ot in TYPES_PANNE:
            stats["pannes"] += 1

    rows = []
    for actif in Actif.objects.all():
        jours = obs
        if actif.date_mise_en_service:
            jours = min(obs, (aujourdhui - actif.date_mise_en_service).days)
        requises = (Decimal(max(jours, 0)) * h_jour).quantize(CENT)
        stats = par_actif.get(actif.pk, {"pannes": 0, "arret": Decimal("0")})
        arret = stats["arret"].quantize(CENT, rounding=ROUND_HALF_UP)
        pannes = stats["pannes"]
        dispo = ((requises - arret) / requises * 100).quantize(CENT, rounding=ROUND_HALF_UP) if requises > 0 else None
        rows.append({
            "actif": actif.code, "designation": actif.designation, "gr": actif.is_global_rental,
            "pannes": pannes, "heures_arret": arret, "heures_requises": requises,
            "mttr_h": (arret / pannes).quantize(CENT, rounding=ROUND_HALF_UP) if pannes else None,
            "mtbf_h": ((requises - arret) / pannes).quantize(CENT, rounding=ROUND_HALF_UP) if pannes else None,
            "disponibilite_pct": dispo,
        })
    return {
        "observation_jours": obs, "heures_par_jour": h_jour,
        "provisoire": parametres_maintenance_provisoires(), "rows": rows,
    }


def couts_maintenance(periode):
    """Coût de maintenance par machine pour le mois `periode` (AAAA-MM), publié à M11 sans écriture comptable.

    OT terminés / clôturés / archivés rattachés au mois de leur fin ; machines GR isolées au compte 618.
    """
    from .models import OrdreTravail

    try:
        annee, mois = (int(x) for x in periode.split("-"))
        debut = date(annee, mois, 1)
    except (ValueError, AttributeError):
        raise ValueError("Période invalide : format AAAA-MM attendu.")
    fin = date(annee + (mois == 12), mois % 12 + 1, 1)
    par_actif = {}
    ots = OrdreTravail.objects.filter(
        statut__in=STATUTS_FAITS, date_fin__date__gte=debut, date_fin__date__lt=fin
    ).select_related("actif").order_by("actif__code")
    for ot in ots:
        gr = ot.actif.is_global_rental or ot.actif.signe_618
        ligne = par_actif.setdefault(ot.actif_id, {
            "actif": ot.actif.code, "designation": ot.actif.designation, "gr": gr,
            "compte": COMPTE_GR if gr else COMPTE_ENTRETIEN, "nb_ot": 0,
            "main_oeuvre": Decimal("0"), "pieces": Decimal("0"), "total": Decimal("0"),
        })
        ligne["nb_ot"] += 1
        ligne["main_oeuvre"] += ot.cout_main_oeuvre
        ligne["pieces"] += ot.cout_pieces
        ligne["total"] += ot.cout_total
    rows = list(par_actif.values())
    return {
        "periode": periode, "rows": rows,
        "totaux": {
            "gr_618": sum((r["total"] for r in rows if r["gr"]), Decimal("0")),
            "hors_gr": sum((r["total"] for r in rows if not r["gr"]), Decimal("0")),
        },
    }
