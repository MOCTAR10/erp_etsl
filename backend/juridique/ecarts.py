"""Écarts M12 (2026-10) — Juridique & GED.

Paramètres provisoires (valeurs par défaut à confirmer ou modifier par ETSL à l'écran), complétude des dossiers,
suivi contentieux, validation DG bloquante, vue Risk, dossier GLOBAL RENTAL « à jour », alertes étendues
(contrats M1, jalons, mandats GR) et notification aux paliers paramétrés (J-60 compris).
"""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from config.echeances import BANDES, PALIERS_DEFAUT, bande
from config.echeances import paliers as paliers_communs

# cle -> (libellé, valeur par défaut). Toute valeur est PROVISOIRE tant qu'ETSL ne l'a pas confirmée.
PARAMETRES_DEFAUT = {
    "pieces_requises": (
        "Pièces constituant un « dossier complet », par type de dossier (contentieux par nature, convention par "
        "type, dossier GR) ; « _defaut » s'applique aux types non listés",
        {
            "contentieux": {
                "_defaut": ["acte_introductif", "piece_contractuelle", "correspondances", "pieces_justificatives"],
                "social": ["acte_introductif", "contrat_travail", "correspondances", "bulletins_paie"],
            },
            "convention": {
                "_defaut": ["convention_signee", "pieces_administratives"],
                "marche_travaux": [
                    "convention_signee", "cahier_des_charges", "caution_bonne_execution", "pieces_administratives",
                ],
            },
            "gr": {"_defaut": ["contrat_cadre_gr", "mandat", "grille_tarifaire"]},
        },
    ),
    "bloquer_dossier_incomplet": (
        "Bloquer la signature d'une convention et l'ouverture d'un dossier GR tant que le dossier est incomplet",
        False,
    ),
    "juridictions": (
        "Juridictions proposées pour les contentieux",
        [
            "Tribunal de première instance de Libreville",
            "Tribunal de commerce de Libreville",
            "Tribunal du travail de Libreville",
            "Cour d'appel de Libreville",
            "Cour commune de justice et d'arbitrage (CCJA — OHADA)",
            "Centre d'arbitrage et de médiation",
        ],
    ),
    "roles_dg": ("Rôles reconnus comme « Direction Générale » pour les validations DG", ["pdg"]),
    "bloquer_sans_validation_dg": (
        "Bloquer mainlevée / appel de caution, renouvellement d'assurance et signature d'une convention garantie "
        "tant que la Direction Générale n'a pas validé",
        True,
    ),
    "paliers_notification": ("Paliers d'alerte des échéances, communs à tous les modules (M1, M12, Couche D) (jours)", list(PALIERS_DEFAUT)),
    "destinataires_alertes": (
        "Rôles prévenus par famille d'échéance",
        {
            "convention": ["secretaire_general", "pdg", "dga"],
            "caution": ["secretaire_general", "pdg", "dga", "finance"],
            "assurance": ["secretaire_general", "pdg", "dga"],
            "contrat_m1": ["secretaire_general", "directeur_projets"],
            "jalon_contentieux": ["secretaire_general"],
            "mandat_gr": ["secretaire_general", "finance"],
        },
    ),
    "probabilites_risque": (
        "Cotation du risque : probabilité (%) associée à chaque niveau",
        {"faible": 10, "moyenne": 40, "forte": 70, "certaine": 100},
    ),
    "seuils_risque": (
        "Seuils d'exposition (FCFA) : au-delà de « moyen » le risque est moyen, au-delà de « eleve » il est élevé",
        {"moyen": 10000000, "eleve": 50000000},
    ),
    "gr_delai_revue_jours": ("Dossier GR « à jour » : revue exigée tous les N jours", 365),
    "archivage_auto": (
        "Archivage automatique en GED à la transition : type d'objet -> statuts déclencheurs et type de document "
        "(les BC M2 sont déjà archivés par le module Achats)",
        {
            "qualite.pvcontrole": {"statuts": ["receptionne"], "type_document": "documents_qualite_iso"},
        },
    ),
    "deee": (
        "« DEEE » (sigle du CDC non défini) — hypothèse : déchets d'équipements électriques et électroniques ; "
        "bordereaux classés en GED et liés au bordereau déchet M7",
        {
            "definition": "Déchets d'équipements électriques et électroniques (hypothèse à confirmer)",
            "type_document": "documents_qualite_iso",
            "objet_lie": "hse.bordereaudechet",
        },
    ),
}


def parametre_obj(cle):
    from .models import ParametreJuridique

    libelle, defaut = PARAMETRES_DEFAUT[cle]
    obj, _ = ParametreJuridique.objects.get_or_create(cle=cle, defaults={"libelle": libelle, "valeur": defaut})
    return obj


def parametre(cle):
    return parametre_obj(cle).valeur


def assurer_parametres():
    return [parametre_obj(cle) for cle in PARAMETRES_DEFAUT]


def valider_valeur(cle, valeur):
    """Contrôle de forme d'une nouvelle valeur (même nature que la valeur par défaut) ; ValueError sinon."""
    from users.models import User

    defaut = PARAMETRES_DEFAUT[cle][1]
    attendu = bool if isinstance(defaut, bool) else type(defaut)
    if attendu is int and (isinstance(valeur, bool) or not isinstance(valeur, int)):
        raise ValueError("Valeur entière attendue.")
    if not isinstance(valeur, attendu):
        raise ValueError(f"Valeur de type {attendu.__name__} attendue.")
    roles = set(User.Role.values)
    if cle == "roles_dg":
        if not valeur or not set(valeur) <= roles:
            raise ValueError("Liste de rôles non vide attendue (rôles ERP existants).")
    if cle == "destinataires_alertes":
        for famille, liste in valeur.items():
            if not isinstance(liste, list) or not set(liste) <= roles:
                raise ValueError(f"Rôles inconnus pour la famille {famille}.")
    if cle == "paliers_notification":
        if not all(isinstance(j, int) and not isinstance(j, bool) and 0 <= j <= 365 for j in valeur):
            raise ValueError("Paliers attendus : entiers entre 0 et 365.")
    if cle == "probabilites_risque":
        if not all(isinstance(v, (int, float)) and 0 <= v <= 100 for v in valeur.values()):
            raise ValueError("Probabilités attendues entre 0 et 100.")
    if cle == "gr_delai_revue_jours" and valeur <= 0:
        raise ValueError("Délai strictement positif attendu.")
    return valeur


# --------------------------------------------------------------------------------------------------
# Complétude des dossiers
# --------------------------------------------------------------------------------------------------
def _modele_dossier(dossier_type):
    from .models import Contentieux, Convention, DossierGlobalRental

    return {"contentieux": Contentieux, "convention": Convention, "gr": DossierGlobalRental}[dossier_type]


def resoudre_dossier(dossier_type, dossier_id):
    from django.core.exceptions import ValidationError as DjangoValidationError

    try:
        modele = _modele_dossier(dossier_type)
    except KeyError:
        raise ValueError("Type de dossier inconnu.")
    try:
        obj = modele.objects.filter(pk=dossier_id).first()
    except (DjangoValidationError, ValueError):
        obj = None
    if obj is None:
        raise ValueError("Dossier introuvable.")
    return obj


def pieces_requises(dossier_type, obj):
    sous_type = {"contentieux": getattr(obj, "nature", None), "convention": getattr(obj, "type", None)}.get(dossier_type)
    cfg = (parametre("pieces_requises") or {}).get(dossier_type, {})
    return list(cfg.get(sous_type) or cfg.get("_defaut") or [])


def completude(dossier_type, obj):
    from .models import PieceDossier

    requises = pieces_requises(dossier_type, obj)
    fournies = sorted(
        set(PieceDossier.objects.filter(dossier_type=dossier_type, dossier_id=str(obj.pk)).values_list("piece", flat=True))
    )
    manquantes = [p for p in requises if p not in fournies]
    taux = Decimal(100) if not requises else (Decimal(len(requises) - len(manquantes)) * 100 / len(requises))
    return {
        "requises": requises,
        "fournies": fournies,
        "manquantes": manquantes,
        "complet": not manquantes,
        "taux_pct": str(taux.quantize(Decimal("1"))),
    }


def controler_signature_convention(convention):
    """Blocages paramétrés avant la signature d'une convention."""
    if parametre("bloquer_dossier_incomplet"):
        c = completude("convention", convention)
        if not c["complet"]:
            raise ValueError("Dossier incomplet : pièces manquantes " + ", ".join(c["manquantes"]) + ".")
    if parametre("bloquer_sans_validation_dg"):
        codes = list(convention.cautions.filter(valide_dg_le__isnull=True).values_list("code", flat=True))
        if codes:
            raise ValueError(
                "Garanties non validées par la Direction Générale : " + ", ".join(codes) + "."
            )


def exiger_validation_dg(obj, acte):
    if parametre("bloquer_sans_validation_dg") and not obj.valide_dg_le:
        raise ValueError(f"{acte} impossible : la Direction Générale doit d'abord valider {obj.code}.")


# --------------------------------------------------------------------------------------------------
# Suivi contentieux
# --------------------------------------------------------------------------------------------------
def journaliser(contentieux, type_action, description, user=None):
    from .models import ActionContentieux

    return ActionContentieux.objects.create(
        contentieux=contentieux, type=type_action, description=description[:2000],
        auteur=user if user is not None and user.is_authenticated else None,
    )


# --------------------------------------------------------------------------------------------------
# Dossier GLOBAL RENTAL « à jour »
# --------------------------------------------------------------------------------------------------
def controle_gr(dossier):
    from logistique.models import TarifGR

    today = timezone.localdate()
    motifs = []
    if not dossier.mandat_date_fin:
        motifs.append("Mandat intra-groupe non renseigné.")
    elif dossier.mandat_date_fin < today:
        motifs.append("Mandat intra-groupe expiré.")
    tarifs = TarifGR.objects.filter(partenaire_id=dossier.partenaire_gr_id, date_effet__lte=today).count()
    if not tarifs:
        motifs.append("Aucune grille tarifaire GR en vigueur pour ce partenaire (M4).")
    comp = completude("gr", dossier)
    if comp["manquantes"]:
        motifs.append("Pièces manquantes : " + ", ".join(comp["manquantes"]) + ".")
    delai = int(parametre("gr_delai_revue_jours"))
    if not dossier.date_revue or dossier.date_revue < today - timedelta(days=delai):
        motifs.append(f"Revue périodique à faire (tous les {delai} jours).")
    return {"a_jour": not motifs, "motifs": motifs, "tarifs_en_vigueur": tarifs, "completude": comp}


# --------------------------------------------------------------------------------------------------
# Vue Risk
# --------------------------------------------------------------------------------------------------
def vue_risques(voir_montants=True):
    from .models import Caution, Contentieux

    probas = parametre("probabilites_risque")
    seuils = parametre("seuils_risque")
    lignes = []
    total_enjeu = Decimal(0)
    total_expo = Decimal(0)
    par_niveau = {"eleve": 0, "moyen": 0, "faible": 0, "non_cote": 0}
    for c in Contentieux.objects.filter(statut__in=["ouvert", "en_instruction"]).order_by("-montant_en_jeu"):
        enjeu = c.montant_en_jeu or Decimal(0)
        pct = probas.get(c.probabilite) if c.probabilite else None
        expo = (enjeu * Decimal(str(pct)) / 100).quantize(Decimal("1")) if pct is not None else None
        if expo is None:
            niveau = "non_cote"
        elif expo >= Decimal(str(seuils.get("eleve", 0))):
            niveau = "eleve"
        elif expo >= Decimal(str(seuils.get("moyen", 0))):
            niveau = "moyen"
        else:
            niveau = "faible"
        par_niveau[niveau] += 1
        total_enjeu += enjeu
        total_expo += expo or 0
        lignes.append({
            "id": str(c.pk), "code": c.code, "objet": c.objet, "partie_adverse": c.partie_adverse,
            "juridiction": c.juridiction, "phase": c.get_phase_display(), "probabilite": c.probabilite or None,
            "probabilite_pct": pct, "niveau": niveau,
            "montant_en_jeu": str(enjeu) if voir_montants else None,
            "exposition": (str(expo) if expo is not None else None) if voir_montants else None,
        })
    ordre = {"eleve": 0, "moyen": 1, "faible": 2, "non_cote": 3}
    lignes.sort(key=lambda r: ordre[r["niveau"]])
    cautions = Caution.objects.filter(statut="en_cours")
    engagements = sum((c.montant for c in cautions), Decimal(0))
    return {
        "contentieux": lignes,
        "par_niveau": par_niveau,
        "total_enjeu": str(total_enjeu) if voir_montants else None,
        "total_exposition": str(total_expo) if voir_montants else None,
        "cautions_en_cours": cautions.count(),
        "engagements_cautions": str(engagements) if voir_montants else None,
        "has_amount_access": voir_montants,
    }


# --------------------------------------------------------------------------------------------------
# Alertes étendues + notification aux paliers paramétrés
# --------------------------------------------------------------------------------------------------
def alertes_complementaires(horizon_jours=90):
    """Contrats M1 actifs, jalons de contentieux et mandats GR arrivant à échéance (<= horizon)."""
    from commercial.models import Contract

    from .models import DossierGlobalRental, JalonContentieux

    today = timezone.localdate()
    horizon = today + timedelta(days=horizon_jours)

    def item(type_, code, libelle, echeance, statut):
        jours = (echeance - today).days
        return {"type": type_, "code": code, "libelle": libelle, "date_echeance": echeance,
                "bande": bande(jours), "jours": jours, "statut": statut}

    contrats = [
        item("contrat_m1", c.code, str(c), c.end_date, c.status)
        for c in Contract.objects.filter(status="actif", end_date__isnull=False, end_date__lte=horizon)
    ]
    jalons = [
        item("jalon_contentieux", j.contentieux.code, j.libelle, j.date_prevue, j.statut)
        for j in JalonContentieux.objects.select_related("contentieux").filter(
            statut="a_venir", date_prevue__lte=horizon
        )
    ]
    mandats = [
        item("mandat_gr", d.code, f"Mandat intra-groupe {d.mandat_reference}".strip(), d.mandat_date_fin, d.statut)
        for d in DossierGlobalRental.objects.exclude(statut="cloture").filter(
            mandat_date_fin__isnull=False, mandat_date_fin__lte=horizon
        )
    ]
    return {"contrats_m1": contrats, "jalons": jalons, "mandats_gr": mandats}


def compteurs_bandes(*listes):
    compteurs = {b: 0 for b in BANDES}
    for liste in listes:
        for it in liste:
            if it["bande"] in compteurs:
                compteurs[it["bande"]] += 1
    return compteurs


def notifier_echeances_juridiques():
    """Notifie les rôles paramétrés des échéances juridiques atteignant un palier paramétré (J-60 compris).

    Sujet identique à la tâche transverse (`analytics.tasks.notifier_echeances`) : la déduplication quotidienne
    par destinataire évite tout doublon quand les deux envois se recouvrent.
    """
    from users.models import User
    from workflow.models import Notification
    from workflow.notifications import notify

    from .services import compute_alertes

    paliers = set(paliers_communs())
    destinataires = parametre("destinataires_alertes")
    alertes = compute_alertes()
    debut_jour = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    envoyees = 0
    for famille in ("conventions", "cautions", "assurances", "contrats_m1", "jalons", "mandats_gr"):
        for it in alertes.get(famille, []):
            if it["jours"] not in paliers:
                continue
            roles = destinataires.get(it["type"]) or []
            if not roles:
                continue
            sujet = f"Échéance J-{it['jours']} : {it['code']} — {it['libelle']}"[:255]
            message = (
                f"L'échéance « {it['libelle']} » ({it['code']}) arrive le {it['date_echeance']:%d/%m/%Y}. "
                "Merci d'engager le renouvellement, la relance ou la clôture."
            )
            for user in User.objects.filter(role__in=roles, is_active=True):
                if Notification.objects.filter(user=user, subject=sujet, created_at__gte=debut_jour).exists():
                    continue
                notify(user, sujet, message, kind="reminder")
                envoyees += 1
    return envoyees
