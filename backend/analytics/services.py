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

from users.models import User


def _band(days_left):
    if days_left is None:
        return "en_cours"
    if days_left < 0:
        return "expiree"
    if days_left <= 30:
        return "j30"
    if days_left <= 60:
        return "j60"
    if days_left <= 90:
        return "j90"
    return "en_cours"


BAND_ORDER = ("expiree", "j30", "j60", "j90")


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
    from stocks.models import ArticleStock, StockQuant, LotMatiere, MouvementStock, Depot
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
        }
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
                statut__in=[OrdreTravail.Statut.CLOTURE, OrdreTravail.Statut.ANNULE]
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
    }


def alertes_agregees():
    """Alertes J-90/J-60/J-30/expirées transverses (C3).

    Agrège : rétention GED (documents), conventions/cautions/assurances
    (juridique, RF-ERP-B0), contrats & qualifications RH, permis/ATEX/EPI HSE.
    """
    from juridique.services import compute_alertes
    from rh_paie.models import ContratTravail, Qualification
    from maintenance.models import Actif
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
    for doc in Document.objects.filter(type__retention_years__gt=0).select_related("type"):
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

    juridique = compute_alertes()
    rh_liste = []
    for contrat in ContratTravail.objects.filter(statut=ContratTravail.Statut.ACTIF,
                                                 date_fin__lte=horizon):
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
    for qualif in Qualification.objects.filter(date_validite__lte=horizon):
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

    maintenance_liste = []
    for actif in Actif.objects.filter(
        statut__in=[Actif.Statut.EN_MAINTENANCE, Actif.Statut.EN_PANNE]
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

    _add(document_liste)
    _add(juridique["conventions"] + juridique["cautions"] + juridique["assurances"])
    _add(rh_liste)

    return {
        "documents": document_liste,
        "juridique": juridique,
        "rh": rh_liste,
        "maintenance": maintenance_liste,
        "compteurs": compteurs,
        "total": sum(compteurs.values()),
    }


def _can_see_amount(user):
    from documents.services import can_see_amount

    return can_see_amount(user) if user and user.is_authenticated else False