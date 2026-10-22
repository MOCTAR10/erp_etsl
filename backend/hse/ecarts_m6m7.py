"""Écarts M7 (lot ecarts-m6m7) : listes paramétrables (§9.2), matrice de cotation et revue du DUER paramétrables,
check-lists et rapport d'audit (M7-02), plan de prévention (M7-03), prestataires déchets agréés (BSD), règles des
sites loués GLOBAL RENTAL (permis / incidents partagés), fiches sécurité terrain (M7-08).

Toutes les valeurs attendues d'ETSL sont livrées PROVISOIRES (paramètres, listes, modèle de check-list, fiches) :
modifiables à l'écran HSE, à confirmer par ETSL.
"""

from django.utils import timezone

from users.models import User
from config.i18n import tr

# --------------------------------------------------------------------------------------------------------------
# Listes paramétrables
# --------------------------------------------------------------------------------------------------------------
#: Destinataires provisoires du partage des événements HSE sur site GLOBAL RENTAL (« équipe intégrée »).
PARTAGE_GR_DEFAUT = (User.Role.LOGISTIQUE, User.Role.HSE, User.Role.DIRECTEUR_OPERATIONS)
DECHETS_DANGEREUX_DEFAUT = ("huiles", "solvants", "batteries", "peintures")


def _defauts(categorie):
    from .models import BordereauDechet, Incident, PermisTravail

    if categorie == "type_permis":
        return [
            {"code": v, "libelle": label, "gaz_obligatoire": v in PermisTravail.GAZ_TYPES}
            for v, label in PermisTravail.TypePermis.choices
        ]
    if categorie == "type_incident":
        return [{"code": v, "libelle": label} for v, label in Incident.TypeIncident.choices]
    if categorie == "type_dechet":
        return [
            {"code": v, "libelle": label, "dangereux": v in DECHETS_DANGEREUX_DEFAUT}
            for v, label in BordereauDechet.TypeDechet.choices
        ]
    if categorie == "partage_gr":
        return [{"code": r.value, "libelle": r.label} for r in PARTAGE_GR_DEFAUT]
    return []


def assurer_liste(categorie):
    """Crée les valeurs par défaut (provisoires) d'une catégorie encore vide ; idempotent."""
    from .models import ListeHse

    if ListeHse.objects.filter(categorie=categorie).exists():
        return
    ListeHse.objects.bulk_create(
        [ListeHse(categorie=categorie, ordre=i, **d) for i, d in enumerate(_defauts(categorie), start=1)],
        ignore_conflicts=True,
    )


def assurer_listes():
    from .models import ListeHse

    for categorie in ListeHse.Categorie.values:
        assurer_liste(categorie)


def libelle_liste(categorie, code):
    from .models import ListeHse

    libelle = ListeHse.objects.filter(categorie=categorie, code=code).values_list("libelle", flat=True).first()
    if libelle:
        return libelle
    return next((d["libelle"] for d in _defauts(categorie) if d["code"] == code), code)


def codes_actifs(categorie):
    from .models import ListeHse

    assurer_liste(categorie)
    return set(ListeHse.objects.filter(categorie=categorie, actif=True).values_list("code", flat=True))


def valider_code(categorie, code, ancien=None):
    """Le type saisi doit figurer, actif, dans la liste paramétrée (un enregistrement existant garde son type)."""
    from rest_framework import serializers

    if code == ancien:
        return code
    if code not in codes_actifs(categorie):
        raise serializers.ValidationError("Type inconnu ou désactivé dans la liste paramétrée HSE.")
    return code


def gaz_obligatoire(type_permis):
    from .models import ListeHse, PermisTravail

    valeur = ListeHse.objects.filter(categorie="type_permis", code=type_permis).values_list("gaz_obligatoire", flat=True).first()
    return type_permis in PermisTravail.GAZ_TYPES if valeur is None else valeur


def codes_dangereux():
    from .models import ListeHse

    assurer_liste("type_dechet")
    return list(ListeHse.objects.filter(categorie="type_dechet", dangereux=True).values_list("code", flat=True))


# --------------------------------------------------------------------------------------------------------------
# Paramètres provisoires (ParametreHse)
# --------------------------------------------------------------------------------------------------------------
PARAMETRES_M6M7 = {
    "RISQUE_SEUIL_MOYEN": ("Matrice de cotation : score mini d'un risque moyen (P × G)", "4", "score"),
    "RISQUE_SEUIL_ELEVE": ("Matrice de cotation : score mini d'un risque élevé (P × G)", "9", "score"),
    "RISQUE_SEUIL_CRITIQUE": ("Matrice de cotation : score mini d'un risque critique (P × G)", "15", "score"),
    "DUER_REVUE_MOIS": ("DUER : périodicité de revue", "12", "mois"),
    "BSD_AGREMENT_OBLIGATOIRE": ("BSD : prestataire déchets agréé obligatoire (1 = oui, 0 = non)", "1", "0/1"),
    "GR_PDP_OBLIGATOIRE": ("Site GLOBAL RENTAL : plan de prévention validé exigé au démarrage du permis (1/0)", "1", "0/1"),
}
#: Paramètres booléens : la valeur 0 (désactivé) est admise.
PARAMETRES_BOOLEENS = ("BSD_AGREMENT_OBLIGATOIRE", "GR_PDP_OBLIGATOIRE")


def _param(code):
    from .services import get_param_hse

    return get_param_hse(code)


def seuils_risque():
    return int(_param("RISQUE_SEUIL_MOYEN")), int(_param("RISQUE_SEUIL_ELEVE")), int(_param("RISQUE_SEUIL_CRITIQUE"))


def duer_revue_jours():
    return int(round(float(_param("DUER_REVUE_MOIS")) * 365 / 12))


# --------------------------------------------------------------------------------------------------------------
# BSD : prestataire agréé
# --------------------------------------------------------------------------------------------------------------
def controle_prestataire_bsd(type_dechet, prestataire, jour=None):
    """Message d'erreur si le BSD ne peut pas être émis / traité (prestataire non agréé), sinon None."""
    if not int(_param("BSD_AGREMENT_OBLIGATOIRE")):
        return None
    jour = jour or timezone.localdate()
    if prestataire is None:
        return "Prestataire déchets agréé obligatoire pour émettre ou traiter un BSD."
    if not prestataire.est_valide(jour):
        return f"Agrément du prestataire {prestataire.nom} expiré ou inactif (valable jusqu'au {prestataire.date_fin_validite:%d/%m/%Y})."
    if not prestataire.couvre(type_dechet):
        return f"Le prestataire {prestataire.nom} n'est pas agréé pour ce type de déchet ({libelle_liste('type_dechet', type_dechet)})."
    return None


# --------------------------------------------------------------------------------------------------------------
# Sites GLOBAL RENTAL : plan de prévention exigé, partage à l'équipe intégrée
# --------------------------------------------------------------------------------------------------------------
def controle_site_gr(permis, jour=None):
    """Un permis sur site loué GR ne démarre qu'avec un plan de prévention validé en vigueur (paramètre)."""
    if not permis.site_gr or not int(_param("GR_PDP_OBLIGATOIRE")):
        return None
    pdp = permis.plan_prevention
    if pdp is None:
        return "Site GLOBAL RENTAL : plan de prévention validé requis avant démarrage."
    if not pdp.en_vigueur(jour):
        return f"Plan de prévention {pdp.code} non validé ou hors période : démarrage interdit sur site GLOBAL RENTAL."
    return None


def destinataires_partage_gr():
    from .models import ListeHse

    assurer_liste("partage_gr")
    roles = list(ListeHse.objects.filter(categorie="partage_gr", actif=True).values_list("code", flat=True))
    return list(User.objects.filter(is_active=True, role__in=roles))


def partager_site_gr(sujet, message, exclure=None):
    """Partage un événement HSE sur site GR à l'équipe intégrée (rôles paramétrés, provisoires)."""
    from workflow.notifications import notify

    n = 0
    for user in destinataires_partage_gr():
        if exclure is not None and user.pk == exclure.pk:
            continue
        notify(user, sujet[:255], message, kind="info")
        n += 1
    return n


# --------------------------------------------------------------------------------------------------------------
# Check-lists d'audit et rapport PDF
# --------------------------------------------------------------------------------------------------------------
CHECKLIST_DEFAUT = (
    "Permis de travail affichés et signés sur la zone",
    "EPI portés et en bon état (casque, chaussures, lunettes, gants)",
    "Balisage et signalisation de la zone de travail",
    "Extincteurs accessibles et vérifiés",
    "Stockage des produits chimiques (FDS disponibles, rétention)",
    "Tri des déchets et bennes identifiées",
    "Échafaudages et moyens d'accès vérifiés (étiquette)",
    "Engins et équipements de levage avec contrôle réglementaire à jour",
    "Consignes d'urgence et points de rassemblement affichés",
    "Ordre et propreté (circulations dégagées)",
)


def assurer_modele_defaut():
    from .models import ModeleChecklistHse

    if not ModeleChecklistHse.objects.exists():
        ModeleChecklistHse.objects.create(
            intitule="Inspection sécurité chantier / atelier (trame provisoire)", referentiel="ISO 45001",
            questions=list(CHECKLIST_DEFAUT),
        )


def appliquer_checklist(audit, modele):
    from .models import ReponseChecklistHse

    debut = (audit.reponses_checklist.order_by("-ordre").values_list("ordre", flat=True).first() or 0) + 1
    return ReponseChecklistHse.objects.bulk_create([
        ReponseChecklistHse(audit=audit, modele=modele, ordre=debut + i, question=str(q)[:2000])
        for i, q in enumerate(modele.questions or [])
    ])


def score_checklist(audit):
    """Score de conformité (%) = conformes / (conformes + non conformes) ; None sans réponse évaluée."""
    reponses = list(audit.reponses_checklist.values_list("reponse", flat=True))
    conformes, nc = reponses.count("conforme"), reponses.count("non_conforme")
    return round(conformes * 100 / (conformes + nc)) if conformes + nc else None


def rapport_audit_pdf(audit):
    from .services import _pdf

    blocs = [
        (tr("Type"), audit.get_type_audit_display()), (tr("Zone / périmètre"), audit.zone),
        (tr("Référentiel"), audit.referentiel), (tr("Date prévue"), f"{audit.date_prevue:%d/%m/%Y}"),
        (tr("Réalisé le"), f"{audit.date_realisation:%d/%m/%Y}" if audit.date_realisation else "—"),
        (tr("Réalisé par"), audit.realise_par.get_full_name() if audit.realise_par else "—"),
        (tr("Score de conformité"), f"{audit.score} %" if audit.score is not None else "—"),
        (tr("Statut"), audit.get_statut_display()),
    ]
    tableau = [["#", tr("Point contrôlé / constat"), tr("Résultat"), tr("Commentaire / action")]]
    for r in audit.reponses_checklist.all():
        tableau.append([str(r.ordre), r.question[:90], r.get_reponse_display(), (r.commentaire or "")[:60]])
    for c in audit.constats.select_related("action"):
        action = f"{c.action.code} ({c.action.get_statut_display()})" if c.action_id else tr("sans action")
        tableau.append(["C", c.description[:90], c.get_gravite_display(), action])
    return _pdf(tr("Rapport d'audit HSE %(audit_code)s") % {"audit_code": audit.code}, blocs, tableau if len(tableau) > 1 else None)


# --------------------------------------------------------------------------------------------------------------
# Fiches sécurité terrain : contenus types provisoires (à remplacer par les fiches ETSL)
# --------------------------------------------------------------------------------------------------------------
FICHES_DEFAUT = (
    ("FS-CHAUD", "Travaux à chaud (soudage, meulage, oxycoupage)", "chaud",
     "Incendie, explosion, brûlures, fumées de soudage.",
     "Permis de travail signé et test gaz conforme avant démarrage.\nÉloigner ou protéger les combustibles (10 m).\n"
     "Extincteur à portée de main, surveillance 1 h après la fin des travaux.",
     "Masque de soudeur, gants cuir, tablier, chaussures de sécurité, protection respiratoire si besoin.",
     "Alerter, couper l'alimentation, utiliser l'extincteur si sans danger, évacuer vers le point de rassemblement."),
    ("FS-HAUTEUR", "Travaux en hauteur", "hauteur",
     "Chute de hauteur, chute d'objets.",
     "Échafaudage réceptionné (étiquette verte) ou nacelle vérifiée.\nHarnais attaché en permanence au-delà de 2 m.\n"
     "Balisage de la zone au sol.",
     "Harnais double longe, casque avec jugulaire, chaussures de sécurité.",
     "Ne pas déplacer une personne chutée sauf danger ; appeler les secours ; plan de sauvetage du chantier."),
    ("FS-CONFINE", "Espaces confinés", "confine",
     "Asphyxie, intoxication, atmosphère explosive.",
     "Permis et test gaz (O2, LIE, H2S, CO) avant et pendant l'intervention.\nSurveillant permanent à l'extérieur.\n"
     "Ventilation forcée.",
     "Détecteur 4 gaz, harnais avec ligne de vie, appareil respiratoire selon le permis.",
     "Ne jamais entrer porter secours sans équipement ; donner l'alerte ; plan de sauvetage."),
)


def assurer_fiches_defaut():
    from .models import FicheSecurite

    if FicheSecurite.objects.exists():
        return
    maintenant = timezone.now()
    FicheSecurite.objects.bulk_create([
        FicheSecurite(code=code, titre=titre, categorie=cat, risques=risques, consignes=consignes, epi=epi,
                      urgence=urgence, provisoire=True, statut=FicheSecurite.Statut.PUBLIEE, publiee_le=maintenant)
        for code, titre, cat, risques, consignes, epi, urgence in FICHES_DEFAUT
    ], ignore_conflicts=True)
