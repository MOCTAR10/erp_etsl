"""Droits métier M4 (RF-ERP-30…33) + stats parc logistique / GLOBAL RENTAL.

Écriture : Logistique, Maintenance, Chefs d'atelier / chantier, Direction des
Opérations, Projets (M1), Direction (circuit administratif-financier W1).
Montants (prestations GR, refacturation 618) : restreints hors rôles
autorisés (RF-59, pattern RF-ERP-33).
"""

import calendar
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from rest_framework.exceptions import ValidationError
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework.permissions import BasePermission

from users.models import User

from .models import EquipementParc, LocationGR, LogistiqueSequence, ParametreLogistique, TarifGR

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


# Qui confirme une valeur provisoire (lecture : lecteurs M4 ; saisie : rôles d'écriture).
LOGISTIQUE_CONFIRM_ROLES = (
    User.Role.ADMIN, User.Role.PDG, User.Role.DGA, User.Role.DIRECTEUR_OPERATIONS, User.Role.DIRECTION,
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


# --------------------------------------------------------------------------------------------------
# Clôture M4 : paramètres provisoires, émission BC / GR, compteurs glissants, ventilation par affaire (M11)
# --------------------------------------------------------------------------------------------------
PARAMETRES_DEFAUT = {
    "COMPTEUR_FENETRE_JOURS": ("Compteurs : fenêtre de la moyenne glissante", Decimal("30"), "jours"),
    "COMPTEUR_HORIZON_JOURS": ("Compteurs : horizon de projection", Decimal("30"), "jours"),
    "JOURS_PAR_MOIS": ("Valorisation au mois : jours par mois facturable", Decimal("30"), "jours"),
}
CENT = Decimal("0.01")


def get_param_logistique(code):
    """Valeur du paramètre `code` ; crée le défaut provisoire si absent."""
    label, valeur, unite = PARAMETRES_DEFAUT[code]
    obj, _ = ParametreLogistique.objects.get_or_create(
        code=code, defaults={"label": label, "valeur": valeur, "unite": unite}
    )
    return obj.valeur


def parametres_logistique_provisoires(codes):
    """Vrai si l'un des paramètres `codes` n'est pas encore confirmé par ETSL."""
    for c in codes:
        get_param_logistique(c)
    return ParametreLogistique.objects.filter(code__in=codes).exclude(statut_valeur="confirme").exists()


def controles_emission(location):
    """Validation automatique avant émission du BC / GR : liste des motifs de refus (vide = valide)."""
    erreurs = []
    if not location.partenaire.is_global_rental:
        erreurs.append("Le partenaire doit être marqué GLOBAL RENTAL (intra-groupe).")
    if not location.imputation_618:
        erreurs.append("La refacturation intra-groupe est imputée au compte 618 : imputation obligatoire.")
    if location.date_debut is None:
        erreurs.append("Date de début requise.")
    if location.tarif is None or location.tarif <= 0:
        erreurs.append("Tarif requis : aucune grille GR applicable et aucun tarif saisi.")
    if location.equipement.statut in (EquipementParc.Statut.MAINTENANCE, EquipementParc.Statut.HORS_SERVICE):
        erreurs.append(f"Équipement indisponible ({location.equipement.get_statut_display().lower()}).")
    if (
        LocationGR.objects.filter(equipement=location.equipement, statut=LocationGR.Statut.ACTIVE)
        .exclude(pk=location.pk).exists()
    ):
        erreurs.append("Équipement déjà en location active sur une autre prestation.")
    return erreurs


def emettre_bc_gr(location, user):
    """Valide automatiquement puis émet le BC et le GR (numéros auto, attestation posée côté serveur)."""
    if location.statut != LocationGR.Statut.BROUILLON:
        raise ValidationError("Seule une prestation en brouillon peut être émise.")
    if location.emis_le:
        raise ValidationError("BC / GR déjà émis.")
    appliquer_tarif(location)
    erreurs = controles_emission(location)
    if erreurs:
        raise ValidationError(erreurs)
    if not location.reference_bc:
        location.reference_bc = LogistiqueSequence.next_for("BCGR", "BCG")
    if not location.reference_gr:
        location.reference_gr = LogistiqueSequence.next_for("GRGR", "GRG")
    location.emis_le = timezone.now()
    location.emis_par = user
    location.save(update_fields=["reference_bc", "reference_gr", "emis_le", "emis_par", "updated_at"])
    return location


def _points_compteur(location):
    """Relevés de la prestation triés par date : départ, relevés périodiques, retour."""
    points = {}
    if location.lecture_initiale is not None and location.date_debut:
        points[location.date_debut] = location.lecture_initiale
    for lecture in location.lectures.all():
        points[lecture.date] = max(points.get(lecture.date, lecture.valeur), lecture.valeur)
    if location.lecture_finale is not None and location.date_retour:
        points[location.date_retour] = location.lecture_finale
    return sorted(points.items())


def valeur_compteur_a(points, jour):
    """Valeur du compteur en fin de `jour` : interpolation linéaire entre relevés, plateau avant/après."""
    if not points:
        return None
    if jour <= points[0][0]:
        return points[0][1]
    for (d0, v0), (d1, v1) in zip(points, points[1:]):
        if jour <= d1:
            return v0 + (v1 - v0) * Decimal((jour - d0).days) / Decimal((d1 - d0).days)
    return points[-1][1]


def compteur_glissant(location, aujourdhui=None):
    """Formule glissante des compteurs (provisoire) : consommation moyenne par jour sur la fenêtre paramétrée,
    projection du compteur à l'horizon paramétré. Fenêtre et horizon sont des paramètres ETSL, pas du code."""
    aujourdhui = aujourdhui or timezone.localdate()
    fenetre = int(get_param_logistique("COMPTEUR_FENETRE_JOURS"))
    horizon = int(get_param_logistique("COMPTEUR_HORIZON_JOURS"))
    points = _points_compteur(location)
    resultat = {
        "fenetre_jours": fenetre, "horizon_jours": horizon, "consommation_fenetre": None, "taux_jour": None,
        "dernier_releve": None, "projection_valeur": None,
        "provisoire": parametres_logistique_provisoires(("COMPTEUR_FENETRE_JOURS", "COMPTEUR_HORIZON_JOURS")),
    }
    if not points or location.date_debut is None:
        return resultat
    jours = min(fenetre, (aujourdhui - location.date_debut).days)
    dernier = valeur_compteur_a(points, aujourdhui)
    resultat["dernier_releve"] = dernier
    if jours <= 0:
        return resultat
    conso = (dernier - valeur_compteur_a(points, aujourdhui - timedelta(days=jours))).quantize(CENT)
    taux = (conso / jours).quantize(CENT, rounding=ROUND_HALF_UP)
    resultat.update(consommation_fenetre=conso, taux_jour=taux, projection_valeur=dernier + taux * horizon)
    return resultat


def _bornes_periode(periode):
    try:
        annee, mois = (int(x) for x in periode.split("-"))
        debut = date(annee, mois, 1)
    except (ValueError, AttributeError):
        raise ValidationError("Période attendue au format AAAA-MM.")
    return debut, date(annee, mois, calendar.monthrange(annee, mois)[1])


def _cout_location(location, debut, fin, jours_par_mois):
    """(consommation, coût) de la prestation sur [debut, fin] ; coût selon la périodicité de la grille."""
    if location.date_debut is None or location.date_debut > fin:
        return None
    if location.statut == LocationGR.Statut.TERMINEE and location.date_retour:
        sortie = location.date_retour
    else:
        sortie = location.date_fin or fin
    a, b = max(debut, location.date_debut), min(fin, sortie)
    if b < a:
        return None
    jours = (b - a).days + 1
    points = _points_compteur(location)
    conso = Decimal("0")
    if points:
        conso = valeur_compteur_a(points, b) - valeur_compteur_a(points, a - timedelta(days=1))
    tarif = location.tarif
    if location.periodicite == LocationGR.Periodicite.HEURE:
        cout = conso * tarif
    elif location.periodicite == LocationGR.Periodicite.JOUR:
        cout = tarif * jours
    elif location.periodicite == LocationGR.Periodicite.MOIS:
        cout = tarif * Decimal(jours) / jours_par_mois
    else:  # forfait : compté le mois du début
        cout = tarif if debut <= location.date_debut <= fin else Decimal("0")
    return conso, cout


def ventilation_gr(periode):
    """Coût GLOBAL RENTAL de la période ventilé par affaire (flux compteurs → M11, marge GR par affaire).

    Le coût reste au compte 618 : rien n'est comptabilisé ici, M11 lit cette ventilation en plus des marges.
    """
    debut, fin = _bornes_periode(periode)
    jours_par_mois = get_param_logistique("JOURS_PAR_MOIS")
    locations = (
        LocationGR.objects.filter(
            statut__in=(LocationGR.Statut.ACTIVE, LocationGR.Statut.TERMINEE), partenaire__is_global_rental=True,
        )
        .select_related("affaire", "equipement").prefetch_related("lectures")
    )
    par_affaire = {}
    for loc in locations:
        calc = _cout_location(loc, debut, fin, jours_par_mois)
        penalite = loc.penalite if loc.date_retour and debut <= loc.date_retour <= fin else Decimal("0")
        if calc is None and not penalite:
            continue
        conso, cout = calc or (Decimal("0"), Decimal("0"))
        ligne = par_affaire.setdefault(loc.affaire_id, {
            "affaire": loc.affaire.code if loc.affaire else None,
            "titre": loc.affaire.title if loc.affaire else "Non affecté à une affaire",
            "analytic": loc.affaire.analytic_id if loc.affaire else None,
            "non_affecte": loc.affaire_id is None, "compte": "618000",
            "consommation": Decimal("0"), "cout_gr": Decimal("0"), "penalites": Decimal("0"), "locations": [],
        })
        ligne["consommation"] += conso
        ligne["cout_gr"] += cout
        ligne["penalites"] += penalite
        ligne["locations"].append(loc.code)
    rows = []
    for ligne in par_affaire.values():
        for k in ("consommation", "cout_gr", "penalites"):
            ligne[k] = ligne[k].quantize(CENT, rounding=ROUND_HALF_UP)
        ligne["total_gr"] = ligne["cout_gr"] + ligne["penalites"]
        rows.append(ligne)
    rows.sort(key=lambda r: (r["non_affecte"], r["affaire"] or ""))
    return {
        "periode": periode, "compte": "618000", "rows": rows,
        "total_gr": sum((r["total_gr"] for r in rows), Decimal("0")),
        "provisoire": parametres_logistique_provisoires(("JOURS_PAR_MOIS",)),
    }
