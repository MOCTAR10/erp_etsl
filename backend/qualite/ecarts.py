"""Écarts M6-A (CDC M6.1) : paramètres provisoires, couverture des qualifications soudeur, relances CAPA / ITP /
punch list, dossier qualité par OF scellé en GED, indicateurs qualité et rapport mensuel."""

import re
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from users.models import User

PARAMETRES_QUALITE_DEFAUT = {
    "CAPA_DELAI_JOURS": ("CAPA : délai de clôture (jours calendaires)", "5", "jours"),
    "CAPA_ESCALADE_JOURS": ("CAPA : retard avant escalade à la direction", "2", "jours"),
    "QUALIF_ALERTE_JOURS": ("Qualification soudeur : alerte avant péremption", "90", "jours"),
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
        ("PV", f"{pv.code} — {pv.intitule}"), ("Affaire", pv.affaire.code if pv.affaire_id else (of.affaire.code if of and of.affaire_id else "—")),
        ("Ordre de fabrication", f"{of.code} — {of.label}" if of else "—"), ("Date du PV", _d(pv.date_pv)),
        ("Statut", pv.get_statut_display()), ("Levée de réserve", _d(pv.levee_reserve)),
        ("Validé par", pv.validated_by.get_full_name() if pv.validated_by_id else "—"),
        ("Conservation", f"{pv.retention_years} ans (Oil & Gas)"),
    ]
    tableau = [["Rubrique", "Référence", "Détail", "Date", "Résultat / statut"]]
    if of:
        for j in JointSoude.objects.filter(ordre=of).select_related("soudeur", "wps"):
            tableau.append(["Joint", f"{j.code} / {j.repere}", f"{j.soudeur.display_name} · WPS {j.wps.code if j.wps_id else '—'} · coulée {j.numero_coulee or '—'}",
                            _d(j.date_soudage), "—"])
        controles = ControleQualite.objects.filter(ordre=of).exclude(statut=ControleQualite.Statut.ANNULE)
        for c in controles:
            detail = c.point_controle or c.get_type_controle_display()
            if c.methode_cnd:
                detail = f"{c.methode_cnd} · {detail}"
            tableau.append([c.get_type_controle_display()[:30], c.code, detail[:80], _d(c.date_controle),
                            f"{c.get_resultat_display()} ({c.get_statut_display()})"])
            for p in c.points.all():
                tableau.append(["  Point ITP", f"#{p.ordre}", p.description[:80], _d(p.leve_le), p.get_statut_display()])
        for e in EpreuvePression.objects.filter(ordre=of):
            tableau.append(["Épreuve", e.code, f"{e.get_type_epreuve_display()} {e.pression_essai} bar / {e.duree_minutes} min",
                            _d(e.conclu_le), e.get_resultat_display() if e.resultat else e.get_statut_display()])
        for nc in NonConformite.objects.filter(controle__ordre=of).prefetch_related("actions_correctives"):
            tableau.append(["NC", nc.code, nc.description[:80], _d(nc.date_decision), nc.get_statut_display()])
            for a in nc.actions_correctives.all():
                tableau.append(["  CAPA", a.code, a.description[:80], _d(a.closed_at), a.get_statut_display()])
        for item in PunchItem.objects.filter(ordre=of):
            tableau.append(["Punch list", item.code, f"{item.categorie} · {item.description}"[:80], _d(item.leve_le), item.get_statut_display()])
    for c in pv.controles.all():
        if not of or c.ordre_id != of.pk:
            tableau.append([c.get_type_controle_display()[:30], c.code, (c.point_controle or "")[:80], _d(c.date_controle), c.get_resultat_display()])
    return _pdf(f"Dossier qualité {of.code if of else pv.code}", blocs, tableau if len(tableau) > 1 else None)


def archiver_dossier_qualite(pv, user=None):
    """Scelle le dossier qualité (SHA-256) en GED, type « Documents qualité / ISO » porté à 10 ans, lié au PV."""
    from hse.services import archiver_ged

    titre = f"Dossier qualité {pv.ordre.code if pv.ordre_id else pv.code} ({pv.code})"
    return archiver_ged(
        dossier_qualite_pdf(pv), f"dossier-qualite-{pv.code}.pdf", titre, TYPE_GED_QUALITE, "Documents qualité / ISO",
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
    tableau = [["Indicateur", "Valeur"]] + [
        [libelle, "—" if data[cle] is None else f"{data[cle]}{(' ' + unite) if unite else ''}"]
        for cle, libelle, unite in LIBELLES_INDICATEURS
    ]
    return _pdf(f"Rapport qualité {'mensuel' if data['mois'] else 'annuel'} — {periode}",
                [("Période", periode), ("Édité le", f"{timezone.localdate():%d/%m/%Y}")], tableau)
