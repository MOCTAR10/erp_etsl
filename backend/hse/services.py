"""Droits métier M7 (RF-ERP-60…63) + helpers workflow HSE.

Écriture : Management HSE (pivot 9.3.3 / 9.6.3), Direction des Opérations,
appui RH (formations & EPI, 9.7.3), Logistique (déchets/BSD), Maintenance,
Chefs d'atelier/chantier, Direction, Projets (permis). Validation des permis
et enquêtes incidents = HSE + hiérarchie. Lecture : tous les utilisateurs
authentifiés. Aucun montant financier → pas de masquage.
"""

from django.utils import timezone
from rest_framework.permissions import BasePermission

from users.models import User
from users.rbac import can_read_app
from config.i18n import tr

HSE_WRITE_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.DIRECTEUR_PROJETS,
    User.Role.DIRECTEUR_OPERATIONS,
    User.Role.HSE,
    User.Role.RH,
    User.Role.LOGISTIQUE,
    User.Role.MAINTENANCE,
    User.Role.CHEF_ATELIER,
    User.Role.DIRECTION,
)

# Validation permis + enquêtes : HSE + hiérarchie opérationnelle.
HSE_VALIDATION_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.DIRECTEUR_PROJETS,
    User.Role.DIRECTEUR_OPERATIONS,
    User.Role.HSE,
    User.Role.DIRECTION,
)


def is_admin_or_staff(user):
    return user.is_authenticated and (
        user.is_staff or user.is_superuser or user.role == User.Role.ADMIN
    )


def can_manage_hse(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in HSE_WRITE_ROLES


def can_validate_hse(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in HSE_VALIDATION_ROLES


class CanManageHse(BasePermission):
    """Lecture authentifiée, écriture réservée rôles HSE / opérationnels / RH."""

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return can_read_app(getattr(request, "user", None), "hse")
        return can_manage_hse(getattr(request, "user", None))


class CanValidateHse(BasePermission):
    """Validation permis / clôture incidents : HSE + hiérarchie."""

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return can_read_app(getattr(request, "user", None), "hse")
        return can_validate_hse(getattr(request, "user", None))


# Signataires de chaque niveau du permis de travail (CDC M7 §9.4). L'administrateur peut signer UN niveau.
PERMIS_SIGNATAIRES = {
    "superviseur": (User.Role.CHEF_ATELIER, User.Role.DIRECTEUR_OPERATIONS, User.Role.DIRECTEUR_PROJETS),
    "hse": (User.Role.HSE,),
    "dg": (User.Role.PDG,),
}
PERMIS_NIVEAU_LIBELLES = {"superviseur": "superviseur", "hse": "HSE", "dg": "Direction Générale"}


def peut_signer_niveau(user, niveau):
    if not (user and user.is_authenticated):
        return False
    return user.is_staff or user.role == User.Role.ADMIN or user.role in PERMIS_SIGNATAIRES.get(niveau, ())


def habilitations_manquantes(permis, jour=None):
    """Intervenants du permis sans qualification RH valide pour une exigence de son type (« aucun départ sans habilitation »).

    Retourne la liste des « Nom : mot-clé » manquants. Une qualification sans date de validité ne périme pas.
    """
    from django.db.models import Q
    from django.utils import timezone

    from .models import ExigenceHabilitation

    jour = jour or timezone.localdate()
    exigences = list(ExigenceHabilitation.objects.filter(type_permis=permis.type_permis, actif=True))
    manquantes = []
    for emp in permis.intervenants.all():
        for ex in exigences:
            ok = emp.qualifications.filter(intitule__icontains=ex.mot_cle).filter(
                Q(date_validite__isnull=True) | Q(date_validite__gte=jour)
            ).exists()
            if not ok:
                manquantes.append(f"{emp.nom_complet} : {ex.mot_cle}")
    return manquantes


# ----------------------------------------------------------------------------------------------------------------
# Écarts M7 (2026-10-19) : rapport d'incident PDF, archivage GED 10 ans, registre OSHA
# ----------------------------------------------------------------------------------------------------------------
TYPE_GED_RAPPORT_HSE = "rapports-hse"
TYPE_GED_BSD = "bsd-dechets"
RETENTION_HSE_ANS = 10


def _pdf(titre, blocs, tableau=None):
    import io

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    esc = lambda t: str(t or "—").replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br/>")  # noqa: E731
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, title=titre)
    story = [Paragraph(esc(titre), styles["Title"])]
    for libelle, valeur in blocs:
        story.append(Paragraph(f"<b>{esc(libelle)}</b> : {esc(valeur)}", styles["Normal"]))
    if tableau:
        story.append(Spacer(1, 4 * mm))
        table = Table(tableau)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#12308f")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))
        story.append(table)
    doc.build(story)
    return buf.getvalue()


def rapport_incident_pdf(incident):
    """Rapport d'accident / d'incident (CDC M7-01) : faits, causes, conséquences, enquête, REX, plan d'action."""
    tz = timezone.get_current_timezone()
    blocs = [
        (tr("Type"), incident.get_type_incident_display()), (tr("Gravité"), incident.get_gravite_display()),
        (tr("Date"), f"{incident.date_evenement.astimezone(tz):%d/%m/%Y %H:%M}"), (tr("Lieu"), incident.lieu),
        (tr("Zone"), incident.get_zone_display() if incident.zone else "—"), (tr("Description"), incident.description),
        (tr("Personnes impliquées"), incident.personnes_impliquees), (tr("Cause immédiate"), incident.cause_immediate),
        (tr("Cause profonde"), incident.cause_profonde), (tr("Conséquences"), incident.consequences),
        (tr("Conséquence humaine"), incident.get_consequence_humaine_display()), (tr("Jours d'arrêt"), incident.jours_arret),
        (tr("Déclaré par"), incident.declared_by), (tr("Enquêteur"), incident.enqueteur),
        (tr("Escalade DG"), f"{incident.escalade_dg_le:%d/%m/%Y}" if incident.escalade_dg_le else "—"),
        (tr("Rapport d'enquête"), incident.rapport), (tr("Retour d'expérience"), incident.retour_experience),
        (tr("Statut"), incident.get_statut_display()),
    ]
    actions = [[tr("Action"), tr("Type"), tr("Responsable"), tr("Échéance"), tr("Statut")]] + [
        [a.code, a.get_type_display(), str(a.responsable or "—"), f"{a.echeance:%d/%m/%Y}" if a.echeance else "—",
         a.get_statut_display()]
        for a in incident.actions.select_related("responsable")
    ]
    return _pdf(tr("Rapport d'incident %(incident_code)s") % {"incident_code": incident.code}, blocs, actions if len(actions) > 1 else None)


def archiver_ged(contenu, nom, titre, type_code, type_label, reference, objet_type, objet_id, user=None, mots=(),
                 module="M7", note="Archivage réglementaire HSE", retention=RETENTION_HSE_ANS):
    """PDF scellé SHA-256 en GED (conservation 10 ans) et lié à l'objet HSE pour la recherche juridique."""
    import hashlib

    from django.core.files.base import ContentFile

    from documents.models import Document, DocumentType, Version
    from juridique.models import LienDocument

    type_doc, _ = DocumentType.objects.get_or_create(code=type_code, defaults={"label": type_label, "retention_years": retention})
    if (type_doc.retention_years or 0) < retention:
        type_doc.retention_years = retention
        type_doc.save(update_fields=["retention_years"])
    sha = hashlib.sha256(contenu).hexdigest()
    document = Document.objects.create(
        title=titre[:200], status=Document.Status.ARCHIVED, archived_at=timezone.now(), type=type_doc,
        document_date=timezone.localdate(), reference=reference[:120], keywords=list(mots), sha256=sha, created_by=user,
    )
    version = Version.objects.create(document=document, number=1, file=ContentFile(contenu, name=nom), sha256=sha,
                                     size=len(contenu), original_filename=nom, created_by=user)
    document.current_version = version
    document.save(update_fields=["current_version"])
    LienDocument.objects.create(document=document, objet_type=objet_type, objet_id=str(objet_id),
                                objet_label=titre[:255], module=module, note=note, created_by=user)
    return document


def bsd_pdf(bsd):
    blocs = [
        ("Type de déchet", bsd.get_type_dechet_display()), ("Quantité", f"{bsd.quantite} {getattr(bsd, 'unite', '')}"),
        ("Transporteur", getattr(bsd, "transporteur", "")), ("N° BSD", getattr(bsd, "numero_bsd", "")),
        ("Destination", getattr(bsd, "destination", "")), ("Statut", bsd.get_statut_display()),
    ]
    return _pdf(f"Bordereau de suivi des déchets {bsd.code}", blocs)


def registre_osha(annee):
    """Registre des cas enregistrables de l'année (modèle OSHA 300 / reporting OILGUARD) + synthèse (OSHA 300A)."""
    from .models import Incident

    rows = []
    for inc in Incident.objects.filter(date_evenement__year=annee).order_by("date_evenement"):
        if not inc.classification_osha:
            continue
        rows.append({
            "cas": inc.code, "date": timezone.localtime(inc.date_evenement).date(), "lieu": inc.lieu,
            "zone": inc.get_zone_display() if inc.zone else "", "personnes": inc.personnes_impliquees,
            "description": inc.description, "classification": inc.classification_osha,
            "jours_arret": inc.jours_arret, "gravite": inc.gravite,
        })
    synthese = {c: sum(1 for r in rows if r["classification"] == c) for c in ("deces", "arret", "restriction", "autre_enregistrable")}
    synthese["jours_arret"] = sum(r["jours_arret"] for r in rows)
    synthese["cas_enregistrables"] = len(rows)
    return {"annee": annee, "rows": rows, "synthese": synthese}


# ----------------------------------------------------------------------------------------------------------------
# Écarts M7-B : paramètres, flux formations → qualifications RH, passeport sécurité, fiche de dotation EPI
# ----------------------------------------------------------------------------------------------------------------
PARAMETRES_HSE_DEFAUT = {
    "EPI_ALERTE_JOURS": ("EPI : alerte avant renouvellement", "30", "jours"),
    "APTITUDE_ALERTE_JOURS": ("Aptitude médicale : alerte avant échéance", "30", "jours"),
    # Facteurs d'émission (kg CO2e par unité) : valeurs usuelles provisoires, à confirmer par ETSL (réseau SEEG, carburants).
    "FE_ELECTRICITE": ("Facteur d'émission électricité", "0.40", "kg CO2e/kWh"),
    "FE_GAZOLE": ("Facteur d'émission gazole", "2.68", "kg CO2e/L"),
    "FE_ESSENCE": ("Facteur d'émission essence", "2.28", "kg CO2e/L"),
    "FE_GAZ": ("Facteur d'émission gaz (GPL)", "2.94", "kg CO2e/kg"),
}
PREFIXE_FORMATION_RH = "Formation HSE — "

# Écarts M7 (lot ecarts-m6m7) : seuils de cotation, revue du DUER, agrément BSD, plan de prévention sur site GR.
from .ecarts_m6m7 import PARAMETRES_M6M7  # noqa: E402

PARAMETRES_HSE_DEFAUT.update(PARAMETRES_M6M7)


def get_param_hse(code):
    from decimal import Decimal

    from .models import ParametreHse

    label, valeur, unite = PARAMETRES_HSE_DEFAUT[code]
    obj, _ = ParametreHse.objects.get_or_create(code=code, defaults={"label": label, "valeur": Decimal(valeur), "unite": unite})
    return obj.valeur


def _ajouter_mois(jour, mois):
    import calendar

    annee, m = divmod(jour.month - 1 + mois, 12)
    annee += jour.year
    m += 1
    return jour.replace(year=annee, month=m, day=min(jour.day, calendar.monthrange(annee, m)[1]))


def publier_formation_rh(formation):
    """Flux M7 → M9 : une session réalisée devient une qualification RH (certificat) de chaque participant, avec son
    échéance de recyclage ; l'exigence d'habilitation par mot-clé la reconnaît. Idempotent."""
    from rh_paie.models import Qualification

    validite = _ajouter_mois(formation.date_session, formation.validite_mois) if formation.validite_mois else None
    intitule = f"{PREFIXE_FORMATION_RH}{formation.theme}"[:180]
    crees = 0
    for emp in formation.participants.all():
        _, cree = Qualification.objects.get_or_create(
            employe=emp, intitule=intitule, date_obtention=formation.date_session,
            defaults={"type": Qualification.Type.CERTIFICAT, "organisme": formation.organisme or formation.formateur,
                      "date_validite": validite, "notes": f"Session HSE {formation.code}"},
        )
        crees += int(cree)
    return crees


def passeport_securite(employe, jour=None):
    """Passeport sécurité (CDC M7-05) : formations HSE, habilitations / certificats RH, aptitude médicale, EPI dotés."""
    from django.db.models import Q

    from .models import Epi

    jour = jour or timezone.localdate()
    qualifs = employe.qualifications.all().order_by("-date_obtention")
    aptitude = employe.aptitudes.order_by("-date_visite").first()
    filtre = Q(employe=employe) | (Q(beneficiaire_id=employe.user_id) if employe.user_id else Q(pk__in=[]))
    epi = Epi.objects.filter(filtre).order_by("-date_dotation")
    return {
        "employe": str(employe), "matricule": employe.code,
        "formations": [
            {"code": f.code, "theme": f.theme, "date": f.date_session, "type": f.get_type_session_display()}
            for f in employe.formations_hse.order_by("-date_session")
        ],
        "qualifications": [
            {"intitule": q.intitule, "type": q.get_type_display(), "obtention": q.date_obtention, "validite": q.date_validite,
             "valide": q.date_validite is None or q.date_validite >= jour}
            for q in qualifs
        ],
        "aptitude": None if aptitude is None else {
            "resultat": aptitude.get_resultat_display(), "visite": aptitude.date_visite, "validite": aptitude.date_validite,
            "restrictions": aptitude.restrictions,
            "valide": aptitude.resultat != "inapte" and (aptitude.date_validite is None or aptitude.date_validite >= jour),
        },
        "epi": [
            {"code": e.code, "type": e.get_type_epi_display(), "designation": e.designation, "dotation": e.date_dotation,
             "renouvellement": e.date_renouvellement, "statut": e.get_statut_display()}
            for e in epi.distinct()
        ],
    }


def passeport_pdf(employe):
    p = passeport_securite(employe)
    blocs = [(tr("Salarié"), p["employe"]), (tr("Matricule"), p["matricule"])]
    if p["aptitude"]:
        a = p["aptitude"]
        blocs.append((tr("Aptitude médicale"), tr("%(resultat)s — visite du %(visite)s") % {"resultat": a['resultat'], "visite": format(a['visite'], '%d/%m/%Y')}
                      + (tr(", valable jusqu'au %(validite)s") % {"validite": format(a['validite'], '%d/%m/%Y')} if a["validite"] else "")))
    tableau = [[tr("Formation / habilitation"), tr("Obtention"), tr("Validité")]] + [
        [q["intitule"], f"{q['obtention']:%d/%m/%Y}" if q["obtention"] else "—",
         (f"{q['validite']:%d/%m/%Y}" if q["validite"] else tr("sans échéance")) + ("" if q["valide"] else tr(" (expirée)"))]
        for q in p["qualifications"]
    ] + [[tr("EPI : %(type)s — %(designation)s") % {"type": e["type"], "designation": e["designation"]}, f"{e['dotation']:%d/%m/%Y}",
          f"{e['renouvellement']:%d/%m/%Y}" if e["renouvellement"] else "—"] for e in p["epi"]]
    return _pdf(tr("Passeport sécurité — %(employe)s") % {"employe": p['employe']}, blocs, tableau if len(tableau) > 1 else None)


# ----------------------------------------------------------------------------------------------------------------
# Écarts M7-C : environnement ISO 14001, indicateurs formation / recyclage / ISO, bilan annuel, revue de direction
# ----------------------------------------------------------------------------------------------------------------
TYPES_INCIDENT_ENVIRONNEMENT = ("pollution", "deversement")


def _dec(valeur):
    from decimal import Decimal

    return str(Decimal(valeur).quantize(Decimal("0.01")))


def consommations_annee(annee):
    """Totaux de l'année par ressource (quantité + émissions kg CO2e au facteur paramétré)."""
    from decimal import Decimal

    from django.db.models import Sum

    from .models import ConsommationEnvironnement as C

    totaux = dict(
        C.objects.filter(periode__year=annee).values_list("ressource").annotate(total=Sum("quantite")).values_list("ressource", "total")
    )
    lignes, emissions = [], Decimal("0")
    for code, libelle in C.Ressource.choices:
        quantite = totaux.get(code) or Decimal("0")
        facteur = get_param_hse(C.FACTEURS[code]) if code in C.FACTEURS else None
        em = quantite * facteur if facteur is not None else None
        emissions += em or 0
        lignes.append({"ressource": code, "libelle": libelle, "unite": C.UNITES[code], "quantite": _dec(quantite),
                       "facteur": None if facteur is None else str(facteur),
                       "emissions_kg_co2e": None if em is None else _dec(em)})
    return {"lignes": lignes, "emissions_kg_co2e": _dec(emissions), "emissions_t_co2e": _dec(emissions / 1000)}


def avancement_plan(plan):
    """Réduction réalisée (%) : consommation de la dernière année relevée (≤ année cible) vs l'année de référence."""
    from django.db.models import Sum

    from .models import ConsommationEnvironnement as C

    if not plan.ressource or not plan.annee_reference:
        return None
    par_an = dict(
        C.objects.filter(ressource=plan.ressource, periode__year__gte=plan.annee_reference, periode__year__lte=plan.annee_cible)
        .values_list("periode__year").annotate(t=Sum("quantite")).values_list("periode__year", "t")
    )
    reference = par_an.get(plan.annee_reference)
    suivies = [a for a in par_an if a > plan.annee_reference]
    if not reference or not suivies:
        return {"reference": _dec(reference or 0), "derniere_annee": None, "realise_pct": None, "atteint": False}
    derniere = max(suivies)
    realise = (reference - par_an[derniere]) * 100 / reference
    return {"reference": _dec(reference), "derniere_annee": derniere, "derniere_valeur": _dec(par_an[derniere]),
            "realise_pct": _dec(realise), "atteint": realise >= plan.reduction_cible_pct}


def indicateurs_hse(debut, fin, heures):
    """Indicateurs M7-07 au-delà des taux de fréquence : formation, recyclage, conformité ISO, incidents environnement.

    - taux de formation = salariés actifs ayant suivi au moins une session HSE réalisée sur la période / salariés actifs ;
    - taux de recyclage = habilitations issues des formations HSE (avec échéance) encore valides à la fin de période ;
    - conformité ISO = score moyen des audits HSE réalisés sur la période (0-100) ;
    - taux d'incidents environnementaux = pollutions + déversements × 200 000 / heures.
    """
    from decimal import Decimal

    from django.db.models import Avg

    from rh_paie.models import Employe, Qualification

    from .indicateurs import BASE_OSHA, _taux
    from .models import AuditHse, FormationSecurite, Incident

    actifs = Employe.objects.filter(statut=Employe.Statut.ACTIF)
    nb_actifs = actifs.count()
    formes = actifs.filter(
        formations_hse__statut=FormationSecurite.Statut.REALISEE,
        formations_hse__date_session__gte=debut, formations_hse__date_session__lte=fin,
    ).distinct().count()
    # Dernière occurrence de chaque habilitation HSE par salarié : valide à `fin` ou à recycler.
    dernieres = {}
    for q in Qualification.objects.filter(intitule__startswith=PREFIXE_FORMATION_RH, date_validite__isnull=False,
                                          employe__in=actifs).order_by("date_obtention"):
        dernieres[(q.employe_id, q.intitule)] = q
    a_jour = sum(1 for q in dernieres.values() if q.date_validite >= fin)
    audits = AuditHse.objects.filter(date_realisation__gte=debut, date_realisation__lte=fin, score__isnull=False)
    score = audits.aggregate(m=Avg("score"))["m"]
    nb_env = Incident.objects.filter(
        type_incident__in=TYPES_INCIDENT_ENVIRONNEMENT, date_evenement__date__gte=debut, date_evenement__date__lte=fin
    ).count()
    pct = lambda n, d: None if not d else _dec(Decimal(n) * 100 / d)  # noqa: E731
    return {
        "salaries_actifs": nb_actifs, "salaries_formes": formes, "taux_formation": pct(formes, nb_actifs),
        "habilitations_suivies": len(dernieres), "habilitations_a_jour": a_jour, "taux_recyclage": pct(a_jour, len(dernieres)),
        "audits_realises": audits.count(), "conformite_iso": None if score is None else _dec(score),
        "incidents_environnement": nb_env, "taux_incidents_environnement": _taux(nb_env, BASE_OSHA, Decimal(heures)),
    }


def bilan_annuel(annee):
    """Bilan HSE annuel (CDC §9.8) : données d'entrée de la revue de direction."""
    from datetime import date

    from django.db.models import Count, Sum

    from .indicateurs import indicateurs_frequence
    from .models import ActionHse, AuditHse, BordereauDechet, FormationSecurite, Incident, PermisTravail, PlanReductionImpact

    debut, fin = date(annee, 1, 1), date(annee, 12, 31)
    freq = indicateurs_frequence(debut, fin)
    incidents = Incident.objects.filter(date_evenement__year=annee)
    par_type = {Incident.TypeIncident(t).label: n for t, n in incidents.values_list("type_incident").annotate(n=Count("id"))}
    dechets = [
        {"type": BordereauDechet.TypeDechet(t).label, "unite": u, "quantite": _dec(q)}
        for t, u, q in BordereauDechet.objects.filter(created_at__year=annee).values_list("type_dechet", "unite")
        .annotate(q=Sum("quantite")).values_list("type_dechet", "unite", "q")
    ]
    plans = [
        {"code": p.code, "objectif": p.objectif, "statut": p.get_statut_display(), "annee_cible": p.annee_cible,
         "cible_pct": None if p.reduction_cible_pct is None else str(p.reduction_cible_pct), "avancement": avancement_plan(p)}
        for p in PlanReductionImpact.objects.all()
    ]
    return {
        "annee": annee,
        "frequence": {k: (str(v) if k in ("debut", "fin") else v) for k, v in freq.items()},
        "indicateurs": indicateurs_hse(debut, fin, freq["heures"]),
        "incidents": {"total": incidents.count(), "par_type": par_type,
                      "clotures": incidents.filter(statut=Incident.Statut.CLOTURE).count()},
        "registre_osha": registre_osha(annee)["synthese"],
        "permis": PermisTravail.objects.filter(date_debut__year=annee).count(),
        "formations": FormationSecurite.objects.filter(date_session__year=annee, statut=FormationSecurite.Statut.REALISEE).count(),
        "audits": AuditHse.objects.filter(date_realisation__year=annee).count(),
        "actions_ouvertes": ActionHse.objects.exclude(statut=ActionHse.Statut.CLOTUREE).count(),
        "environnement": consommations_annee(annee),
        "dechets": dechets,
        "plans_reduction": plans,
    }


def bilan_pdf(bilan, titre, revue=None):
    f, i = bilan["frequence"], bilan["indicateurs"]
    nd = lambda v, s="": "—" if v is None else f"{v}{s}"  # noqa: E731
    blocs = [
        (tr("Heures travaillées"), f["heures"]), (tr("TRIR / LTIR / LTIFR"), f"{nd(f['trir'])} / {nd(f['ltir'])} / {nd(f['ltifr'])}"),
        (tr("Cas enregistrables / avec arrêt"), tr("%(enregistrables)s / %(avec_arret)s (%(jours_perdus)s jours perdus)") % {"enregistrables": f['enregistrables'], "avec_arret": f['avec_arret'], "jours_perdus": f['jours_perdus']}),
        (tr("Incidents (clôturés)"), f"{bilan['incidents']['total']} ({bilan['incidents']['clotures']})"),
        (tr("Par type"), ", ".join(f"{k} : {v}" for k, v in bilan["incidents"]["par_type"].items()) or "—"),
        (tr("Taux de formation"), nd(i["taux_formation"], " %")), (tr("Taux de recyclage à jour"), nd(i["taux_recyclage"], " %")),
        (tr("Conformité ISO (score moyen des audits)"), nd(i["conformite_iso"], " %")),
        (tr("Incidents environnementaux"), tr("%(incidents_environnement)s (taux %(nd)s)") % {"incidents_environnement": i['incidents_environnement'], "nd": nd(i['taux_incidents_environnement'])}),
        (tr("Permis / formations / audits"), f"{bilan['permis']} / {bilan['formations']} / {bilan['audits']}"),
        (tr("Actions HSE ouvertes"), bilan["actions_ouvertes"]),
        (tr("Émissions"), f"{bilan['environnement']['emissions_t_co2e']} t CO2e"),
        (tr("Déchets"), ", ".join(f"{d['type']} : {d['quantite']} {d['unite']}" for d in bilan["dechets"]) or "—"),
        (tr("Plans de réduction"), "; ".join(
            f"{p['code']} {p['objectif']} ({p['statut']}"
            + (tr(", réalisé %(realise_pct)s %% / %(cible_pct)s %%") % {"realise_pct": p['avancement']['realise_pct'], "cible_pct": p['cible_pct']} if p["avancement"] and p["avancement"]["realise_pct"] else "")
            + ")" for p in bilan["plans_reduction"]) or "—"),
    ]
    if revue is not None:
        blocs += [(tr("Date de la revue"), f"{revue.date_revue:%d/%m/%Y}"), (tr("Participants"), revue.participants),
                  (tr("Conclusions"), revue.conclusions), (tr("Décisions"), revue.decisions),
                  (tr("Validée par"), revue.validee_par), (tr("Validée le"), f"{revue.validee_le:%d/%m/%Y}" if revue.validee_le else "—")]
    tableau = [[tr("Ressource"), tr("Quantité"), tr("Unité"), tr("kg CO2e")]] + [
        [lg["libelle"], lg["quantite"], lg["unite"], lg["emissions_kg_co2e"] or "—"] for lg in bilan["environnement"]["lignes"]
    ]
    return _pdf(titre, blocs, tableau)


# ----------------------------------------------------------------------------------------------------------------
# Écarts M7-D : permis (signataire suivant prévenu, expiration), coûts HSE analytiques (M11)
# ----------------------------------------------------------------------------------------------------------------
PIECES_PERMIS = {"photo": (".jpg", ".jpeg", ".png", ".webp", ".heic"), "plan": (".pdf", ".jpg", ".jpeg", ".png")}
PIECE_TAILLE_MAX = 10 * 1024 * 1024


def signataires_niveau(niveau):
    return User.objects.filter(is_active=True, role__in=PERMIS_SIGNATAIRES.get(niveau, ()))


def notifier_niveau_suivant(permis):
    """Alerte (notification, email, SMS si configuré) des signataires du prochain visa : « permis imminent à valider »."""
    from workflow.notifications import notify

    niveau = permis.prochain_niveau
    if niveau is None:
        return 0
    sujet = f"Permis {permis.code} à valider (visa {PERMIS_NIVEAU_LIBELLES.get(niveau, niveau)})"
    message = (f"{permis.get_type_permis_display()} — {permis.emplacement}, début le {permis.date_debut:%d/%m/%Y}. "
               "Merci de viser ou refuser le permis.")
    n = 0
    for user in signataires_niveau(niveau).exclude(pk=permis.demandeur_id):
        notify(user, sujet, message, kind="reminder", sms=True)
        n += 1
    return n


def expirer_permis(jour=None):
    """Permis validés ou actifs dont la date de fin est passée → « expiré » ; demandeur et HSE prévenus."""
    from workflow.notifications import notify

    from .models import PermisTravail

    jour = jour or timezone.localdate()
    expires = list(PermisTravail.objects.filter(
        statut__in=(PermisTravail.Statut.VALIDE, PermisTravail.Statut.ACTIF), date_fin__lt=jour,
    ))
    hse = list(User.objects.filter(is_active=True, role=User.Role.HSE))
    for permis in expires:
        permis.statut = PermisTravail.Statut.EXPIRE
        permis.notes = (permis.notes + "\n" if permis.notes else "") + f"Expiré le {jour:%d/%m/%Y} (fin prévue le {permis.date_fin:%d/%m/%Y})."
        permis.save(update_fields=["statut", "notes", "updated_at"])
        for user in {u.pk: u for u in hse + ([permis.demandeur] if permis.demandeur else [])}.values():
            notify(user, f"Permis {permis.code} expiré", f"Le permis {permis.code} ({permis.emplacement}) est arrivé à "
                   "échéance : travaux à arrêter ou nouveau permis à demander.", kind="reminder")
    return len(expires)


#: Centres de coût HSE (axe « Centre de coût ») : imputation analytique des achats et charges HSE (CDC M7 → M11).
CENTRES_HSE = (
    ("HSE-EPI", "HSE — EPI et équipements de sécurité"),
    ("HSE-FORM", "HSE — formations et habilitations"),
    ("HSE-MED", "HSE — médecine du travail"),
    ("HSE-DECH", "HSE — déchets et BSD"),
    ("HSE-ENV", "HSE — environnement (mesures, analyses)"),
    ("HSE-SEC", "HSE — sécurité chantier et divers"),
)


def centres_hse():
    """Crée au besoin l'axe « Centre de coût » et les centres HSE ; idempotent."""
    from referentiels.models import AnalyticAccount, AnalyticAxis

    axe, _ = AnalyticAxis.objects.get_or_create(
        code="AX-CC", defaults={"label": "Centre de coût", "axis_type": AnalyticAxis.AxisType.CENTRE_COUT}
    )
    return [AnalyticAccount.objects.get_or_create(axis=axe, code=code, defaults={"label": label})[0] for code, label in CENTRES_HSE]


def couts_hse(annee):
    """Charges (classe 6, écritures comptabilisées) imputées aux centres HSE : par centre et par mois, sans ressaisie."""
    from decimal import Decimal

    from django.db.models import Sum
    from django.db.models.functions import ExtractMonth

    from accounting_kernel.models import AccountMove, AccountMoveLine

    centres = centres_hse()
    lignes = (
        AccountMoveLine.objects.filter(
            move__status__in=(AccountMove.Status.POSTED, AccountMove.Status.REVERSED), move__date__year=annee,
            account__account_class=6, analytic_account__in=centres,
        )
        .annotate(mois=ExtractMonth("move__date"))
        .values("analytic_account_id", "mois")
        .annotate(debit=Sum("debit"), credit=Sum("credit"))
    )
    par_centre = {c.pk: {"centre": c.code, "libelle": c.label, "analytic": c.pk, "mois": [Decimal("0")] * 12} for c in centres}
    for lg in lignes:
        par_centre[lg["analytic_account_id"]]["mois"][lg["mois"] - 1] += (lg["debit"] or 0) - (lg["credit"] or 0)
    rows = [{**r, "total": sum(r["mois"], Decimal("0"))} for r in par_centre.values()]
    return {"annee": annee, "rows": rows, "total": sum((r["total"] for r in rows), Decimal("0"))}
