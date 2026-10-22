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

from .models import (
    AffectationParc,
    ArchiveCompteurGR,
    DemandeMobilisation,
    EquipementParc,
    HistoriqueEquipement,
    LocationGR,
    LogistiqueSequence,
    ParametreLogistique,
    ReceptionBLGR,
    ReleveCompteurParc,
    TarifGR,
)

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


# Validation d'une commande GR avant émission : Achats (M2) puis Direction (DR) au-delà des seuils paramétrés.
LOGISTIQUE_VALIDATION_M2_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.DIRECTEUR_PROJETS,
    User.Role.DIRECTEUR_OPERATIONS,
    User.Role.FINANCE,
    User.Role.DIRECTION,
)
LOGISTIQUE_VALIDATION_DR_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
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


def reporter_compteur(equipement, valeur, jour=None, user=None):
    """Relevé GR → compteur du parc (jamais à la baisse) puis seuils préventifs M8 (CDC M4 §12.11).

    Le relevé est historisé (kilométrage / heures, écart M4.1) et le plafond du compteur contrôlé."""
    from maintenance.preventif import declencher_plans

    if valeur is None:
        return []
    equipement = EquipementParc.objects.select_for_update().get(pk=equipement.pk)
    if valeur > equipement.compteur_value:
        equipement.compteur_value = valeur
        equipement.save(update_fields=["compteur_value", "updated_at"])
        ReleveCompteurParc.objects.create(
            equipement=equipement, date=jour or timezone.localdate(), valeur=valeur,
            source=ReleveCompteurParc.Source.LOCATION, saisi_par=user,
        )
        controler_plafond(equipement)
    actifs = list(equipement.maintenance_actifs.all())
    return declencher_plans(actifs) if actifs else []


# --------------------------------------------------------------------------------------------------
# Clôture M4 : paramètres provisoires, émission BC / GR, compteurs glissants, ventilation par affaire (M11)
# --------------------------------------------------------------------------------------------------
PARAMETRES_DEFAUT = {
    "COMPTEUR_FENETRE_JOURS": ("Compteurs : fenêtre de la moyenne glissante", Decimal("30"), "jours"),
    "COMPTEUR_HORIZON_JOURS": ("Compteurs : horizon de projection", Decimal("30"), "jours"),
    "JOURS_PAR_MOIS": ("Valorisation au mois : jours par mois facturable", Decimal("30"), "jours"),
    # Écarts M4 (valeurs provisoires « à confirmer ou modifier par ETSL »)
    "PLAFOND_ALERTE_PCT": ("Parc : alerte à ce pourcentage du plafond de compteur", Decimal("90"), "%"),
    "SEUIL_VALIDATION_M2": ("Commande GR : montant exigeant la validation Achats (M2)", Decimal("15000000"), "FCFA"),
    "SEUIL_VALIDATION_DR": ("Commande GR : montant exigeant la validation Direction (DR)", Decimal("50000000"), "FCFA"),
    "SEUIL_ECART_BL_PCT": ("BL GR : écart de livraison déclenchant l'escalade M12", Decimal("5"), "%"),
    "TOLERANCE_FACTURE_PCT": ("Facture GR : tolérance de rapprochement avec le montant attendu", Decimal("2"), "%"),
    "CONSERVATION_ANNEES": ("Audit et archives GR : durée de conservation", Decimal("10"), "ans"),
    "HORIZON_PROPOSITION_JOURS": ("Plan de charge : horizon des propositions de mobilisation", Decimal("30"), "jours"),
    "TARIF_JOUR_REFERENCE": ("Économies : tarif journalier de référence sans grille GR", Decimal("100000"), "FCFA"),
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
    requis = validations_requises(location)
    if requis["m2"] and not location.valide_m2_le:
        erreurs.append("Validation Achats (M2) requise au-delà du seuil paramétré.")
    if requis["dr"] and not location.valide_dr_le:
        erreurs.append("Validation Direction (DR) requise au-delà du seuil paramétré.")
    if location.bon_commande_achat_id:
        erreurs.extend(controles_bc_achat(location, location.bon_commande_achat))
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


# --------------------------------------------------------------------------------------------------
# Écarts M4 : plafond et historique des compteurs, validation M2 / DR, lignes BC / BL, réception BL et
# escalade M12, archive GR, liens BC / facture achats (fil rouge 618), reporting, plan de charge, flux M3
# --------------------------------------------------------------------------------------------------
def _notifier_roles(roles, sujet, message, kind="warning"):
    from workflow.notifications import notify

    for u in User.objects.filter(role__in=roles, is_active=True):
        notify(u, sujet, message, kind=kind)


def controler_plafond(equipement):
    """Compteur ≥ plafond × pourcentage d'alerte : notification Logistique / Maintenance. Renvoie le taux (%)."""
    if not equipement.plafond_compteur:
        return None
    taux = (equipement.compteur_value * 100 / equipement.plafond_compteur).quantize(CENT, rounding=ROUND_HALF_UP)
    if taux >= get_param_logistique("PLAFOND_ALERTE_PCT"):
        _notifier_roles(
            (User.Role.LOGISTIQUE, User.Role.MAINTENANCE),
            f"Plafond de compteur atteint : {equipement.code}",
            f"{equipement.label} : compteur {equipement.compteur_value} pour un plafond de "
            f"{equipement.plafond_compteur} ({taux} %).",
        )
    return taux


def enregistrer_releve_parc(equipement, valeur, jour, user, commentaire=""):
    """Relevé de kilométrage / heures du parc : historisé, jamais à la baisse, plafond contrôlé."""
    equipement = EquipementParc.objects.select_for_update().get(pk=equipement.pk)
    dernier = equipement.releves.order_by("-date", "-created_at").first()
    if valeur < equipement.compteur_value or (dernier and valeur < dernier.valeur):
        raise ValidationError({"valeur": f"Le compteur ne peut baisser (dernière valeur : {equipement.compteur_value})."})
    if dernier and jour < dernier.date:
        raise ValidationError({"date": "Un relevé plus récent existe déjà."})
    releve = ReleveCompteurParc.objects.create(
        equipement=equipement, date=jour, valeur=valeur, saisi_par=user, commentaire=commentaire,
    )
    equipement.compteur_value = valeur
    equipement.save(update_fields=["compteur_value", "updated_at"])
    controler_plafond(equipement)
    return releve


CHAMPS_HISTORISES = (
    "label", "registration", "categorie", "statut", "compteur_type", "compteur_value", "site",
    "is_global_rental", "proprietaire_id", "signe_618", "plafond_compteur",
)


def historiser_equipement(avant, apres, user):
    """Trace chaque champ modifié de l'équipement (piste d'audit inaltérable)."""
    for champ in CHAMPS_HISTORISES:
        a, b = getattr(avant, champ), getattr(apres, champ)
        if a != b:
            HistoriqueEquipement.objects.create(
                equipement=apres, champ=champ, ancienne_valeur="" if a is None else str(a),
                nouvelle_valeur="" if b is None else str(b), modifie_par=user,
            )


def conservation_jusqu_au(jour=None):
    jour = jour or timezone.localdate()
    annees = int(get_param_logistique("CONSERVATION_ANNEES"))
    try:
        return jour.replace(year=jour.year + annees)
    except ValueError:  # 29 février
        return jour.replace(year=jour.year + annees, day=28)


def montant_commande(location):
    """Base des seuils de validation : montant estimé ou total des lignes du BC (le plus élevé)."""
    total = sum((ligne.montant for ligne in location.lignes.all()), Decimal("0"))
    return max(location.montant_estime or Decimal("0"), total)


def validations_requises(location):
    montant = montant_commande(location)
    return {
        "montant": montant,
        "m2": montant >= get_param_logistique("SEUIL_VALIDATION_M2"),
        "dr": montant >= get_param_logistique("SEUIL_VALIDATION_DR"),
    }


def valider_commande(location, user, niveau):
    """Validation M2 (Achats) ou DR (Direction) d'une commande GR en brouillon, avant émission."""
    if location.statut != LocationGR.Statut.BROUILLON or location.emis_le:
        raise ValidationError("Seule une commande GR en brouillon, non émise, se valide.")
    roles = LOGISTIQUE_VALIDATION_M2_ROLES if niveau == "m2" else LOGISTIQUE_VALIDATION_DR_ROLES
    if not (is_admin_or_staff(user) or user.role in roles):
        from rest_framework.exceptions import PermissionDenied

        raise PermissionDenied("Rôle non habilité à cette validation.")
    if niveau == "dr" and validations_requises(location)["m2"] and not location.valide_m2_le:
        raise ValidationError("La validation Achats (M2) précède la validation Direction (DR).")
    if getattr(location, f"valide_{niveau}_le"):
        raise ValidationError("Déjà validée à ce niveau.")
    setattr(location, f"valide_{niveau}_par", user)
    setattr(location, f"valide_{niveau}_le", timezone.now())
    location.save(update_fields=[f"valide_{niveau}_par", f"valide_{niveau}_le", "updated_at"])
    return location


def controles_bc_achat(location, bc):
    """Fil rouge 618 : le BC achats d'une prestation GR est un BC GLOBAL RENTAL du même partenaire."""
    erreurs = []
    if not bc.is_global_rental:
        erreurs.append("Le BC achats doit être marqué intra-groupe GLOBAL RENTAL.")
    if bc.supplier_id != location.partenaire_id:
        erreurs.append("Le fournisseur du BC achats doit être le partenaire GR de la prestation.")
    if bc.status == bc.Status.ANNULEE:
        erreurs.append("BC achats annulé.")
    return erreurs


def _synchroniser_bc(location, bc):
    """Lien unique location ↔ BC GR : le BC porte aussi la location (lu par M10, exclusion anti-double 618)."""
    from comptabilite.gr import controler_liaison_bc

    controler_liaison_bc(location, bc)
    if bc.location_gr_id is None:
        type(bc).objects.filter(pk=bc.pk).update(location_gr=location)
        bc.location_gr = location


def lier_bc_achat(location, bc):
    erreurs = controles_bc_achat(location, bc)
    if erreurs:
        raise ValidationError(erreurs)
    _synchroniser_bc(location, bc)
    location.bon_commande_achat = bc
    if not location.reference_bc:
        location.reference_bc = bc.code
    location.save(update_fields=["bon_commande_achat", "reference_bc", "updated_at"])
    return location


def montant_attendu(location, jusqu_au=None):
    """Montant attendu de la facture GR : total des lignes du BC, sinon coût calculé (grille × durée) + pénalités."""
    lignes = list(location.lignes.all())
    if lignes:
        return sum((ligne.montant for ligne in lignes), Decimal("0")).quantize(CENT)
    if location.date_debut is None:
        return Decimal("0.00")
    fin = location.date_retour or location.date_fin or jusqu_au or timezone.localdate()
    calc = _cout_location(location, location.date_debut, fin, get_param_logistique("JOURS_PAR_MOIS"))
    cout = calc[1] if calc else Decimal("0")
    return (cout + (location.penalite or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def rapprocher_facture(location, facture):
    """Rapproche une facture fournisseur GR de la prestation : BC GR, partenaire GR, écart vs montant attendu."""
    if not facture.purchase_order.is_global_rental:
        raise ValidationError("La facture doit porter sur un BC intra-groupe GLOBAL RENTAL (compte 618).")
    if (facture.supplier_id or facture.purchase_order.supplier_id) != location.partenaire_id:
        raise ValidationError("Le fournisseur de la facture doit être le partenaire GR de la prestation.")
    if location.bon_commande_achat_id and facture.purchase_order_id != location.bon_commande_achat_id:
        raise ValidationError("La facture ne porte pas sur le BC achats lié à la prestation.")
    if facture.status == facture.Status.ANNULEE:
        raise ValidationError("Facture annulée.")
    if LocationGR.objects.filter(facture_achat=facture).exclude(pk=location.pk).exists():
        raise ValidationError("Facture déjà rapprochée d'une autre prestation.")
    attendu = montant_attendu(location)
    total = Decimal(str(facture.total)).quantize(CENT)
    ecart = (total - attendu).quantize(CENT)
    tolerance = get_param_logistique("TOLERANCE_FACTURE_PCT")
    conforme = abs(ecart) <= (attendu * tolerance / 100) if attendu else ecart == 0
    _synchroniser_bc(location, facture.purchase_order)
    location.facture_achat = facture
    if not location.bon_commande_achat_id:
        location.bon_commande_achat = facture.purchase_order
    location.facture_ecart = ecart
    location.facture_conforme = conforme
    location.save(update_fields=[
        "facture_achat", "bon_commande_achat", "facture_ecart", "facture_conforme", "updated_at",
    ])
    if not conforme:
        _notifier_roles(
            (User.Role.FINANCE, User.Role.LOGISTIQUE),
            f"Facture GR hors tolérance : {location.code}",
            f"Facture {facture.code} : {total} pour un montant attendu de {attendu} (écart {ecart}).",
        )
    return location


def donnees_618(periode=None):
    """Prestations GR à refacturer / comptabiliser au 618 (lecture par M10 : rien n'est comptabilisé ici)."""
    qs = LocationGR.objects.filter(
        statut__in=(LocationGR.Statut.ACTIVE, LocationGR.Statut.TERMINEE), partenaire__is_global_rental=True,
        imputation_618=True,
    ).select_related("partenaire", "affaire", "facture_achat", "bon_commande_achat").prefetch_related("lignes")
    if periode:
        debut, fin = _bornes_periode(periode)
        qs = qs.filter(date_debut__lte=fin).filter(Q(date_retour__isnull=True) | Q(date_retour__gte=debut))
    rows = []
    for loc in qs:
        rows.append({
            "location": loc.code, "id": str(loc.pk), "statut": loc.statut, "compte": "618000",
            "partenaire": loc.partenaire.code, "partenaire_gr": loc.partenaire.is_global_rental,
            "affaire": loc.affaire.code if loc.affaire else None,
            "analytic": str(loc.affaire.analytic_id) if loc.affaire and loc.affaire.analytic_id else None,
            "bc_achat": loc.bon_commande_achat.code if loc.bon_commande_achat else None,
            "facture": loc.facture_achat.code if loc.facture_achat else None,
            "montant_attendu": str(montant_attendu(loc)),
            "facture_ecart": None if loc.facture_ecart is None else str(loc.facture_ecart),
            "facture_conforme": loc.facture_conforme,
        })
    return {"compte": "618000", "rows": rows}


def _dossier_gr(location, user):
    """Dossier intra-groupe GR (M12) ouvert pour le partenaire / l'affaire ; créé s'il n'existe pas."""
    from juridique.models import DossierGlobalRental

    dossier = (
        DossierGlobalRental.objects.filter(partenaire_gr=location.partenaire, affaire=location.affaire)
        .exclude(statut=DossierGlobalRental.Statut.CLOTURE).order_by("-created_at").first()
    )
    if dossier is None:
        debut = location.date_debut or timezone.localdate()
        dossier = DossierGlobalRental.objects.create(
            partenaire_gr=location.partenaire, affaire=location.affaire, signe_618=True,
            objet=f"Prestations GLOBAL RENTAL — {location.equipement.label}"[:250],
            date_debut=debut, date_fin=max(location.date_fin or debut, debut), cree_par=user,
        )
        dossier.ouvrir()
    refs = list(dossier.references_documents or [])
    for ref in (location.code, location.reference_bc, location.reference_bl):
        if ref and ref not in refs:
            refs.append(ref)
    dossier.references_documents = refs
    dossier.save(update_fields=["references_documents", "updated_at"])
    return dossier


def escalader_m12(location, user, motif, montant=None):
    """Escalade d'un litige BL / GR vers M12 : contentieux fournisseur + rattachement au dossier GR."""
    from juridique.models import Contentieux
    from juridique.services import JURIDIQUE_WRITE_ROLES

    dossier = _dossier_gr(location, user)
    contentieux = Contentieux.objects.create(
        nature=Contentieux.Nature.FOURNISSEUR, objet=f"Litige GR {location.code} : {motif}"[:250],
        partie_adverse=location.partenaire.name[:200], reference=location.code, montant_en_jeu=montant,
        cree_par=user,
    )
    _notifier_roles(
        JURIDIQUE_WRITE_ROLES,
        f"Litige GLOBAL RENTAL escaladé : {location.code}",
        f"{motif} — contentieux {contentieux.code}, dossier GR {dossier.code}.",
    )
    return contentieux, dossier


def receptionner_bl(location, user, reference_bl, jour, reserves="", litige=False):
    """Réception contrôlée du BL : écart quantité commandée / livrée par ligne ; escalade M12 au-delà du seuil."""
    if location.statut in (LocationGR.Statut.ANNULEE, LocationGR.Statut.TERMINEE):
        raise ValidationError("Prestation terminée ou annulée : réception impossible.")
    if not reference_bl:
        raise ValidationError({"reference_bl": "Référence du BL requise."})
    lignes, commande, ecart_total = [], Decimal("0"), Decimal("0")
    for ligne in location.lignes.all():
        livree = ligne.quantite if ligne.quantite_livree is None else ligne.quantite_livree
        ecart = (livree - ligne.quantite).quantize(CENT)
        commande += ligne.quantite
        ecart_total += abs(ecart)
        lignes.append({
            "ligne": str(ligne.pk), "designation": ligne.designation, "commandee": str(ligne.quantite),
            "livree": str(livree), "ecart": str(ecart),
        })
    ecart_pct = (ecart_total * 100 / commande).quantize(CENT, rounding=ROUND_HALF_UP) if commande else Decimal("0")
    seuil = get_param_logistique("SEUIL_ECART_BL_PCT")
    escalade = litige or ecart_pct > seuil
    reception = ReceptionBLGR.objects.create(
        location=location, reference_bl=reference_bl, date_reception=jour, lignes=lignes, ecart_pct=ecart_pct,
        reserves=reserves, litige=escalade, recu_par=user,
    )
    location.reference_bl = reference_bl
    location.save(update_fields=["reference_bl", "updated_at"])
    if escalade:
        motif = f"BL {reference_bl} : écart {ecart_pct} % (seuil {seuil} %)" + (f" — {reserves}" if reserves else "")
        reception.contentieux, reception.dossier_gr = escalader_m12(location, user, motif)
        reception.save(update_fields=["contentieux", "dossier_gr"])
    return reception


def archiver_compteurs(location):
    """Archive scellée (SHA-256) des compteurs d'une prestation GR clôturée."""
    import hashlib
    import json

    if hasattr(location, "archive_compteurs"):
        return location.archive_compteurs
    glissant = compteur_glissant(location, aujourdhui=location.date_retour)
    contenu = {
        "location": location.code, "equipement": location.equipement.code, "partenaire": location.partenaire.code,
        "date_debut": str(location.date_debut) if location.date_debut else None,
        "date_retour": str(location.date_retour) if location.date_retour else None,
        "lecture_initiale": str(location.lecture_initiale), "lecture_finale": str(location.lecture_finale),
        "consommation": str(location.consommation) if location.consommation is not None else None,
        "releves": [
            {"date": str(lec.date), "valeur": str(lec.valeur), "type": lec.type_lecture, "source": lec.source}
            for lec in location.lectures.order_by("date", "created_at")
        ],
        "glissant": {k: (str(v) if isinstance(v, Decimal) else v) for k, v in glissant.items()},
        "jours_retard": location.jours_retard, "penalite": str(location.penalite), "compte": "618000",
    }
    sha = hashlib.sha256(json.dumps(contenu, sort_keys=True).encode()).hexdigest()
    return ArchiveCompteurGR.objects.create(
        location=location, contenu=contenu, sha256=sha, conserver_jusqu_au=conservation_jusqu_au(),
    )


def archive_integre(archive):
    import hashlib
    import json

    return hashlib.sha256(json.dumps(archive.contenu, sort_keys=True).encode()).hexdigest() == archive.sha256


def _jours_mobilises(equipement, debut, fin):
    """Jours de la période où l'équipement est affecté (M3) ou en location GR."""
    jours = set()
    periodes = [
        (a.date_debut, a.date_fin) for a in equipement.affectations.all()
        if a.statut != AffectationParc.Statut.ANNULEE
    ] + [
        (loc.date_debut, loc.date_retour or loc.date_fin) for loc in equipement.locations.all()
        if loc.statut in (LocationGR.Statut.ACTIVE, LocationGR.Statut.TERMINEE) and loc.date_debut
    ]
    for d0, d1 in periodes:
        a, b = max(debut, d0), min(fin, d1 or fin)
        while a <= b:
            jours.add(a)
            a += timedelta(days=1)
    return len(jours)


def reporting_parc(periode):
    """Rentabilité, utilisation et économies du parc sur un mois (formules provisoires, affichées à l'écran).

    - utilisation (%) = jours mobilisés (affectation ou location) / jours du mois, par équipement puis moyenne ;
    - économies = jours mobilisés des équipements propres × tarif journalier GR de la catégorie (coût évité) ;
    - rentabilité (%) = économies / (économies + coût GR du mois) : part des besoins couverts par le parc propre.
    """
    debut, fin = _bornes_periode(periode)
    jours_mois = (fin - debut).days + 1
    reference = get_param_logistique("TARIF_JOUR_REFERENCE")
    rows, economies, taux = [], Decimal("0"), []
    for eq in EquipementParc.objects.prefetch_related("affectations", "locations"):
        jours = _jours_mobilises(eq, debut, fin)
        utilisation = (Decimal(jours) * 100 / jours_mois).quantize(CENT, rounding=ROUND_HALF_UP)
        taux.append(utilisation)
        economie = Decimal("0")
        if not eq.is_global_rental:
            tarif = (
                TarifGR.objects.filter(
                    equipement__isnull=True, categorie=eq.categorie, periodicite=LocationGR.Periodicite.JOUR,
                    date_effet__lte=fin,
                ).order_by("-date_effet", "-version").first()
            )
            economie = (Decimal(jours) * (tarif.tarif if tarif else reference)).quantize(CENT)
            economies += economie
        rows.append({
            "equipement": eq.code, "label": eq.label, "gr": eq.is_global_rental, "jours_mobilises": jours,
            "utilisation_pct": str(utilisation), "economie": str(economie),
            "compteur": str(eq.compteur_value),
            "plafond": None if eq.plafond_compteur is None else str(eq.plafond_compteur),
            "plafond_pct": None if not eq.plafond_compteur else str(
                (eq.compteur_value * 100 / eq.plafond_compteur).quantize(CENT, rounding=ROUND_HALF_UP)
            ),
        })
    cout_gr = ventilation_gr(periode)["total_gr"]
    base = economies + cout_gr
    return {
        "periode": periode, "jours": jours_mois, "rows": rows,
        "utilisation_moyenne_pct": str(
            (sum(taux, Decimal("0")) / len(taux)).quantize(CENT, rounding=ROUND_HALF_UP) if taux else Decimal("0")
        ),
        "economies": str(economies.quantize(CENT)), "cout_gr": str(cout_gr.quantize(CENT)),
        "rentabilite_pct": str((economies * 100 / base).quantize(CENT, rounding=ROUND_HALF_UP)) if base else None,
        "provisoire": parametres_logistique_provisoires(("TARIF_JOUR_REFERENCE", "JOURS_PAR_MOIS")),
    }


def proposer_demandes(user, aujourdhui=None):
    """Plan de charge M3 → propositions de mobilisation machines (brouillon) pour les OF qui démarrent dans
    l'horizon paramétré et n'ont pas encore de demande. Idempotent ; lit M3 sans le modifier."""
    from operations.models import OrdreFabrication

    aujourdhui = aujourdhui or timezone.localdate()
    horizon = aujourdhui + timedelta(days=int(get_param_logistique("HORIZON_PROPOSITION_JOURS")))
    ordres = (
        OrdreFabrication.objects.filter(
            status__in=(OrdreFabrication.Status.PREVU, OrdreFabrication.Status.LANCE, OrdreFabrication.Status.EN_COURS),
            planned_start__isnull=False, planned_start__lte=horizon,
        )
        .filter(Q(planned_end__isnull=True) | Q(planned_end__gte=aujourdhui))
        .exclude(demandes_logistique__statut__in=(
            DemandeMobilisation.Statut.BROUILLON, DemandeMobilisation.Statut.SOUMISE, DemandeMobilisation.Statut.TRAITEE,
        ))
        .select_related("affaire")
    )
    creees = []
    for of in ordres:
        creees.append(DemandeMobilisation.objects.create(
            label=f"Mobilisation machines — {of.code} {of.label}"[:200], affaire=of.affaire, ordre=of,
            departement=of.get_scope_display(), date_debut=of.planned_start, date_fin=of.planned_end,
            notes=f"Proposition générée depuis le plan de charge M3 ({of.calculated_hours or 0} h calculées).",
            created_by=user,
        ))
    return creees


def flux_operations(affaire_id=None):
    """Déversement M4 → M3 / M11 : machines, compteurs et BL par affaire et OF (lecture seule pour M3)."""
    locations = LocationGR.objects.filter(
        statut__in=(LocationGR.Statut.ACTIVE, LocationGR.Statut.TERMINEE)
    ).select_related("affaire", "equipement").prefetch_related("receptions_bl")
    affectations = AffectationParc.objects.exclude(statut=AffectationParc.Statut.ANNULEE).select_related(
        "affaire", "ordre", "equipement"
    )
    if affaire_id:
        locations = locations.filter(affaire_id=affaire_id)
        affectations = affectations.filter(affaire_id=affaire_id)
    par_affaire = {}

    def bloc(affaire):
        return par_affaire.setdefault(affaire.code if affaire else None, {
            "affaire": affaire.code if affaire else None, "titre": affaire.title if affaire else "Sans affaire",
            "machines": [], "consommation_gr": Decimal("0"), "bl": [],
        })

    for a in affectations:
        bloc(a.affaire)["machines"].append({
            "equipement": a.equipement.code, "label": a.equipement.label, "of": a.ordre.code if a.ordre else None,
            "debut": str(a.date_debut), "fin": str(a.date_fin) if a.date_fin else None, "source": "parc",
            "compteur": str(a.equipement.compteur_value),
        })
    for loc in locations:
        b = bloc(loc.affaire)
        b["machines"].append({
            "equipement": loc.equipement.code, "label": loc.equipement.label, "of": None,
            "debut": str(loc.date_debut) if loc.date_debut else None,
            "fin": str(loc.date_retour or loc.date_fin) if (loc.date_retour or loc.date_fin) else None,
            "source": "gr", "location": loc.code, "compteur": str(loc.lecture_finale or loc.lecture_initiale or 0),
        })
        b["consommation_gr"] += loc.consommation or 0
        for r in loc.receptions_bl.all():
            b["bl"].append({
                "code": r.code, "reference_bl": r.reference_bl, "date": str(r.date_reception),
                "ecart_pct": str(r.ecart_pct), "litige": r.litige,
            })
    rows = list(par_affaire.values())
    for r in rows:
        r["consommation_gr"] = str(r["consommation_gr"])
    rows.sort(key=lambda r: (r["affaire"] is None, r["affaire"] or ""))
    return {"rows": rows}
