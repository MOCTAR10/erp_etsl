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
    "PREVENTIF_PREALERTE_JOURS": ("Préventif : pré-alerte avant l'échéance calendaire", Decimal("7"), "jours"),
    "PREVENTIF_PREALERTE_PCT": ("Préventif : pré-alerte avant le seuil compteur (part de l'intervalle)", Decimal("10"), "%"),
    "SEUIL_DISPONIBILITE_PCT": ("Fiabilité : disponibilité minimale attendue par machine", Decimal("90"), "%"),
    "SEUIL_MTBF_H": ("Fiabilité : MTBF minimal attendu par machine", Decimal("500"), "heures"),
    "TAUX_HORAIRE_DEFAUT": ("Coût OT : taux horaire de main-d'œuvre par défaut (OT sans taux saisi)", Decimal("15000"),
                            "FCFA/h"),
    "COMPTE_ENTRETIEN": ("Coût OT : compte de charge d'entretien (hors GLOBAL RENTAL, 618 sinon)", Decimal("624000"),
                         "compte"),
    "COMPTE_CONTREPARTIE_MO": ("Coût OT : compte crédité pour la main-d'œuvre interne (transfert)", Decimal("661000"),
                               "compte"),
    "COMPTE_CONTREPARTIE_PIECES": ("Coût OT : compte crédité pour les pièces sorties du stock", Decimal("603300"),
                                   "compte"),
}
CODES_FIABILITE = ("OBSERVATION_JOURS", "HEURES_PAR_JOUR", "SEUIL_DISPONIBILITE_PCT", "SEUIL_MTBF_H")
ROLES_ALERTE_MAINTENANCE = (User.Role.MAINTENANCE, User.Role.DIRECTEUR_OPERATIONS)
TYPE_GED_RAPPORT_OT = "rapports-maintenance"
RETENTION_RAPPORT_OT_ANS = 10
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
    seuil_dispo = get_param_maintenance("SEUIL_DISPONIBILITE_PCT")
    seuil_mtbf = get_param_maintenance("SEUIL_MTBF_H")
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
        mtbf = ((requises - arret) / pannes).quantize(CENT, rounding=ROUND_HALF_UP) if pannes else None
        alertes = []
        if dispo is not None and dispo < seuil_dispo:
            alertes.append(f"disponibilité {dispo} % < {seuil_dispo} %")
        if mtbf is not None and mtbf < seuil_mtbf:
            alertes.append(f"MTBF {mtbf} h < {seuil_mtbf} h")
        rows.append({
            "actif": actif.code, "designation": actif.designation, "gr": actif.is_global_rental,
            "pannes": pannes, "heures_arret": arret, "heures_requises": requises,
            "mttr_h": (arret / pannes).quantize(CENT, rounding=ROUND_HALF_UP) if pannes else None,
            "mtbf_h": mtbf,
            "disponibilite_pct": dispo,
            "alertes": alertes,
        })
    return {
        "observation_jours": obs, "heures_par_jour": h_jour,
        "seuil_disponibilite_pct": seuil_dispo, "seuil_mtbf_h": seuil_mtbf,
        "provisoire": parametres_maintenance_provisoires(CODES_FIABILITE), "rows": rows,
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
        from .ecarts_m5m8 import centre_actif

        ligne = par_actif.setdefault(ot.actif_id, {
            "actif": ot.actif.code, "designation": ot.actif.designation, "gr": gr,
            "centre": centre_actif(ot.actif).code,
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


# --------------------------------------------------------------------------------------------------
# Pièces de rechange : sortie du stock M5 liée à l'OT, valorisation CUMP, réappro sous seuil
# --------------------------------------------------------------------------------------------------
STATUTS_SORTIE_PIECE = ("planifie", "en_cours")
TITRE_DA_REAPPRO = "Réapprovisionnement pièces de rechange (M8)"


def sortir_piece(ot, article, depot, quantite, user):
    """Sortie d'une pièce du stock M5 pour `ot` (appelé sous verrou de l'OT) ; lève ValueError si refusée."""
    from stocks.models import MouvementStock
    from stocks.services import apply_move

    from .models import PieceOT

    if ot.statut not in STATUTS_SORTIE_PIECE:
        raise ValueError("Les pièces se sortent sur un OT planifié ou en cours.")
    if quantite <= 0:
        raise ValueError("La quantité doit être strictement positive.")
    mouvement = MouvementStock(
        type_mouvement=MouvementStock.Type.CONSOMMATION, article=article, quantite=quantite, source=depot,
        document_reference=ot.code, date=timezone.localdate(), created_by=user,
        notes=f"Pièce de rechange — OT {ot.code} ({ot.actif.code})",
    )
    mouvement.clean()
    mouvement.save()
    apply_move(mouvement)  # ValueError si stock insuffisant, lot bloqué…
    piece = PieceOT.objects.create(
        ot=ot, article=article, depot=depot, quantite=quantite, cout_unitaire=mouvement.cout_unitaire,
        mouvement=mouvement, sorti_par=user,
    )
    ot.cout_pieces = (ot.cout_pieces + piece.cout_total).quantize(CENT, rounding=ROUND_HALF_UP)
    ot.save(update_fields=["cout_pieces", "updated_at"])
    return piece


def besoins_reappro():
    """Pièces de rechange (déjà sorties pour un OT) dont le stock total est sous le seuil minimum M5."""
    from django.db.models import Sum

    from stocks.models import ArticleStock

    from .models import PieceOT

    articles = PieceOT.objects.values_list("article_id", flat=True).distinct()
    rows = []
    for cfg in ArticleStock.objects.filter(
        article_id__in=articles, is_active=True, seuil_minimal__gt=0
    ).select_related("article"):
        stock = cfg.article.quants.aggregate(t=Sum("quantity"))["t"] or Decimal("0")
        if stock < cfg.seuil_minimal:
            rows.append({
                "article_id": cfg.article_id, "article": cfg.article.code, "designation": cfg.article.label,
                "stock": stock, "seuil": cfg.seuil_minimal, "a_commander": cfg.seuil_minimal - stock,
            })
    return rows


def generer_da_reappro(user):
    """DA brouillon (M2) pour les pièces sous seuil ; idempotent : une pièce déjà demandée n'est pas redemandée."""
    from achats.models import PurchaseRequest, PurchaseRequestLine

    besoins = besoins_reappro()
    deja = set(
        PurchaseRequestLine.objects.filter(
            request__title=TITRE_DA_REAPPRO, request__status__in=("brouillon", "soumise", "approuvee")
        ).values_list("article_id", flat=True)
    )
    a_ajouter = [b for b in besoins if b["article_id"] not in deja]
    if not a_ajouter:
        return {"da": None, "lignes_ajoutees": 0}
    da = PurchaseRequest.objects.filter(title=TITRE_DA_REAPPRO, status="brouillon").first()
    if da is None:
        da = PurchaseRequest.objects.create(title=TITRE_DA_REAPPRO, requester=user, department="Maintenance")
    from referentiels.models import Article

    for b in a_ajouter:
        art = Article.objects.get(pk=b["article_id"])
        PurchaseRequestLine.objects.create(
            request=da, article=art, label=art.label, quantity=b["a_commander"], unit=art.unit,
            estimated_price=art.purchase_price or 0,
        )
    return {"da": da.code, "lignes_ajoutees": len(a_ajouter)}


def prealerte_parametres():
    """(jours, pct) de la pré-alerte préventive, paramètres provisoires tant qu'ETSL ne les confirme pas."""
    return int(get_param_maintenance("PREVENTIF_PREALERTE_JOURS")), get_param_maintenance("PREVENTIF_PREALERTE_PCT")


def calendrier_preventif(periode, aujourdhui=None):
    """Calendrier mensuel des plans préventifs en vigueur (CDC M8.2 / §13.4).

    Plans calendaires : occurrences projetées à la périodicité depuis la prochaine échéance ; une échéance passée
    non traitée reste affichée comme échue. Plans au compteur : seuil restant, sans date (non prévisible).
    """
    from .models import PlanPreventif

    try:
        annee, mois = (int(x) for x in periode.split("-"))
        debut = date(annee, mois, 1)
    except (ValueError, AttributeError):
        raise ValueError("Période attendue au format AAAA-MM.")
    fin = (debut.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    aujourdhui = aujourdhui or timezone.localdate()
    jours_pa, pct_pa = prealerte_parametres()
    occurrences, compteurs = [], []
    for plan in PlanPreventif.objects.filter(en_vigueur=True).select_related("actif", "actif__equipement_gr"):
        base = {
            "plan": plan.code, "actif": plan.actif.code, "designation": plan.actif.designation,
            "libelle": plan.libelle, "composant": plan.composant, "priorite": plan.priorite,
        }
        if plan.periodicite_jours:
            pas = timedelta(days=plan.periodicite_jours)
            d = plan.prochaine_date
            if d < debut:
                if d <= aujourdhui and debut <= aujourdhui <= fin:
                    occurrences.append({**base, "date": d, "echu": True})
                d += pas * -(-(debut - d).days // plan.periodicite_jours)
            while d <= fin:
                occurrences.append({**base, "date": d, "echu": d <= aujourdhui})
                d += pas
        if plan.intervalle_compteur is not None:
            compteurs.append({
                **base, "compteur_actuel": plan.actif.compteur_lecture, "prochain_compteur": plan.prochain_compteur,
                "echeance": plan.motif_echeance(aujourdhui),
                "prealerte": plan.motif_prealerte(aujourdhui, jours_pa, pct_pa),
            })
    occurrences.sort(key=lambda o: (o["date"], o["actif"]))
    return {
        "periode": f"{debut:%Y-%m}", "debut": debut, "fin": fin, "occurrences": occurrences, "compteurs": compteurs,
        "prealerte_jours": jours_pa, "prealerte_pct": pct_pa,
        "provisoire": parametres_maintenance_provisoires(("PREVENTIF_PREALERTE_JOURS", "PREVENTIF_PREALERTE_PCT")),
    }


def habilitations_technicien_manquantes(ot, jour=None):
    """Habilitations exigées pour l'OT (catégorie d'équipement, type) que son technicien n'a pas, qualification RH
    valide à `jour` (sans date de validité = valable). Liste vide si aucune exigence ne s'applique."""
    from django.db.models import Q

    from rh_paie.models import Employe

    from .models import ExigenceHabilitationMaintenance

    jour = jour or timezone.localdate()
    exigences = list(
        ExigenceHabilitationMaintenance.objects.filter(actif=True)
        .filter(Q(categorie_actif="") | Q(categorie_actif=ot.actif.categorie))
        .filter(Q(type_ot="") | Q(type_ot=ot.type_ot))
    )
    if not exigences:
        return []
    if not ot.technicien_id:
        return ["technicien non désigné"]
    employe = Employe.objects.filter(user_id=ot.technicien_id).first()
    if employe is None:
        return [f"{ot.technicien} : aucune fiche salarié (qualifications introuvables)"]
    valides = employe.qualifications.filter(Q(date_validite__isnull=True) | Q(date_validite__gte=jour))
    return [ex.mot_cle for ex in exigences if not valides.filter(intitule__icontains=ex.mot_cle).exists()]


def _notifier_roles(sujet, message):
    """Notification interne aux rôles maintenance, une seule fois par sujet (le sujet porte l'échéance)."""
    from workflow.models import Notification
    from workflow.notifications import notify

    envoyees = 0
    for user in User.objects.filter(role__in=ROLES_ALERTE_MAINTENANCE, is_active=True):
        if Notification.objects.filter(user=user, subject=sujet).exists():
            continue
        notify(user, sujet[:255], message, kind="reminder")
        envoyees += 1
    return envoyees


def notifier_maintenance(aujourdhui=None):
    """Pré-alertes préventives (une fois par échéance) et machines sous les seuils de fiabilité (une fois par mois)."""
    from .models import PlanPreventif

    aujourdhui = aujourdhui or timezone.localdate()
    jours, pct = prealerte_parametres()
    envoyees = 0
    for plan in PlanPreventif.objects.filter(en_vigueur=True).select_related("actif", "actif__equipement_gr"):
        motif = plan.motif_prealerte(aujourdhui, jours, pct)
        if motif:
            cible = plan.prochaine_date.isoformat() if plan.prochaine_date else str(plan.prochain_compteur)
            envoyees += _notifier_roles(
                f"Pré-alerte préventive {plan.code} ({cible}) : {plan.actif.code} — {plan.libelle}",
                f"Le plan {plan.code} ({plan.actif.designation}) arrive à échéance : {motif}. Préparer l'intervention.",
            )
    for row in fiabilite_actifs(aujourdhui)["rows"]:
        if row["alertes"]:
            envoyees += _notifier_roles(
                f"Fiabilité {aujourdhui:%Y-%m} sous le seuil : {row['actif']} — {row['designation']}",
                f"{row['designation']} ({row['actif']}) : {' ; '.join(row['alertes'])}. Analyser les pannes et le plan préventif.",
            )
    return envoyees


def rapport_ot_pdf(ot):
    """Rapport d'intervention PDF (reportlab) : identification, déroulé horodaté, pièces, main-d'œuvre."""
    import io

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, title=ot.code)
    esc = lambda t: str(t or "—").replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br/>")  # noqa: E731
    story = [
        Paragraph(f"Rapport d'intervention {ot.code}", styles["Title"]),
        Paragraph(f"Équipement : <b>{esc(ot.actif.designation)}</b> ({ot.actif.code}) · {ot.get_type_ot_display()} · "
                  f"priorité {ot.get_priorite_display().lower()}", styles["Normal"]),
        Paragraph(f"Technicien : {esc(ot.technicien)} · demandé le {ot.date_demande:%d/%m/%Y}", styles["Normal"]),
        Spacer(1, 4 * mm),
        Paragraph(f"<b>Demande</b> : {esc(ot.description)}", styles["Normal"]),
        Paragraph(f"<b>Diagnostic</b> : {esc(ot.cause)}", styles["Normal"]),
        Paragraph(f"<b>Rapport</b> : {esc(ot.rapport)}", styles["Normal"]),
        Spacer(1, 4 * mm),
    ]
    rows = [["Date", "Statut", "Par", "Commentaire"]]
    for h in ot.historique.select_related("par"):
        rows.append([f"{timezone.localtime(h.le):%d/%m/%Y %H:%M}", f"{h.de or '—'} → {h.vers}", str(h.par or "système"),
                     (h.commentaire or "")[:60]])
    pieces = [[p.article.code, f"{p.quantite:g}", p.depot.code] for p in ot.pieces.select_related("article", "depot")]
    for titre, data, largeurs in (("Historique", rows, [30 * mm, 45 * mm, 45 * mm, 60 * mm]),
                                  ("Pièces sorties du stock", [["Article", "Quantité", "Dépôt"]] + pieces, [80 * mm, 30 * mm, 70 * mm])):
        story.append(Paragraph(f"<b>{titre}</b>", styles["Normal"]))
        table = Table(data, colWidths=largeurs)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#12308f")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))
        story += [table, Spacer(1, 4 * mm)]
    story.append(Paragraph(f"Main-d'œuvre : {ot.heures_mo} h · Archivé le {timezone.localtime(ot.archive_le):%d/%m/%Y %H:%M} "
                           f"par {esc(ot.archive_par)}", styles["Normal"]))
    doc.build(story)
    return buf.getvalue()


def archiver_ot_ged(ot, user=None):
    """Archivage réglementaire via M12 (CDC M8 §13.8) : rapport PDF scellé (SHA-256) en GED, conservation 10 ans,
    lié à l'OT pour la recherche juridique."""
    import hashlib

    from django.core.files.base import ContentFile

    from documents.models import Document, DocumentType, Version
    from juridique.models import LienDocument

    type_doc, _ = DocumentType.objects.get_or_create(
        code=TYPE_GED_RAPPORT_OT, defaults={"label": "Rapports de maintenance", "retention_years": RETENTION_RAPPORT_OT_ANS}
    )
    if (type_doc.retention_years or 0) < RETENTION_RAPPORT_OT_ANS:
        type_doc.retention_years = RETENTION_RAPPORT_OT_ANS
        type_doc.save(update_fields=["retention_years"])
    contenu = rapport_ot_pdf(ot)
    sha = hashlib.sha256(contenu).hexdigest()
    nom = f"{ot.code}.pdf"
    document = Document.objects.create(
        title=f"Rapport d'intervention {ot.code} — {ot.actif.designation}"[:200], status=Document.Status.ARCHIVED,
        archived_at=timezone.now(), type=type_doc, document_date=timezone.localdate(ot.archive_le),
        reference=ot.code, keywords=["maintenance", "OT", ot.code, ot.actif.code], sha256=sha, created_by=user,
    )
    version = Version.objects.create(
        document=document, number=1, file=ContentFile(contenu, name=nom), sha256=sha, size=len(contenu),
        original_filename=nom, created_by=user,
    )
    document.current_version = version
    document.save(update_fields=["current_version"])
    LienDocument.objects.create(
        document=document, objet_type="maintenance.ordretravail", objet_id=str(ot.pk),
        objet_label=f"{ot.code} — {ot.actif.designation}"[:255], module="M8", note="Rapport archivé", created_by=user,
    )
    ot.document = document
    ot.save(update_fields=["document"])
    return document
