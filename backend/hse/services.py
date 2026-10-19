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
        ("Type", incident.get_type_incident_display()), ("Gravité", incident.get_gravite_display()),
        ("Date", f"{incident.date_evenement.astimezone(tz):%d/%m/%Y %H:%M}"), ("Lieu", incident.lieu),
        ("Zone", incident.get_zone_display() if incident.zone else "—"), ("Description", incident.description),
        ("Personnes impliquées", incident.personnes_impliquees), ("Cause immédiate", incident.cause_immediate),
        ("Cause profonde", incident.cause_profonde), ("Conséquences", incident.consequences),
        ("Conséquence humaine", incident.get_consequence_humaine_display()), ("Jours d'arrêt", incident.jours_arret),
        ("Déclaré par", incident.declared_by), ("Enquêteur", incident.enqueteur),
        ("Escalade DG", f"{incident.escalade_dg_le:%d/%m/%Y}" if incident.escalade_dg_le else "—"),
        ("Rapport d'enquête", incident.rapport), ("Retour d'expérience", incident.retour_experience),
        ("Statut", incident.get_statut_display()),
    ]
    actions = [["Action", "Type", "Responsable", "Échéance", "Statut"]] + [
        [a.code, a.get_type_display(), str(a.responsable or "—"), f"{a.echeance:%d/%m/%Y}" if a.echeance else "—",
         a.get_statut_display()]
        for a in incident.actions.select_related("responsable")
    ]
    return _pdf(f"Rapport d'incident {incident.code}", blocs, actions if len(actions) > 1 else None)


def archiver_ged(contenu, nom, titre, type_code, type_label, reference, objet_type, objet_id, user=None, mots=()):
    """PDF scellé SHA-256 en GED (conservation 10 ans) et lié à l'objet HSE pour la recherche juridique."""
    import hashlib

    from django.core.files.base import ContentFile

    from documents.models import Document, DocumentType, Version
    from juridique.models import LienDocument

    type_doc, _ = DocumentType.objects.get_or_create(code=type_code, defaults={"label": type_label, "retention_years": RETENTION_HSE_ANS})
    if (type_doc.retention_years or 0) < RETENTION_HSE_ANS:
        type_doc.retention_years = RETENTION_HSE_ANS
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
                                objet_label=titre[:255], module="M7", note="Archivage réglementaire HSE", created_by=user)
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
}
PREFIXE_FORMATION_RH = "Formation HSE — "


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
    blocs = [("Salarié", p["employe"]), ("Matricule", p["matricule"])]
    if p["aptitude"]:
        a = p["aptitude"]
        blocs.append(("Aptitude médicale", f"{a['resultat']} — visite du {a['visite']:%d/%m/%Y}"
                      + (f", valable jusqu'au {a['validite']:%d/%m/%Y}" if a["validite"] else "")))
    tableau = [["Formation / habilitation", "Obtention", "Validité"]] + [
        [q["intitule"], f"{q['obtention']:%d/%m/%Y}" if q["obtention"] else "—",
         (f"{q['validite']:%d/%m/%Y}" if q["validite"] else "sans échéance") + ("" if q["valide"] else " (expirée)")]
        for q in p["qualifications"]
    ] + [[f"EPI : {e['type']} — {e['designation']}", f"{e['dotation']:%d/%m/%Y}",
          f"{e['renouvellement']:%d/%m/%Y}" if e["renouvellement"] else "—"] for e in p["epi"]]
    return _pdf(f"Passeport sécurité — {p['employe']}", blocs, tableau if len(tableau) > 1 else None)
