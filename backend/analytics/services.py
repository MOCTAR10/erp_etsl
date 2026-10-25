"""Couche D — agrégations BI (RF-ERP-C0...C3).

Couche d'agrégation pure sur les tables des 12 modules (aucune écriture).
Réplica : les datamarts dbt consomment le réplica lecteur (C0) ; la couche
services ci-dessous calcule les agrégats en direct pour le tableau de bord
Direction (C1), le reporting client pétrolier ASMR/HSE/Qualité (C2) et les
alertes J-90/J-60/J-30 transverses (C3).

Montants : pattern RF-59 — masqués (None) hors rôles autorisés
(`can_see_amount` du noyau documents).
"""

from django.utils import timezone

from config.echeances import BANDES as BAND_ORDER
from config.echeances import bande as _band





def _zero():
    return {band: 0 for band in BAND_ORDER}


def dashboard_direction(user):
    """Tableau de bord Direction (C1) — KPIs consolidés des 12 modules."""
    from django.db.models import Count, Sum
    from documents.models import Dossier, Document
    from workflow.models import Circuit, Task
    from referentiels.models import Partner, Article, Annexe
    from registres.models import Registre, RegistreEntry

    see_amount = _can_see_amount(user)

    from commercial.models import Affaire, Opportunity
    from achats.models import (
        PurchaseOrder,
        PurchaseRequest,
        ConsultationRequest,
        GoodsReceipt,
        PurchaseInvoice,
    )
    from operations.models import OrdreFabrication
    from logistique.models import EquipementParc, LocationGR
    from stocks.models import StockQuant, LotMatiere, MouvementStock, Depot
    from qualite.models import NonConformite, Soudeur, WpsWpqr, PvControle
    from hse.models import Incident, PermisTravail, ActionHse, EvaluationRisque
    from maintenance.models import Actif, OrdreTravail, Inspection
    from rh_paie.models import Employe, BulletinPaie, DemandesConge
    from comptabilite.models import Engagement, Paiement, DeclarationTva
    from controle_gestion.models import Budget, BudgetRevision, ClotureGestion
    from juridique.models import Courrier, Convention, Contentieux, Caution, Assurance

    today = timezone.localdate()

    def _commercial():
        from commercial.services import pipeline_stats
        stats = pipeline_stats()
        won = stats.get("won_total") if see_amount else None
        result = {
            "opportunites_ouvertes": Opportunity.objects.filter(is_active=True)
            .exclude(stage="perdu")
            .count(),
            "pipeline_stages": len(stats.get("by_stage", {})),
            "taux_conversion": stats.get("conversion_rate"),
            "ca_gagne": won,
            "affaires_actives": Affaire.objects.exclude(status="cloturee").count(),
            # Pipe pondéré 90/60/25 publié vers M11 / Couche D (clôture M1, CDC §3.11).
            "pipe_pondere": stats["pipe_pondere"]["total"] if see_amount else None,
        }
        # Reporting commercial Couche D (M1) : prix moyen, transformation, scoring clients (montants masqués RF-59).
        from commercial.ecarts_m1 import indicateurs_commerciaux

        result["indicateurs"] = indicateurs_commerciaux(see_amount)
        if not see_amount:
            result["ca_gagne"] = None
        return result

    def _achats():
        from achats.models import PurchaseOrderLine

        qs = PurchaseOrder.objects.exclude(status=PurchaseOrder.Status.ANNULEE)
        if see_amount:
            ids = list(qs.values_list("id", flat=True))
            total = PurchaseOrderLine.objects.filter(
                purchase_order_id__in=ids
            ).aggregate(t=Sum("price_total"))["t"]
        else:
            total = None
        return {
            "da": PurchaseRequest.objects.count(),
            "consultations": ConsultationRequest.objects.count(),
            "bc": qs.count(),
            "bc_en_cours": qs.exclude(
                status__in=[PurchaseOrder.Status.CLOTUREE, PurchaseOrder.Status.ANNULEE]
            ).count(),
            "bl": GoodsReceipt.objects.count(),
            "rc": PurchaseInvoice.objects.count(),
            "montant_bc": float(total) if total is not None else None,
        }

    def _logistique():
        parc = EquipementParc.Statut
        return {
            "equipements": EquipementParc.objects.count(),
            "disponibles": EquipementParc.objects.filter(statut=parc.DISPONIBLE).count(),
            "affectes": EquipementParc.objects.filter(statut=parc.AFFECTE).count(),
            "locations": LocationGR.objects.exclude(statut=LocationGR.Statut.ANNULEE).count(),
            "locations_actives": LocationGR.objects.filter(statut=LocationGR.Statut.ACTIVE).count(),
        }

    def _stocks():
        quants = StockQuant.objects.aggregate(valeur=Sum("stock_value"))
        return {
            "depots": Depot.objects.count(),
            "articles": Article.objects.count(),
            "lots": LotMatiere.objects.count(),
            "mouvements": MouvementStock.objects.count(),
            "lots_non_dispo": LotMatiere.objects.exclude(statut=LotMatiere.Statut.DISPONIBLE).count(),
            "valorisation": float(quants["valeur"] or 0) if see_amount else None,
        }

    def _qualite():
        return {
            "nc_ouvertes": NonConformite.objects.exclude(statut=NonConformite.Statut.CLOTUREE).count(),
            "soudeurs": Soudeur.objects.count(),
            "wps_valides": WpsWpqr.objects.filter(statut=WpsWpqr.Statut.VALIDE).count(),
            "pv_sous_reserve": PvControle.objects.filter(statut=PvControle.Statut.RESERVE).count(),
        }

    def _hse():
        return {
            "jours_sans_accident": _jours_sans_accident(),
            "incidents_ouverts": Incident.objects.exclude(statut=Incident.Statut.CLOTURE).count(),
            "permis_actifs": PermisTravail.objects.filter(statut=PermisTravail.Statut.ACTIF).count(),
            "actions_ouvertes": ActionHse.objects.exclude(statut=ActionHse.Statut.CLOTUREE).count(),
            "risques_critiques": sum(
                1 for r in EvaluationRisque.objects.exclude(statut=EvaluationRisque.Statut.CLOTUREE)
                if r.criticite == r.Criticite.CRITIQUE
            ),
        }

    def _maintenance():
        return {
            "actifs": Actif.objects.count(),
            "en_panne": Actif.objects.filter(statut=Actif.Statut.EN_PANNE).count(),
            "en_maintenance": Actif.objects.filter(statut=Actif.Statut.EN_MAINTENANCE).count(),
            "ot_ouverts": OrdreTravail.objects.exclude(
                statut__in=OrdreTravail.STATUTS_CLOS
            ).count(),
            "inspections_prevues": Inspection.objects.exclude(
                statut__in=[Inspection.Statut.REALISEE]
            ).count(),
            "en_arret": Actif.objects.filter(
                statut__in=[Actif.Statut.EN_MAINTENANCE, Actif.Statut.EN_PANNE]
            ).count(),
        }

    def _rh():
        return {
            "effectif": Employe.objects.filter(statut=Employe.Statut.ACTIF).count(),
            "en_conge": Employe.objects.filter(statut=Employe.Statut.CONGE).count(),
            "conges_en_attente": DemandesConge.objects.filter(
                statut__in=[DemandesConge.Statut.DEMANDE, DemandesConge.Statut.APPROUVE]
            ).count(),
            "bulletins_mois": BulletinPaie.objects.filter(
                periode__gte=f"{today:%Y-%m}-01",
                statut__in=[BulletinPaie.Statut.VALIDE, BulletinPaie.Statut.CLOTURE],
            ).count(),
        }

    def _comptabilite():
        return {
            "engagements_a_visa": Engagement.objects.filter(
                statut__in=[Engagement.Statut.BROUILLON, Engagement.Statut.SOUMIS]
            ).count(),
            "engagements_approuves": Engagement.objects.filter(statut=Engagement.Statut.APPROUVE).count(),
            "paiements_mois": Paiement.objects.filter(date__year=today.year,
                                                       date__month=today.month).count(),
            "declarations_tva": DeclarationTva.objects.count(),
        }

    def _controle_gestion():
        from accounting_kernel.models import FiscalYear
        fy = FiscalYear.objects.order_by("-year").first()
        return {
            "budgets": Budget.objects.count(),
            "budgets_approuves": Budget.objects.filter(statut="approuve").count(),
            "revisions": BudgetRevision.objects.count(),
            "clotures_realisees": ClotureGestion.objects.filter(statut="realisee").count(),
            "conformite_j4": _compute_conformite_j4(fy.pk if fy else None),
        }

    def _juridique():
        return {
            "courriers": Courrier.objects.count(),
            "courriers_a_classer": Courrier.objects.filter(statut__in=["recu", "enregistre"]).count(),
            "conventions": Convention.objects.filter(
                statut__in=[Convention.Statut.SIGNE, Convention.Statut.EN_SIGNATURE]
            ).count(),
            "contentieux_ouverts": Contentieux.objects.filter(
                statut__in=[Contentieux.Statut.OUVERT, Contentieux.Statut.EN_INSTRUCTION]
            ).count(),
            "cautions_en_cours": Caution.objects.filter(statut=Caution.Statut.EN_COURS).count(),
            "assurances": Assurance.objects.filter(
                statut__in=[Assurance.Statut.ACTIVE, Assurance.Statut.A_RENOUVELER]
            ).count(),
        }

    return {
        "documents": {
            "total": Document.objects.count(),
            "dossiers": Dossier.objects.count(),
            "par_statut": list(Document.objects.values("status").annotate(count=Count("id"))),
        },
        "workflow": {
            "circuits": Circuit.objects.count(),
            "taches_pending": Task.objects.filter(status=Task.Status.PENDING).count(),
            "taches_done": Task.objects.filter(status=Task.Status.DONE).count(),
            "taches_en_retard": Task.objects.filter(
                status=Task.Status.PENDING, due_date__lt=timezone.now()
            ).count(),
        },
        "referentiels": {
            "partners": Partner.objects.count(),
            "articles": Article.objects.count(),
            "annexes": Annexe.objects.count(),
        },
        "registres": {
            "registres": Registre.objects.count(),
            "entrees": RegistreEntry.objects.count(),
        },
        "commercial": _commercial(),
        "achats": _achats(),
        "operations": {
            "of_en_cours": OrdreFabrication.objects.exclude(status="annule").exclude(
                status__in=["termine", "cloture"]
            ).count(),
        },
        "logistique": _logistique(),
        "stocks": _stocks(),
        "qualite": _qualite(),
        "hse": _hse(),
        "maintenance": _maintenance(),
        "rh_paie": _rh(),
        "comptabilite": _comptabilite(),
        "controle_gestion": _controle_gestion(),
        "juridique": _juridique(),
    }


def _jours_sans_accident():
    from hse.models import Incident

    last = (
        Incident.objects.filter(
            type_incident__in=[Incident.TypeIncident.ACCIDENT, Incident.TypeIncident.BLESSURE],
            date_evenement__lte=timezone.now(),
        ).order_by("-date_evenement").first()
    )
    if not last:
        return None
    return max((timezone.now() - last.date_evenement).days, 0)


def _frequence_annee():
    from hse.indicateurs import indicateurs_frequence

    today = timezone.localdate()
    return indicateurs_frequence(today.replace(month=1, day=1), today)


def _compute_conformite_j4(fiscal_year_id):
    from accounting_kernel.models import Period
    from controle_gestion.models import ClotureGestion

    closures = list(
        ClotureGestion.objects.filter(
            period__fiscal_year_id=fiscal_year_id, statut="realisee"
        )
    )
    n_periodes = Period.objects.filter(fiscal_year_id=fiscal_year_id).count()
    return {
        "conformes": sum(1 for c in closures if c.conforme_j4),
        "periodes": n_periodes,
        "taux": round(
            sum(1 for c in closures if c.conforme_j4) / n_periodes, 4
        ) if n_periodes else 0.0,
    }


def reporting_petrolier(user):
    """Reporting client pétrolier (C2) — ASMR (disponibilité) / HSE / Qualité.

    Filtre en dur (réplica : aucun montant financier — uniquement disponibilité
    matérielle, indicateurs HSE et Qualité liés à l'exécution des travaux).
    """
    from maintenance.models import Actif
    from hse.models import Incident, PermisTravail, Epi, EquipementAtex
    from qualite.models import (
        NonConformite,
        QualificationSoudeur,
        WpsWpqr,
        PvControle,
    )

    actif_status = Actif.Statut
    asmr_total = Actif.objects.count()
    asmr_dispo = Actif.objects.filter(statut=actif_status.OPERATIONNEL).count()

    quals = QualificationSoudeur.objects.all()
    nc = NonConformite.objects.all()
    itp_cnd = _indicateurs_itp_cnd()

    return {
        "asmr": {
            "equipements": asmr_total,
            "operationnels": asmr_dispo,
            "en_panne": Actif.objects.filter(statut=actif_status.EN_PANNE).count(),
            "en_maintenance": Actif.objects.filter(statut=actif_status.EN_MAINTENANCE).count(),
            "hors_service": Actif.objects.filter(statut=actif_status.HORS_SERVICE).count(),
            "en_arret": Actif.objects.filter(
                statut__in=[actif_status.EN_MAINTENANCE, actif_status.EN_PANNE]
            ).count(),
            "taux_disponibilite": round(asmr_dispo / asmr_total, 4) if asmr_total else 0.0,
        },
        "hse": {
            "jours_sans_accident": _jours_sans_accident(),
            # TRIR / LTIR / LTIFR de l'année en cours sur les heures pointées (lot 15, CDC M7 §9.7).
            "frequence": _frequence_annee(),
            "incidents": Incident.objects.count(),
            "incidents_ouverts": Incident.objects.exclude(statut=Incident.Statut.CLOTURE).count(),
            "accidents": Incident.objects.filter(
                type_incident__in=[Incident.TypeIncident.ACCIDENT, Incident.TypeIncident.BLESSURE]
            ).count(),
            "permis_actifs": PermisTravail.objects.filter(statut=PermisTravail.Statut.ACTIF).count(),
"permis_atex": PermisTravail.objects.filter(type_permis=PermisTravail.TypePermis.ATEX,
                                                    statut=PermisTravail.Statut.ACTIF).count(),
            "equipements_atex_quarantaine": EquipementAtex.objects.filter(
                statut=EquipementAtex.Statut.QUARANTAINE
            ).count(),
            "epi_a_renouveler": Epi.objects.filter(
                statut=Epi.Statut.EN_USAGE,
                date_renouvellement__lte=timezone.localdate() + timezone.timedelta(days=30),
            ).count(),
        },
        "qualite": {
            "soudeurs_qualifies": QualificationSoudeur.objects.filter(
                statut=QualificationSoudeur.Statut.VALIDE
            ).count(),
            "soudeurs_expires": QualificationSoudeur.objects.filter(
                statut=QualificationSoudeur.Statut.EXPIREE
            ).count(),
            "wps_valides": WpsWpqr.objects.filter(statut=WpsWpqr.Statut.VALIDE).count(),
            "nc_total": nc.count(),
            "nc_ouvertes": nc.exclude(statut=NonConformite.Statut.CLOTUREE).count(),
            "nc_critiques": nc.filter(gravite=NonConformite.Gravite.CRITIQUE)
            .exclude(statut=NonConformite.Statut.CLOTUREE).count(),
            "pv_sous_reserve": PvControle.objects.filter(statut=PvControle.Statut.RESERVE).count(),
        },
        "itp": itp_cnd["itp"],
        "cnd": itp_cnd["cnd"],
    }


def _indicateurs_itp_cnd():
    """Qualité ITP (points d'arrêt / d'observation) et CND (méthodes, résultats, taux de rejet) pour le client pétrolier."""
    from django.db.models import Count

    from qualite.models import ControleQualite, PointInspection

    actifs = ControleQualite.objects.exclude(statut=ControleQualite.Statut.ANNULE)
    itp = actifs.filter(type_controle=ControleQualite.TypeControle.ITP)
    points = PointInspection.objects.filter(controle__in=itp)
    n_points = points.count()
    leves = points.filter(statut=PointInspection.Statut.LEVE).count()
    cnd = actifs.filter(type_controle=ControleQualite.TypeControle.CND)
    tranches = {r["resultat"]: r["n"] for r in cnd.filter(statut=ControleQualite.Statut.VALIDE).values("resultat").annotate(n=Count("id"))}
    juges = sum(tranches.values())
    rejets = tranches.get(ControleQualite.Resultat.NON_CONFORME, 0)
    return {
        "itp": {
            "plans": itp.count(),
            "plans_approuves": itp.filter(approuve_le__isnull=False).count(),
            "points": n_points,
            "points_arret_en_attente": points.filter(
                type_point=PointInspection.TypePoint.ARRET, statut=PointInspection.Statut.EN_ATTENTE
            ).count(),
            "points_leves": leves,
            "points_non_conformes": points.filter(statut=PointInspection.Statut.NON_CONFORME).count(),
            "taux_levee": round(leves / n_points, 4) if n_points else 0.0,
        },
        "cnd": {
            "controles": cnd.count(),
            "en_cours": cnd.exclude(statut=ControleQualite.Statut.VALIDE).count(),
            "par_methode": {
                (r["methode_cnd"] or "non_precisee"): r["n"]
                for r in cnd.values("methode_cnd").annotate(n=Count("id")).order_by("methode_cnd")
            },
            "conformes": tranches.get(ControleQualite.Resultat.CONFORME, 0),
            "sous_reserve": tranches.get(ControleQualite.Resultat.RESERVE, 0),
            "non_conformes": rejets,
            "taux_rejet": round(rejets / juges, 4) if juges else 0.0,
        },
    }


def alertes_agregees(user=None):
    """Alertes J-90/J-60/J-30/J-15/J-0/expirées transverses (C3, EX-G-05).

    Agrège : rétention GED (documents), conventions/cautions/assurances
    (juridique, RF-ERP-B0), contrats & qualifications RH, permis/ATEX/EPI HSE.

    Avec `user`, chaque famille respecte les droits de lecture : documents via les ACL de la
    GED (paie restreinte RF-33), RH / juridique / maintenance via la matrice de lecture
    par module — une alerte nominative n'est jamais servie à un rôle sans accès au module.
    `user=None` = usage interne (tâches, tests) : tout est agrégé.
    """
    from documents.services import visible_documents
    from users.rbac import can_read_app

    def _allowed(app):
        return user is None or can_read_app(user, app)

    from juridique.services import compute_alertes
    from rh_paie.models import ContratTravail, Qualification
    from maintenance.models import Actif, Inspection
    from documents.models import Document

    compteurs = _zero()

    def _add(liste):
        for item in liste:
            bande = item.get("bande")
            if bande in compteurs:
                compteurs[bande] += 1

    # Rétention GED (documents).
    document_liste = []

    def _retention_end(doc):
        if not doc.type_id:
            return None
        base = doc.document_date or timezone.localdate()
        years = doc.type.retention_years if doc.type else 0
        return base + timezone.timedelta(days=365 * years) if years else None

    horizon = timezone.localdate() + timezone.timedelta(days=90)
    docs = visible_documents(user) if user is not None else Document.objects.all()
    for doc in docs.filter(type__retention_years__gt=0).select_related("type"):
        end = _retention_end(doc)
        if end is None or end > horizon:
            continue
        item = {
            "type": "document",
            "code": doc.type.label if doc.type else "document",
            "libelle": doc.title,
            "date_echeance": end,
            "bande": _band((end - timezone.localdate()).days),
            "jours": (end - timezone.localdate()).days,
            "statut": doc.status,
        }
        document_liste.append(item)

    juridique = (
        compute_alertes()
        if _allowed("juridique")
        else {"conventions": [], "cautions": [], "assurances": [], "compteurs": _zero()}
    )
    rh_liste = []
    for contrat in (
        ContratTravail.objects.filter(statut=ContratTravail.Statut.ACTIF, date_fin__lte=horizon)
        if _allowed("rh_paie")
        else ContratTravail.objects.none()
    ):
        jours = (contrat.date_fin - timezone.localdate()).days
        rh_liste.append({
            "type": "contrat_rh",
            "code": contrat.employe.code if contrat.employe_id else None,
            "libelle": f"{contrat.employe} — {contrat.get_type_display()}",
            "date_echeance": contrat.date_fin,
            "bande": _band(jours),
            "jours": jours,
            "statut": contrat.statut,
        })
    for qualif in (
        Qualification.objects.filter(date_validite__lte=horizon)
        if _allowed("rh_paie")
        else Qualification.objects.none()
    ):
        jours = (qualif.date_validite - timezone.localdate()).days
        rh_liste.append({
            "type": "qualification_rh",
            "code": qualif.get_type_display() if qualif.type else "qualification",
            "libelle": f"{qualif.employe} — {qualif.intitule}",
            "date_echeance": qualif.date_validite,
            "bande": _band(jours),
            "jours": jours,
            "statut": qualif.date_validite < timezone.localdate() and "expiree" or "active",
        })

    # Échéances des déclarations sociales et fiscales (CDC M9) : cercle de la paie uniquement.
    if _allowed("rh_paie"):
        from rh_paie.services import can_manage_paie

        if user is None or can_manage_paie(user):
            from rh_paie.paie_m9a import alertes_echeances_declarations

            rh_liste += alertes_echeances_declarations(_band)

    # Aptitudes médicales et EPI à renouveler (CDC M7-04 / M7-05) : délais paramétrables par ETSL.
    if _allowed("hse"):
        from hse.models import AptitudeMedicale, Epi
        from hse.services import get_param_hse

        aujourdhui_hse = timezone.localdate()
        vus = set()
        horizon_apt = aujourdhui_hse + timezone.timedelta(days=int(get_param_hse("APTITUDE_ALERTE_JOURS")))
        for apt in AptitudeMedicale.objects.select_related("employe").order_by("employe_id", "-date_visite"):
            if apt.employe_id in vus:
                continue
            vus.add(apt.employe_id)
            if apt.date_validite and apt.date_validite <= horizon_apt:
                jours = (apt.date_validite - aujourdhui_hse).days
                rh_liste.append({
                    "type": "aptitude_medicale", "code": "aptitude", "libelle": f"Aptitude médicale — {apt.employe}",
                    "date_echeance": apt.date_validite, "bande": _band(jours), "jours": jours,
                    "statut": "expiree" if jours < 0 else "active",
                })
        horizon_epi = aujourdhui_hse + timezone.timedelta(days=int(get_param_hse("EPI_ALERTE_JOURS")))
        for epi in Epi.objects.filter(statut=Epi.Statut.EN_USAGE, date_renouvellement__lte=horizon_epi).select_related("employe", "beneficiaire"):
            jours = (epi.date_renouvellement - aujourdhui_hse).days
            rh_liste.append({
                "type": "epi", "code": epi.code, "libelle": f"EPI {epi.get_type_epi_display()} — {epi.employe or (epi.beneficiaire.nom_affiche if epi.beneficiaire else epi.designation)}",
                "date_echeance": epi.date_renouvellement, "bande": _band(jours), "jours": jours,
                "statut": "expiree" if jours < 0 else "active",
            })

    qualite_liste = []
    if _allowed("qualite"):
        from qualite.ecarts import alertes_metrologie, alertes_qualifications_soudeurs
        from qualite.systeme import alertes_documents_qualite

        qualite_liste = alertes_qualifications_soudeurs(_band) + alertes_metrologie(_band) + alertes_documents_qualite(_band)

    maintenance_liste = []
    for actif in (
        Actif.objects.filter(statut__in=[Actif.Statut.EN_MAINTENANCE, Actif.Statut.EN_PANNE])
        if _allowed("maintenance")
        else Actif.objects.none()
    ):
        maintenance_liste.append({
            "type": "actif_arret",
            "code": actif.code,
            "libelle": actif.designation,
            "date_echeance": None,
            "bande": "en_cours",
            "jours": None,
            "statut": actif.statut,
        })
    # Inspections réglementaires (levage, ATEX, métrologie…) : planifiées, ou prochaine échéance d'une inspection
    # réalisée sans inspection plus récente du même type sur la même machine (CDC M8 §13.4 « suivi réglementaire »).
    if _allowed("maintenance"):
        aujourdhui = timezone.localdate()
        vues = set()
        for insp in Inspection.objects.exclude(statut=Inspection.Statut.ANNULEE).select_related("actif").order_by(
            "actif_id", "type_inspection", "-date_inspection"
        ):
            cle = (insp.actif_id, insp.type_inspection)
            if cle in vues:
                continue
            vues.add(cle)
            echeance = insp.date_inspection if insp.statut == Inspection.Statut.PLANIFIEE else insp.prochaine_inspection
            if echeance is None or echeance > aujourdhui + timezone.timedelta(days=90):
                continue
            jours = (echeance - aujourdhui).days
            maintenance_liste.append({
                "type": "inspection_reglementaire",
                "code": insp.code,
                "libelle": f"{insp.get_type_inspection_display()} — {insp.actif.designation} ({insp.actif.code})",
                "date_echeance": echeance,
                "bande": _band(jours),
                "jours": jours,
                "statut": insp.statut,
            })

    # Familles calendaires de la Couche D : garantie, agrément fournisseur, audit interne, revue de direction.
    from .pilotage import alertes_calendaires

    calendrier_liste = alertes_calendaires(user)

    _add(document_liste)
    _add(calendrier_liste)
    _add(juridique["conventions"] + juridique["cautions"] + juridique["assurances"])
    _add(rh_liste)
    _add(qualite_liste)
    _add([i for i in maintenance_liste if i["type"] == "inspection_reglementaire"])

    return {
        "documents": document_liste,
        "juridique": juridique,
        "rh": rh_liste,
        "qualite": qualite_liste,
        "maintenance": maintenance_liste,
        "calendrier": calendrier_liste,
        "compteurs": compteurs,
        "total": sum(compteurs.values()),
    }


def _can_see_amount(user):
    from documents.services import can_see_amount

    return can_see_amount(user) if user and user.is_authenticated else False


def _derniers_mois(n=6):
    """Les `n` derniers mois (le plus ancien d'abord), le dernier étant le mois courant : [(année, mois), ...]."""
    courant = timezone.localdate().replace(day=1)
    mois = [courant]
    for _ in range(n - 1):
        mois.append((mois[-1] - timezone.timedelta(days=1)).replace(day=1))
    return [(d.year, d.month) for d in reversed(mois)]


def tendances(user, n=6):
    """Séries mensuelles NON financières du cockpit Direction (documents, incidents HSE, ordres de travail).

    Chaque série respecte les droits de lecture : documents via les ACL de la GED (paie restreinte),
    incidents / ordres de travail uniquement pour les rôles qui lisent HSE / Maintenance (sinon `None`).
    """
    from django.db.models import Count
    from django.db.models.functions import TruncMonth

    from documents.models import Document
    from documents.services import visible_documents
    from hse.models import Incident
    from maintenance.models import OrdreTravail
    from users.rbac import can_read_app

    mois = _derniers_mois(n)
    debut = timezone.make_aware(timezone.datetime(mois[0][0], mois[0][1], 1))

    def serie(queryset, champ):
        agg = (
            queryset.filter(**{f"{champ}__gte": debut})
            .annotate(m=TruncMonth(champ))
            .values("m")
            .annotate(c=Count("id"))
        )
        par_mois = {(row["m"].year, row["m"].month): row["c"] for row in agg}
        return [par_mois.get(k, 0) for k in mois]

    return {
        "mois": [f"{y}-{m:02d}" for y, m in mois],
        "series": {
            "documents": serie(visible_documents(user), "created_at"),
            "incidents": serie(Incident.objects.all(), "date_evenement") if can_read_app(user, "hse") else None,
            "ordres_travail": serie(OrdreTravail.objects.all(), "created_at")
            if can_read_app(user, "maintenance")
            else None,
        },
    }
