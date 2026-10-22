"""API des écarts M11 (2026-10-21) — voir `ecarts_m11.py`."""

from datetime import timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.fields import DateField
from rest_framework.response import Response

from referentiels.models import AnalyticAccount, AnalyticAxis
from referentiels.serializers import AnalyticAccountSerializer, AnalyticAxisSerializer
from users.permissions import can_read_module

from . import ecarts_m11 as svc
from .models import (
    Budget,
    BudgetLigne,
    BudgetRevision,
    BudgetRevisionLigne,
    ClotureGestion,
    PlanActionSousActivite,
    ProvisionFnp,
    ReportingArchive,
    RevuePerformance,
)
from .services import CanApproveBudget, CanManageGestion, can_see_amount, get_param_gestion
from .views import DjangoValidationMixin, _fiscal_year_requis
from config.i18n import tr


def _money(voir, v):
    return (None if v is None else f"{v:.2f}") if voir else None


def _date(request, name, required=True, default=None):
    brut = request.data.get(name) if request.method == "POST" else request.query_params.get(name)
    if brut in (None, ""):
        if required and default is None:
            raise DRFValidationError({name: "Date requise (AAAA-MM-JJ)."})
        return default
    return DateField().run_validation(brut)


# ------------------------------------------------------------------------------------------------
# Révision par ligne mensuelle
# ------------------------------------------------------------------------------------------------
class BudgetRevisionLigneSerializer(serializers.ModelSerializer):
    period_label = serializers.CharField(source="period.__str__", read_only=True)
    revision_code = serializers.CharField(source="revision.code", read_only=True)

    class Meta:
        model = BudgetRevisionLigne
        fields = ["id", "revision", "revision_code", "period", "period_label", "ancien_montant", "nouveau_montant"]
        read_only_fields = ["ancien_montant"]

    def validate_nouveau_montant(self, value):
        if value < 0:
            raise serializers.ValidationError("Le montant révisé ne peut pas être négatif.")
        return value

    def validate(self, attrs):
        revision = attrs.get("revision") or self.instance.revision
        period = attrs.get("period") or self.instance.period
        if revision.statut != BudgetRevision.Statut.BROUILLON or revision.visa_daf_par_id or revision.visa_cg_par_id:
            raise serializers.ValidationError("Révision visée ou appliquée : lignes non modifiables.")
        if period.fiscal_year_id != revision.budget.fiscal_year_id:
            raise serializers.ValidationError("La période doit appartenir à l'exercice du budget.")
        doublon = BudgetRevisionLigne.objects.filter(revision=revision, period=period)
        if self.instance:
            doublon = doublon.exclude(pk=self.instance.pk)
        if doublon.exists():
            raise serializers.ValidationError("Cette période est déjà révisée dans cette révision : modifiez la ligne.")
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not can_see_amount(getattr(self.context.get("request"), "user", None)):
            data["ancien_montant"] = data["nouveau_montant"] = None
        return data


def _recalculer_revision(revision):
    """Montant après révision = montant en vigueur + Σ(révisé − actuel) des lignes révisées."""
    delta = sum((l.nouveau_montant - l.ancien_montant for l in revision.lignes.all()), 0)
    revision.nouveau_montant = revision.ancien_montant + delta
    revision.save(update_fields=["nouveau_montant", "updated_at"])


class BudgetRevisionLigneViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    queryset = BudgetRevisionLigne.objects.select_related("revision__budget", "period").all()
    serializer_class = BudgetRevisionLigneSerializer
    permission_classes = [CanManageGestion]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        if revision := self.request.query_params.get("revision"):
            qs = qs.filter(revision_id=revision)
        return qs

    @transaction.atomic
    def perform_create(self, serializer):
        revision, period = serializer.validated_data["revision"], serializer.validated_data["period"]
        actuelle = BudgetLigne.objects.filter(budget=revision.budget, period=period).first()
        ligne = serializer.save(ancien_montant=actuelle.montant if actuelle else 0)
        _recalculer_revision(ligne.revision)

    @transaction.atomic
    def perform_update(self, serializer):
        _recalculer_revision(serializer.save().revision)

    @transaction.atomic
    def perform_destroy(self, instance):
        revision = instance.revision
        if revision.statut != BudgetRevision.Statut.BROUILLON or revision.visa_daf_par_id or revision.visa_cg_par_id:
            raise DRFValidationError("Révision visée ou appliquée : lignes non modifiables.")
        instance.delete()
        _recalculer_revision(revision)


# ------------------------------------------------------------------------------------------------
# Axes analytiques (activité, profil…) : écran d'administration M11
# ------------------------------------------------------------------------------------------------
class AxeGestionViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    queryset = AnalyticAxis.objects.all().order_by("code")
    serializer_class = AnalyticAxisSerializer
    permission_classes = [CanManageGestion]
    http_method_names = ["get", "post", "patch", "head", "options"]
    search_fields = ("code", "label")

    @action(detail=False, methods=["post"])
    def initialiser(self, request):
        return Response({"crees": svc.initialiser_axes()})


class ValeurAxeViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    queryset = AnalyticAccount.objects.select_related("axis").all().order_by("axis__code", "code")
    serializer_class = AnalyticAccountSerializer
    permission_classes = [CanManageGestion]
    http_method_names = ["get", "post", "patch", "head", "options"]
    search_fields = ("code", "label")

    def get_queryset(self):
        qs = super().get_queryset()
        if axis := self.request.query_params.get("axis"):
            if not axis.isdigit():
                raise DRFValidationError("Paramètre `axis` doit être un entier.")
            qs = qs.filter(axis_id=axis)
        return qs


# ------------------------------------------------------------------------------------------------
# Lectures de pilotage (imputation, pipe, KPI, tableau de bord, coût MO)
# ------------------------------------------------------------------------------------------------
FY_PARAM = [OpenApiParameter("fiscal_year", type=int, required=True)]


class ImputationStructureView(viewsets.ViewSet):
    permission_classes = [can_read_module("controle_gestion")]

    @extend_schema(parameters=FY_PARAM, responses={200: OpenApiTypes.OBJECT})
    def list(self, request):
        r = svc.imputer_structure(_fiscal_year_requis(request))
        voir = can_see_amount(request.user)
        for row in r["rows"]:
            for k in ("produits", "charges_directes", "marge_directe", "structure_imputee", "marge_apres_structure"):
                row[k] = _money(voir, row[k])
        r["charges_structure"] = _money(voir, r["charges_structure"])
        r["non_imputees"] = _money(voir, r["non_imputees"])
        return Response(r)


class PipeBudgetView(viewsets.ViewSet):
    """Pipe pondéré (RGM_POND_PROSPECT) et proposition d'un budget de produits brouillon."""

    def get_permissions(self):
        return [CanManageGestion()] if getattr(self, "action", None) == "proposer" else [can_read_module("controle_gestion")()]

    @extend_schema(parameters=FY_PARAM, responses={200: OpenApiTypes.OBJECT})
    def list(self, request):
        r = svc.pipe_pondere_m11(_fiscal_year_requis(request))
        voir = can_see_amount(request.user)
        for c in r["categories"]:
            c["brut"], c["pondere"] = _money(voir, c["brut"]), _money(voir, c["pondere"])
            c["ponderation"] = f"{c['ponderation']:.2f}"
        r["total"] = _money(voir, r["total"])
        return Response(r)

    @action(detail=False, methods=["post"])
    def proposer(self, request):
        fy = str(request.data.get("fiscal_year") or "")
        if not fy.isdigit():
            raise DRFValidationError({"fiscal_year": "Exercice requis."})
        try:
            budget = svc.proposer_budget_pipe(fy, request.user)
        except DjangoValidationError as exc:
            raise DRFValidationError(exc.messages)
        return Response({"budget": str(budget.pk), "code": budget.code}, status=201)


class KpiView(viewsets.ViewSet):
    permission_classes = [can_read_module("controle_gestion")]

    @extend_schema(parameters=FY_PARAM, responses={200: OpenApiTypes.OBJECT})
    def list(self, request):
        return Response(svc.compute_kpis(_fiscal_year_requis(request)))


class TableauBordView(viewsets.ViewSet):
    """Tableau de bord Direction par profil contractuel, client, affaire ou responsable (marges prévues / réelles)."""

    permission_classes = [can_read_module("controle_gestion")]

    @extend_schema(parameters=[OpenApiParameter("par", type=str, required=False)], responses={200: OpenApiTypes.OBJECT})
    def list(self, request):
        from commercial.services import MARGE_AXES, marges_affaires

        par = request.query_params.get("par") or "profil"
        if par not in MARGE_AXES:
            raise DRFValidationError({"par": tr("Valeurs possibles : %(liste)s.") % {"liste": ', '.join(MARGE_AXES)}})
        return Response(marges_affaires(par, can_see_amount(request.user)))


class CoutMoAffairesView(viewsets.ViewSet):
    """Coût de main-d'œuvre chargé par affaire (pointages M3 valorisés par M9) : lecture seule."""

    permission_classes = [can_read_module("controle_gestion")]

    @extend_schema(
        parameters=[OpenApiParameter("debut", type=str, required=False), OpenApiParameter("fin", type=str, required=False)],
        responses={200: OpenApiTypes.OBJECT},
    )
    def list(self, request):
        today = timezone.localdate()
        debut = _date(request, "debut", default=today.replace(month=1, day=1))
        fin = _date(request, "fin", default=today)
        voir = can_see_amount(request.user)
        rows = svc.cout_mo_par_affaire(debut, fin)
        for r in rows:
            r["heures"], r["heures_non_valorisees"] = f"{r['heures']:.2f}", f"{r['heures_non_valorisees']:.2f}"
            r["cout"], r["cout_horaire_moyen"] = _money(voir, r["cout"]), _money(voir, r["cout_horaire_moyen"])
        return Response({"debut": debut.isoformat(), "fin": fin.isoformat(), "rows": rows, "has_amount_access": voir})


# ------------------------------------------------------------------------------------------------
# Validation de la marge d'affaire
# ------------------------------------------------------------------------------------------------
class MargeAffaireViewSet(viewsets.ViewSet):
    def get_permissions(self):
        if getattr(self, "action", None) in ("valider", "rejeter"):
            return [CanApproveBudget()]
        return [can_read_module("controle_gestion")()]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def list(self, request):
        voir = can_see_amount(request.user)
        rows = svc.marges_a_valider()
        for r in rows:
            r["ca"], r["marge"] = _money(voir, r["ca"]), _money(voir, r["marge"])
            if not voir:
                r["taux"] = None
        return Response({"rows": rows, "has_amount_access": voir})

    def _decider(self, request, pk, statut):
        try:
            with transaction.atomic():
                v = svc.decider_marge(pk, statut, request.data.get("commentaire"), request.user)
        except DjangoValidationError as exc:
            raise DRFValidationError(getattr(exc, "message_dict", None) or exc.messages)
        return Response({"affaire": str(v.affaire_id), "statut": v.statut, "le": v.le.isoformat()})

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    @action(detail=True, methods=["post"])
    def valider(self, request, pk=None):
        return self._decider(request, pk, "validee")

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    @action(detail=True, methods=["post"])
    def rejeter(self, request, pk=None):
        return self._decider(request, pk, "rejetee")


# ------------------------------------------------------------------------------------------------
# Plan d'action de sous-activité
# ------------------------------------------------------------------------------------------------
class PlanActionSerializer(serializers.ModelSerializer):
    budget_code = serializers.CharField(source="budget.code", read_only=True)
    budget_label = serializers.CharField(source="budget.label", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    responsable_nom = serializers.SerializerMethodField()
    en_retard = serializers.BooleanField(read_only=True)

    class Meta:
        model = PlanActionSousActivite
        fields = ["id", "code", "budget", "budget_code", "budget_label", "alerte", "centre", "taux", "actions",
                  "responsable", "responsable_nom", "echeance", "statut", "statut_label", "suivi", "en_retard",
                  "clos_par", "clos_le", "created_by", "created_at"]
        read_only_fields = ["code", "alerte", "centre", "taux", "statut", "suivi", "clos_par", "clos_le", "created_by"]

    def get_responsable_nom(self, obj):
        return (obj.responsable.get_full_name() or obj.responsable.email) if obj.responsable_id else None


class PlanActionViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    queryset = PlanActionSousActivite.objects.select_related("budget", "responsable").all()
    serializer_class = PlanActionSerializer
    permission_classes = [CanManageGestion]
    http_method_names = ["get", "post", "patch", "head", "options"]
    search_fields = ("code",)

    def perform_create(self, serializer):
        budget = serializer.validated_data["budget"]
        if budget.statut == Budget.Statut.BROUILLON:
            raise DRFValidationError("Plan d'action sur un budget approuvé uniquement.")
        centre, taux, alerte = svc.situation_sous_activite(budget)
        echeance = serializer.validated_data.get("echeance") or (
            timezone.localdate() + timedelta(days=int(get_param_gestion("PLAN_ACTION_DELAI")))
        )
        serializer.save(created_by=self.request.user, centre=centre, taux=taux, alerte=alerte, echeance=echeance)

    def perform_update(self, serializer):
        if serializer.instance.statut == PlanActionSousActivite.Statut.CLOS:
            raise DRFValidationError("Plan d'action clos : non modifiable.")
        serializer.save()

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def demarrer(self, request, pk=None):
        plan = PlanActionSousActivite.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if plan.statut != PlanActionSousActivite.Statut.OUVERT:
            raise DRFValidationError("Seul un plan ouvert peut être démarré.")
        plan.statut = PlanActionSousActivite.Statut.EN_COURS
        plan.save(update_fields=["statut", "updated_at"])
        return Response(self.get_serializer(plan).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def clore(self, request, pk=None):
        plan = PlanActionSousActivite.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if plan.statut == PlanActionSousActivite.Statut.CLOS:
            raise DRFValidationError("Plan d'action déjà clos.")
        suivi = str(request.data.get("suivi") or "").strip()
        if not suivi:
            raise DRFValidationError({"suivi": "Résultat du plan d'action obligatoire."})
        plan.suivi, plan.statut = suivi, PlanActionSousActivite.Statut.CLOS
        plan.clos_par, plan.clos_le = request.user, timezone.now()
        plan.save(update_fields=["suivi", "statut", "clos_par", "clos_le", "updated_at"])
        return Response(self.get_serializer(plan).data)


# ------------------------------------------------------------------------------------------------
# Reporting par horizon (PDF archivé GED)
# ------------------------------------------------------------------------------------------------
class ReportingArchiveSerializer(serializers.ModelSerializer):
    cloture_code = serializers.CharField(source="cloture.code", read_only=True)
    period_label = serializers.CharField(source="cloture.period.__str__", read_only=True)
    document_titre = serializers.CharField(source="document.title", read_only=True, default=None)

    class Meta:
        model = ReportingArchive
        fields = ["id", "cloture", "cloture_code", "period_label", "type_reporting", "horizon", "echeance",
                  "archive_le", "a_temps", "document", "document_titre", "archive_par"]
        read_only_fields = fields


class ReportingViewSet(viewsets.ReadOnlyModelViewSet):
    """Reportings archivés ; `donnees` (JSON ou `?export=pdf`) et `archiver` portent sur une clôture."""

    queryset = ReportingArchive.objects.select_related("cloture__period", "document").all()
    serializer_class = ReportingArchiveSerializer

    def get_permissions(self):
        if getattr(self, "action", None) == "archiver":
            return [CanApproveBudget()]
        return [CanManageGestion()]

    def _cloture(self, request):
        cid = request.query_params.get("cloture") if request.method == "GET" else request.data.get("cloture")
        try:
            return ClotureGestion.objects.select_related("period").get(pk=cid)
        except (ClotureGestion.DoesNotExist, ValueError, DjangoValidationError):
            raise DRFValidationError({"cloture": "Clôture de gestion introuvable."})

    @extend_schema(
        parameters=[OpenApiParameter("cloture", type=str, required=True), OpenApiParameter("type", type=str, required=True),
                    OpenApiParameter("export", type=str, required=False)],
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["get"])
    def donnees(self, request):
        cloture = self._cloture(request)
        type_reporting = request.query_params.get("type") or "j4"
        try:
            if request.query_params.get("export") == "pdf":
                contenu, _ = svc.reporting_pdf(cloture, type_reporting)
                resp = HttpResponse(contenu, content_type="application/pdf")
                resp["Content-Disposition"] = f'attachment; filename="REPORTING-{cloture.code}-{type_reporting.upper()}.pdf"'
                return resp
            data = svc.donnees_reporting(cloture, type_reporting)
        except DjangoValidationError as exc:
            raise DRFValidationError(exc.messages)
        if not can_see_amount(request.user):
            for r in data["rows"]:
                for k in list(r):
                    if k not in ("period", "period_label"):
                        r[k] = None
        return Response(data)

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: ReportingArchiveSerializer})
    @action(detail=False, methods=["post"])
    def archiver(self, request):
        cloture = self._cloture(request)
        try:
            archive = svc.archiver_reporting(cloture, str(request.data.get("type") or ""), request.user)
        except DjangoValidationError as exc:
            raise DRFValidationError(exc.messages)
        return Response(self.get_serializer(archive).data, status=201)


# ------------------------------------------------------------------------------------------------
# Revue de performance P-M11.10
# ------------------------------------------------------------------------------------------------
class RevuePerformanceSerializer(serializers.ModelSerializer):
    period_label = serializers.CharField(source="period.__str__", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)

    class Meta:
        model = RevuePerformance
        fields = ["id", "code", "period", "period_label", "date_revue", "ordre_du_jour", "participants", "decisions",
                  "kpis", "statut", "statut_label", "pv_document", "tenue_par", "tenue_le", "created_by", "created_at"]
        read_only_fields = ["code", "decisions", "kpis", "statut", "pv_document", "tenue_par", "tenue_le", "created_by"]


class RevuePerformanceViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    queryset = RevuePerformance.objects.select_related("period").all()
    serializer_class = RevuePerformanceSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    search_fields = ("code",)

    def get_permissions(self):
        if getattr(self, "action", None) == "tenir":
            return [CanApproveBudget()]
        return [CanManageGestion()]

    def perform_create(self, serializer):
        odj = (serializer.validated_data.get("ordre_du_jour") or "").strip() or svc.ODJ_REVUE_DEFAUT
        serializer.save(created_by=self.request.user, ordre_du_jour=odj)

    def perform_update(self, serializer):
        if serializer.instance.statut != RevuePerformance.Statut.PLANIFIEE:
            raise DRFValidationError("Revue tenue : PV archivé, non modifiable.")
        serializer.save()

    @action(detail=True, methods=["post"])
    def tenir(self, request, pk=None):
        revue = svc.tenir_revue(self.get_object(), str(request.data.get("decisions") or ""), request.user)
        return Response(self.get_serializer(revue).data)


# ------------------------------------------------------------------------------------------------
# Provision des factures non parvenues (408)
# ------------------------------------------------------------------------------------------------
class ProvisionFnpSerializer(serializers.ModelSerializer):
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    move_number = serializers.CharField(source="move.number", read_only=True, default=None)
    extourne_number = serializers.CharField(source="extourne.number", read_only=True, default=None)

    class Meta:
        model = ProvisionFnp
        fields = ["id", "code", "date_arrete", "montant", "detail", "statut", "statut_label", "move", "move_number",
                  "extourne", "extourne_number", "created_by", "created_at"]
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not can_see_amount(getattr(self.context.get("request"), "user", None)):
            data["montant"], data["detail"] = None, []
        return data


class ProvisionFnpViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ProvisionFnp.objects.select_related("move", "extourne").all()
    serializer_class = ProvisionFnpSerializer
    search_fields = ("code",)

    def get_permissions(self):
        if getattr(self, "action", None) in ("provisionner", "extourner"):
            return [CanApproveBudget()]
        return [CanManageGestion()]

    @extend_schema(parameters=[OpenApiParameter("date", type=str, required=False)], responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["get"])
    def apercu(self, request):
        jour = _date(request, "date", default=timezone.localdate())
        voir = can_see_amount(request.user)
        lignes = [{k: v for k, v in x.items() if not k.endswith("_id")} for x in svc.calculer_fnp(jour)]
        total = sum((float(x["montant"]) for x in lignes), 0.0)
        if not voir:
            for x in lignes:
                x["prix"] = x["montant"] = None
        return Response({"date": jour.isoformat(), "lignes": lignes, "total": f"{total:.2f}" if voir else None,
                         "compte": str(int(get_param_gestion("PROVISION_FNP_COMPTE")))})

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: ProvisionFnpSerializer})
    @action(detail=False, methods=["post"])
    def provisionner(self, request):
        try:
            p = svc.provisionner_fnp(_date(request, "date_arrete"), request.user)
        except DjangoValidationError as exc:
            raise DRFValidationError(exc.messages)
        return Response(self.get_serializer(p).data, status=201)

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: ProvisionFnpSerializer})
    @action(detail=True, methods=["post"])
    def extourner(self, request, pk=None):
        try:
            p = svc.extourner_fnp(self.get_object(), _date(request, "date", required=False), request.user)
        except DjangoValidationError as exc:
            raise DRFValidationError(exc.messages)
        return Response(self.get_serializer(p).data)
