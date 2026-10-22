"""Écarts M6-A (CDC M6.1) : paramètres provisoires, couverture des qualifications soudeur, relances CAPA / ITP /
punch list, dossier qualité par OF scellé en GED, indicateurs qualité et rapport mensuel."""

import re
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from users.models import User
from config.i18n import en_francais, tr

PARAMETRES_QUALITE_DEFAUT = {
    "CAPA_DELAI_JOURS": ("CAPA : délai de clôture (jours calendaires)", "5", "jours"),
    "CAPA_ESCALADE_JOURS": ("CAPA : retard avant escalade à la direction", "2", "jours"),
    "QUALIF_ALERTE_JOURS": ("Qualification soudeur : alerte avant péremption", "90", "jours"),
    "METRO_ALERTE_JOURS": ("Métrologie : alerte avant échéance d'étalonnage", "30", "jours"),
    "AGREMENT_SCORE_MIN": ("Audit fournisseur : score minimal d'agrément", "70", "%"),
    "DOC_REVUE_ALERTE_JOURS": ("Document qualité : alerte avant la date de revue", "30", "jours"),
    # Écarts M6 (lot ecarts-m6m7)
    "CND_ORGANISME_REFERENTIEL": ("CND tiers : organisme agréé du référentiel exigé (1 = oui, 0 = non)", "1", "0/1"),
    "WPS_PROFIL_BLOQUANT": ("Soudage : WPS limités aux WPS requis du profil / contrat M1.3 (1 = oui, 0 = non)", "1", "0/1"),
    # Lot a3 : traçabilité M5 → M6 (lot / coulée / certificat 3.1 jusqu'au joint) et coût de non-qualité M6 → M10
    "JOINT_LOT_OBLIGATOIRE": (
        "Joint soudé : 1 = lot matière obligatoire dès que l'OF a consommé un lot (coulée reprise du lot), 0 = facultatif",
        "1", "0/1"),
    "JOINT_LOT_CONSOMME_OF": (
        "Joint soudé : 1 = le lot cité doit être sorti du stock pour cet OF, 0 = tout lot non bloqué", "1", "0/1"),
    "CNQ_TAUX_HORAIRE": ("Coût de non-qualité : taux horaire de valorisation des reprises", "6000", "FCFA/h"),
    "CNQ_COMPTE_CHARGE": ("Coût de non-qualité : compte de charge débité (reclassement)", "624000", "compte"),
    "CNQ_COMPTE_MATIERE": ("Coût de non-qualité : compte crédité pour la matière rebutée et les frais externes",
                           "603200", "compte"),
    "CNQ_COMPTE_MO": ("Coût de non-qualité : compte crédité pour la main-d'œuvre de reprise", "661000", "compte"),
}
#: Destinataires des relances qualité (QA/QC) et de l'escalade d'une CAPA en retard (hiérarchie).
ROLES_QAQC = (User.Role.QAQC,)
ROLES_ESCALADE = (User.Role.DIRECTEUR_OPERATIONS, User.Role.DGA)
TYPE_GED_QUALITE = "documents_qualite_iso"
RETENTION_QUALITE_ANS = 10


def get_param_qualite(code):
    from .models import ParametreQualite

    label, valeur, unite = PARAMETRES_QUALITE_DEFAUT[code]
    obj, _ = ParametreQualite.objects.get_or_create(code=code, defaults={"label": label, "valeur": Decimal(valeur), "unite": unite})
    return obj.valeur


# ----------------------------------------------------------------------------------------------------------------
# Qualification soudeur ↔ WPS (ISO 9606-1 / ASME IX) : procédé identique, position couverte
# ----------------------------------------------------------------------------------------------------------------
#: Positions « toutes positions » (tube) : une qualification 6G / H-L045 couvre toutes les positions.
POSITIONS_TOUTES = {"6G", "H-L045", "6GR", "J-L045"}


def _positions(texte):
    return {p for p in re.split(r"[\s,;/+]+", (texte or "").upper()) if p}


def qualif_couvre(qualif, wps):
    """Vrai si la qualification (valide) autorise le soudage selon ce WPS : même procédé et position couverte."""
    if not qualif.est_valide or qualif.procede != wps.procede:
        return False
    requises, detenues = _positions(wps.position), _positions(qualif.position)
    if not requises or detenues & POSITIONS_TOUTES:
        return True
    return requises <= detenues


def qualification_couvrante(soudeur, wps):
    return next((q for q in soudeur.qualifications.all() if qualif_couvre(q, wps)), None)


# ----------------------------------------------------------------------------------------------------------------
# Relances quotidiennes (tâche `notifier_echeances`) : CAPA en retard + escalade, points ITP et punch list en retard
# ----------------------------------------------------------------------------------------------------------------
def _notifier_une_fois(users, sujet, message):
    from workflow.models import Notification
    from workflow.notifications import notify

    debut = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    n = 0
    for user in {u.pk: u for u in users if u is not None}.values():
        if Notification.objects.filter(user=user, subject=sujet[:255], created_at__gte=debut).exists():
            continue
        notify(user, sujet[:255], message, kind="reminder")
        n += 1
    return n


def relances_qualite(jour=None):
    from .models import ActionCorrective, PointInspection, PunchItem

    jour = jour or timezone.localdate()
    qaqc = list(User.objects.filter(is_active=True, role__in=ROLES_QAQC))
    hierarchie = list(User.objects.filter(is_active=True, role__in=ROLES_ESCALADE))
    seuil = int(get_param_qualite("CAPA_ESCALADE_JOURS"))
    envoyees = 0
    for capa in ActionCorrective.objects.exclude(statut=ActionCorrective.Statut.CLOTUREE).filter(
        echeance__lt=jour
    ).select_related("non_conformite", "responsable"):
        retard = (jour - capa.echeance).days
        envoyees += _notifier_une_fois(
            qaqc + [capa.responsable], f"CAPA {capa.code} en retard de {retard} j",
            f"L'action {capa.code} (NC {capa.non_conformite.code}) devait être clôturée le {capa.echeance:%d/%m/%Y}.",
        )
        if retard >= seuil and capa.escaladee_le is None:
            envoyees += _notifier_une_fois(
                hierarchie, f"Escalade : CAPA {capa.code} en retard de {retard} j",
                f"L'action corrective {capa.code} (NC {capa.non_conformite.code}) n'est pas clôturée {retard} jours "
                f"après son échéance du {capa.echeance:%d/%m/%Y}. Arbitrage de la direction demandé.",
            )
            capa.escaladee_le = timezone.now()
            capa.save(update_fields=["escaladee_le", "updated_at"])
    for point in PointInspection.objects.filter(statut=PointInspection.Statut.EN_ATTENTE, date_prevue__lt=jour).select_related("controle"):
        envoyees += _notifier_une_fois(
            qaqc, f"ITP {point.controle.code} : point {point.ordre} en retard",
            f"Le point « {point.description} » était prévu le {point.date_prevue:%d/%m/%Y} et n'est pas levé.",
        )
    for item in PunchItem.objects.filter(statut=PunchItem.Statut.OUVERTE, echeance__lt=jour).select_related("ordre"):
        envoyees += _notifier_une_fois(
            qaqc, f"Punch list {item.code} en retard ({item.ordre.code})",
            f"Réserve {item.get_categorie_display()} « {item.description} » à lever avant le {item.echeance:%d/%m/%Y}.",
        )
    return envoyees


def alertes_qualifications_soudeurs(band):
    """Qualifications soudeur à renouveler (horizon paramétrable) : dernière qualification de chaque (soudeur, norme,
    procédé), pour alimenter les alertes J-90 / J-30 / J-15 / J-0 transverses."""
    from .models import QualificationSoudeur

    aujourdhui = timezone.localdate()
    horizon = aujourdhui + timedelta(days=int(get_param_qualite("QUALIF_ALERTE_JOURS")))
    vues, items = set(), []
    for q in QualificationSoudeur.objects.exclude(statut=QualificationSoudeur.Statut.SUSPENDUE).select_related(
        "soudeur"
    ).filter(soudeur__is_active=True).order_by("soudeur_id", "norme", "procede", "-date_validite"):
        cle = (q.soudeur_id, q.norme, q.procede)
        if cle in vues:
            continue
        vues.add(cle)
        if q.date_validite > horizon:
            continue
        jours = (q.date_validite - aujourdhui).days
        items.append({
            "type": "qualification_soudeur", "code": q.code,
            "libelle": f"{q.soudeur.display_name} — {q.get_norme_display()} {q.get_procede_display()} {q.position}".strip(),
            "date_echeance": q.date_validite, "bande": band(jours), "jours": jours,
            "statut": "expiree" if jours < 0 else "active",
        })
    return items


# ----------------------------------------------------------------------------------------------------------------
# Dossier qualité de l'OF (MANUEL 5.8, CDC M6.1-14) : PDF scellé en GED 10 ans à la levée de réserve du PV
# ----------------------------------------------------------------------------------------------------------------
def _d(valeur):
    return f"{valeur:%d/%m/%Y}" if valeur else "—"


def dossier_qualite_pdf(pv):
    from hse.services import _pdf

    from .models import ControleQualite, EpreuvePression, JointSoude, NonConformite, PunchItem

    of = pv.ordre
    blocs = [
        ("PV", f"{pv.code} — {pv.intitule}"), (tr("Affaire"), pv.affaire.code if pv.affaire_id else (of.affaire.code if of and of.affaire_id else "—")),
        (tr("Ordre de fabrication"), f"{of.code} — {of.label}" if of else "—"), (tr("Date du PV"), _d(pv.date_pv)),
        (tr("Statut"), pv.get_statut_display()), (tr("Levée de réserve"), _d(pv.levee_reserve)),
        (tr("Validé par"), pv.validated_by.get_full_name() if pv.validated_by_id else "—"),
        (tr("Conservation"), tr("%(ans)s ans (Oil & Gas)") % {"ans": pv.retention_years}),
    ]
    tableau = [[tr("Rubrique"), tr("Référence"), tr("Détail"), tr("Date"), tr("Résultat / statut")]]
    if of:
        for j in JointSoude.objects.filter(ordre=of).select_related("soudeur", "wps"):
            tableau.append([tr("Joint"), f"{j.code} / {j.repere}", tr("%(soudeur_display_name)s · WPS %(valeur)s · coulée %(valeur2)s") % {"soudeur_display_name": j.soudeur.display_name, "valeur": j.wps.code if j.wps_id else '—', "valeur2": j.numero_coulee or '—'},
                            _d(j.date_soudage), "—"])
        controles = ControleQualite.objects.filter(ordre=of).exclude(statut=ControleQualite.Statut.ANNULE)
        for c in controles:
            detail = c.point_controle or c.get_type_controle_display()
            if c.methode_cnd:
                detail = f"{c.methode_cnd} · {detail}"
            tableau.append([c.get_type_controle_display()[:30], c.code, detail[:80], _d(c.date_controle),
                            f"{c.get_resultat_display()} ({c.get_statut_display()})"])
            for p in c.points.all():
                tableau.append([tr("  Point ITP"), f"#{p.ordre}", p.description[:80], _d(p.leve_le), p.get_statut_display()])
        for e in EpreuvePression.objects.filter(ordre=of):
            tableau.append([tr("Épreuve"), e.code, f"{e.get_type_epreuve_display()} {e.pression_essai} bar / {e.duree_minutes} min",
                            _d(e.conclu_le), e.get_resultat_display() if e.resultat else e.get_statut_display()])
        for nc in NonConformite.objects.filter(controle__ordre=of).prefetch_related("actions_correctives"):
            tableau.append(["NC", nc.code, nc.description[:80], _d(nc.date_decision), nc.get_statut_display()])
            for a in nc.actions_correctives.all():
                tableau.append(["  CAPA", a.code, a.description[:80], _d(a.closed_at), a.get_statut_display()])
        for item in PunchItem.objects.filter(ordre=of):
            tableau.append([tr("Punch list"), item.code, f"{item.categorie} · {item.description}"[:80], _d(item.leve_le), item.get_statut_display()])
    for c in pv.controles.all():
        if not of or c.ordre_id != of.pk:
            tableau.append([c.get_type_controle_display()[:30], c.code, (c.point_controle or "")[:80], _d(c.date_controle), c.get_resultat_display()])
    return _pdf(tr("Dossier qualité %(valeur)s") % {"valeur": of.code if of else pv.code}, blocs, tableau if len(tableau) > 1 else None)


def archiver_dossier_qualite(pv, user=None):
    """Scelle le dossier qualité (SHA-256) en GED, type « Documents qualité / ISO » porté à 10 ans, lié au PV."""
    from hse.services import archiver_ged

    titre = f"Dossier qualité {pv.ordre.code if pv.ordre_id else pv.code} ({pv.code})"
    return archiver_ged(
        en_francais(dossier_qualite_pdf, pv), f"dossier-qualite-{pv.code}.pdf", titre, TYPE_GED_QUALITE, "Documents qualité / ISO",
        pv.code, "qualite.pvcontrole", pv.pk, user=user, mots=("dossier qualité", "PV de contrôle"), module="M6",
        note="Dossier qualité scellé à la levée de réserve (10 ans Oil & Gas)", retention=RETENTION_QUALITE_ANS,
    )


# ----------------------------------------------------------------------------------------------------------------
# Indicateurs qualité (CDC M6.1-15) et rapport mensuel
# ----------------------------------------------------------------------------------------------------------------
def _taux(n, d):
    return round(Decimal(n) * 100 / Decimal(d), 1) if d else None


def indicateurs(annee, mois=None):
    from django.db.models import Q

    from .models import ActionCorrective, ControleQualite, JointSoude, NonConformite, PvControle

    def periode(champ):
        f = Q(**{f"{champ}__year": annee})
        return f & Q(**{f"{champ}__month": mois}) if mois else f

    controles = ControleQualite.objects.filter(periode("date_controle")).exclude(statut=ControleQualite.Statut.ANNULE)
    valides = controles.filter(statut=ControleQualite.Statut.VALIDE)
    conformes = valides.filter(resultat=ControleQualite.Resultat.CONFORME).count()
    ncs = NonConformite.objects.filter(periode("created_at")).exclude(type_ncr="hse")
    rebuts = ncs.filter(traitement=NonConformite.Traitement.REJET).count()
    joints = JointSoude.objects.filter(periode("date_soudage")).count()
    ncr_sd = ncs.filter(type_ncr="soudage").count()
    pvs = PvControle.objects.filter(periode("levee_reserve"), statut=PvControle.Statut.RECEPTIONNE)
    delais = [(pv.levee_reserve - pv.date_pv).days for pv in pvs if pv.levee_reserve and pv.date_pv]
    capas = ActionCorrective.objects.filter(periode("closed_at"), statut=ActionCorrective.Statut.CLOTUREE)
    capa_a_temps = sum(1 for a in capas if not a.echeance or timezone.localtime(a.closed_at).date() <= a.echeance)
    return {
        "annee": annee, "mois": mois,
        "controles": controles.count(), "controles_valides": valides.count(), "controles_conformes": conformes,
        "taux_conformite": _taux(conformes, valides.count()),
        "non_conformites": ncs.count(), "nc_critiques": ncs.filter(gravite=NonConformite.Gravite.CRITIQUE).count(),
        "taux_nc": _taux(ncs.count(), controles.count()),
        "rebuts": rebuts, "taux_rebut": _taux(rebuts, controles.count()),
        "joints_soudes": joints, "ncr_soudage": ncr_sd, "densite_defauts": _taux(ncr_sd, joints),
        "pv_receptionnes": len(delais),
        "delai_levee_reserves_jours": round(sum(delais) / len(delais), 1) if delais else None,
        "capa_cloturees": capas.count(), "capa_dans_les_delais": _taux(capa_a_temps, capas.count()),
        "capa_en_retard": ActionCorrective.objects.exclude(statut=ActionCorrective.Statut.CLOTUREE)
        .filter(echeance__lt=timezone.localdate()).count(),
    }


LIBELLES_INDICATEURS = (
    ("controles", "Contrôles réalisés", ""), ("taux_conformite", "Taux de conformité", "%"),
    ("non_conformites", "Non-conformités", ""), ("taux_nc", "Taux de NC (NC / contrôles)", "%"),
    ("taux_rebut", "Taux de rebut (NC rejetées / contrôles)", "%"), ("joints_soudes", "Joints soudés", ""),
    ("densite_defauts", "Densité de défauts (NCR-SD / 100 joints)", ""),
    ("delai_levee_reserves_jours", "Délai moyen de levée des réserves", "j"),
    ("capa_dans_les_delais", "CAPA clôturées dans les délais", "%"), ("capa_en_retard", "CAPA en retard (à date)", ""),
)


def rapport_indicateurs_pdf(data):
    from hse.services import _pdf

    periode = f"{data['mois']:02d}/{data['annee']}" if data["mois"] else str(data["annee"])
    tableau = [[tr("Indicateur"), tr("Valeur")]] + [
        [libelle, "—" if data[cle] is None else f"{data[cle]}{(' ' + unite) if unite else ''}"]
        for cle, libelle, unite in LIBELLES_INDICATEURS
    ]
    return _pdf(tr("Rapport qualité %(valeur)s — %(periode)s") % {"valeur": 'mensuel' if data['mois'] else 'annuel', "periode": periode},
                [(tr("Période"), periode), (tr("Édité le"), f"{timezone.localdate():%d/%m/%Y}")], tableau)


# ----------------------------------------------------------------------------------------------------------------
# Écarts M6-B : contrôles mesurés (peinture, génie civil, électricité, essais), métrologie typée
# ----------------------------------------------------------------------------------------------------------------
#: Critères livrés par défaut (valeurs usuelles provisoires, à remplacer par les fiches de contrôle ETSL).
CRITERES_DEFAUT = (
    ("peinture", "DFT", "Épaisseur de film sec (DFT)", "µm", "200", None, "ISO 19840"),
    ("peinture", "ADHERENCE", "Adhérence (pull-off)", "MPa", "5", None, "ISO 4624"),
    ("peinture", "RUGOSITE", "Rugosité de surface (profil)", "µm", "50", "100", "ISO 8503"),
    ("peinture", "HR", "Humidité relative à l'application", "%", None, "85", "ISO 8502-4"),
    ("peinture", "ECART_ROSEE", "Écart support / point de rosée", "°C", "3", None, "ISO 8502-4"),
    ("genie_civil", "FC28", "Résistance à la compression à 28 j", "MPa", "25", None, "EN 12390-3"),
    ("genie_civil", "SLUMP", "Affaissement (cône d'Abrams)", "mm", "50", "150", "EN 12350-2"),
    ("genie_civil", "ENROBAGE", "Enrobage des armatures", "mm", "30", None, "Eurocode 2"),
    ("genie_civil", "PLANEITE", "Planéité (règle de 2 m)", "mm", None, "5", ""),
    ("electrique", "ISOLEMENT", "Résistance d'isolement", "MΩ", "1", None, "IEC 60364-6"),
    ("electrique", "CONTINUITE", "Continuité du conducteur de protection", "Ω", None, "1", "IEC 60364-6"),
    ("electrique", "TERRE", "Résistance de prise de terre", "Ω", None, "10", "IEC 60364-6"),
    ("electrique", "BOUCLE_4_20", "Erreur de boucle 4-20 mA", "%", None, "0.5", "IEC 61298"),
    ("essai", "ECART_CONSIGNE", "Écart à la consigne", "%", None, "2", ""),
    ("essai", "DUREE", "Durée de fonctionnement sans défaut", "min", "60", None, ""),
    ("tth", "TEMP_PALIER", "Température de palier", "°C", "580", "620", "ASME B31.3"),
    ("tth", "DUREE_PALIER", "Durée de palier", "min", "60", None, "ASME B31.3"),
)
#: Type d'équipement dont l'usage est contrôlé par type de contrôle (blocage d'usage).
EQUIPEMENT_PAR_CONTROLE = {"tth": "four_tth"}


def criteres_defaut():
    from .models import CritereControle

    for type_controle, code, libelle, unite, mini, maxi, norme in CRITERES_DEFAUT:
        CritereControle.objects.get_or_create(type_controle=type_controle, code=code, defaults={
            "libelle": libelle, "unite": unite, "mini": Decimal(mini) if mini else None,
            "maxi": Decimal(maxi) if maxi else None, "norme": norme,
        })


def conclure_mesures(controle, user):
    """Résultat calculé : conforme si toutes les mesures le sont ; sinon non conforme et NC ouverte automatiquement."""
    from .models import ControleQualite, NonConformite

    mesures = list(controle.mesures.select_related("critere"))
    hors = [m for m in mesures if not m.conforme]
    controle.resultat = ControleQualite.Resultat.NON_CONFORME if hors else ControleQualite.Resultat.CONFORME
    controle.statut = ControleQualite.Statut.VALIDE
    controle.save(update_fields=["resultat", "statut", "updated_at"])
    nc = None
    if hors:
        detail = " ; ".join(f"{m.critere.libelle} = {m.valeur} {m.critere.unite} (hors [{m.mini if m.mini is not None else '—'} ; "
                            f"{m.maxi if m.maxi is not None else '—'}])" for m in hors)
        nc = NonConformite.objects.create(
            controle=controle, source=NonConformite.Source.CONTROLE, gravite=NonConformite.Gravite.MAJEURE,
            description=f"{controle.get_type_controle_display()} {controle.code} non conforme : {detail}"[:2000],
            decided_by=user,
        )
    return nc


def nc_metrologie(instrument, user=None):
    """Équipement hors tolérance : NC ouverte listant les contrôles et joints réalisés avec lui depuis le dernier
    étalonnage conforme (analyse d'impact à mener par QA/QC)."""
    from .models import NonConformite

    depuis = instrument.date_etalonnage
    controles = list(instrument.controles.filter(date_controle__gte=depuis).values_list("code", flat=True))
    joints = list(instrument.joints.filter(date_soudage__gte=depuis).values_list("code", flat=True))
    epreuves = list(instrument.epreuves.filter(created_at__date__gte=depuis).values_list("code", flat=True))
    impact = ", ".join(controles + joints + epreuves) or "aucun usage enregistré"
    return NonConformite.objects.create(
        source=NonConformite.Source.INTERNE, gravite=NonConformite.Gravite.MAJEURE, instrument=instrument,
        description=(f"{instrument.get_type_equipement_display()} {instrument.code} ({instrument.designation}) hors tolérance. "
                     f"Usages depuis le {depuis:%d/%m/%Y} à réévaluer : {impact}.")[:2000],
        decided_by=user,
    )


def alertes_metrologie(band):
    from .models import InstrumentMesure

    aujourdhui = timezone.localdate()
    horizon = aujourdhui + timedelta(days=int(get_param_qualite("METRO_ALERTE_JOURS")))
    items = []
    for inst in InstrumentMesure.objects.filter(statut=InstrumentMesure.Statut.ACTIF, echeance_etalonnage__lte=horizon):
        jours = (inst.echeance_etalonnage - aujourdhui).days
        items.append({
            "type": "etalonnage", "code": inst.code,
            "libelle": f"{inst.get_type_equipement_display()} — {inst.designation} ({inst.numero_serie})",
            "date_echeance": inst.echeance_etalonnage, "bande": band(jours), "jours": jours,
            "statut": "expiree" if jours < 0 else "active",
        })
    return items


def etiquette_pdf(instrument):
    """Étiquette de statut métrologique (vert : utilisable ; rouge : interdit d'usage), format 70 x 40 mm."""
    import io

    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    largeur, hauteur = 70 * mm, 40 * mm
    c = canvas.Canvas(buf, pagesize=(largeur, hauteur))
    ok = instrument.utilisable
    c.setFillColor(colors.HexColor("#15803d" if ok else "#b91c1c"))
    c.rect(0, hauteur - 12 * mm, largeur, 12 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(largeur / 2, hauteur - 8 * mm, tr("CONFORME - UTILISABLE") if ok else tr("INTERDIT D'USAGE"))
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(3 * mm, hauteur - 18 * mm, f"{instrument.code} - {instrument.numero_serie}"[:45])
    c.setFont("Helvetica", 8)
    c.drawString(3 * mm, hauteur - 23 * mm, instrument.designation[:48])
    dernier = instrument.etalonnages.first()
    operation = dict(instrument.etalonnages.model._meta.get_field("type_operation").choices).get(instrument.operation_attendue)
    c.drawString(3 * mm, hauteur - 28 * mm, f"{operation} : {instrument.date_etalonnage:%d/%m/%Y}")
    c.drawString(3 * mm, hauteur - 33 * mm, tr("Prochaine échéance : %(instrument_echeance_etalonnage)s") % {"instrument_echeance_etalonnage": format(instrument.echeance_etalonnage, '%d/%m/%Y')})
    if dernier and dernier.certificat:
        c.drawString(3 * mm, hauteur - 38 * mm, (tr("Certificat : %(dernier_certificat)s") % {"dernier_certificat": dernier.certificat})[:48])
    c.showPage()
    c.save()
    return buf.getvalue()


# ----------------------------------------------------------------------------------------------------------------
# Écarts M6 (lot ecarts-m6m7) : organisme agréé (M6.1-09), WPS requis par profil contractuel (M1.3)
# ----------------------------------------------------------------------------------------------------------------
def controle_organisme(organisme, organisme_agree, methode, jour=None):
    """Message d'erreur si un contrôle confié à un organisme agréé ne cite pas un organisme valide, sinon None."""
    if organisme != "agrege" or not int(get_param_qualite("CND_ORGANISME_REFERENTIEL")):
        return None
    if organisme_agree is None:
        return "Organisme agréé du référentiel obligatoire (Qualité › Organismes agréés)."
    if not organisme_agree.est_valide(jour):
        return f"Agrément de {organisme_agree.nom} expiré ou inactif (valable jusqu'au {organisme_agree.date_fin_validite:%d/%m/%Y})."
    if not organisme_agree.couvre(methode):
        return f"{organisme_agree.nom} n'est pas agréé pour la méthode {methode}."
    return None


def wps_requis_affaire(affaire):
    """WPS exigés pour une affaire : exigences propres à ses contrats, sinon celles de leurs profils (M1.3)."""
    from .models import WpsRequis

    if affaire is None:
        return []
    contrats = list(affaire.contracts.all())
    if not contrats:
        return []
    propres = list(WpsRequis.objects.filter(contract__in=contrats).select_related("wps"))
    if propres:
        return propres
    profils = {c.profile for c in contrats if c.profile}
    return list(WpsRequis.objects.filter(contract__isnull=True, profile__in=profils).select_related("wps"))


def controle_wps_profil(wps, affaire):
    """Message d'erreur si le WPS n'est pas requis par le profil / contrat de l'affaire (paramètre), sinon None."""
    if wps is None or affaire is None or not int(get_param_qualite("WPS_PROFIL_BLOQUANT")):
        return None
    requis = wps_requis_affaire(affaire)
    if requis and wps.pk not in {r.wps_id for r in requis}:
        codes = ", ".join(sorted({r.wps.code for r in requis}))
        return f"WPS {wps.code} non prévu par le profil contractuel de l'affaire {affaire.code} (WPS requis : {codes})."
    return None


def conformite_wps_affaire(affaire):
    """Couverture des WPS requis : chaque WPS exigé doit être validé (non obsolète)."""
    lignes = []
    for r in wps_requis_affaire(affaire):
        lignes.append({
            "wps": str(r.wps_id), "wps_code": r.wps.code, "procede": r.wps.procede, "statut": r.wps.statut,
            "valide": r.wps.statut == "valide", "origine": r.contract.code if r.contract_id else r.profile,
            "libelle": r.libelle,
        })
    return {"affaire": str(affaire.pk), "affaire_code": affaire.code, "requis": lignes,
            "conforme": all(ligne["valide"] for ligne in lignes)}
