"""API module M11 — Contrôle de gestion (RF-ERP-A0…A4)."""

from datetime import date, timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Budget, BudgetLigne, BudgetRevision, ClotureGestion
from .serializers import (
    BudgetLigneSerializer,
    BudgetRevisionSerializer,
    BudgetSerializer,
    ClotureGestionSerializer,
)
from .services import (
    CanApproveBudget,
    CanManageGestion,
    compute_clotures_stats,
    compute_marges,
    compute_variance,
)


class DjangoValidationMixin:
    """Convertit les `ValidationError` Django en réponses HTTP 400."""

    def handle_exception(self, exc):
        if isinstance(exc, DjangoValidationError):
            exc = DRFValidationError(getattr(exc, "messages", [str(exc)]))
        return super().handle_exception(exc)


class BudgetViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    queryset = Budget.objects.select_related(
        "fiscal_year", "axis", "analytic"
    ).prefetch_related("lignes", "revisions")
    serializer_class = BudgetSerializer

    def get_permissions(self):
        if getattr(self, "action", None) in ("approuver", "cloturer"):
            return [CanApproveBudget()]
        return [CanManageGestion()]

    def get_queryset(self):
        qs = super().get_queryset()
        fiscal_year = self.request.query_params.get("fiscal_year")
        type_budget = self.request.query_params.get("type_budget")
        statut = self.request.query_params.get("statut")
        axis = self.request.query_params.get("axis")
        analytic = self.request.query_params.get("analytic")
        if fiscal_year:
            qs = qs.filter(fiscal_year_id=fiscal_year)
        if type_budget:
            qs = qs.filter(type_budget=type_budget)
        if statut:
            qs = qs.filter(statut=statut)
        if axis:
            qs = qs.filter(axis_id=axis)
        if analytic:
            qs = qs.filter(analytic_id=analytic)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["get"])
    def variance(self, request, pk=None):
        budget = self.get_object()
        result = compute_variance(budget)
        return Response(result)

    @action(detail=True, methods=["post"])
    def approuver(self, request, pk=None):
        budget = self.get_object()
        if budget.statut != Budget.Statut.BROUILLON:
            raise DRFValidationError("Seul un budget brouillon peut être approuvé.")
        budget.statut = Budget.Statut.APPROUVE
        budget.save(update_fields=["statut", "updated_at"])
        return Response(self.get_serializer(budget).data)

    @action(detail=True, methods=["post"])
    def cloturer(self, request, pk=None):
        budget = self.get_object()
        if budget.statut != Budget.Statut.APPROUVE:
            raise DRFValidationError("Seul un budget approuvé peut être clôturé.")
        budget.statut = Budget.Statut.CLOTURE
        budget.save(update_fields=["statut", "updated_at"])
        return Response(self.get_serializer(budget).data)


class BudgetLigneViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    queryset = BudgetLigne.objects.select_related("budget", "period").all()
    serializer_class = BudgetLigneSerializer
    permission_classes = [CanManageGestion]

    def get_queryset(self):
        qs = super().get_queryset()
        budget = self.request.query_params.get("budget")
        if budget:
            qs = qs.filter(budget_id=budget)
        return qs


class BudgetRevisionViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    """Révisions budgétaires R1-R4 (RF-ERP-A1)."""

    queryset = BudgetRevision.objects.select_related("budget", "created_by").all()
    serializer_class = BudgetRevisionSerializer

    def get_permissions(self):
        if getattr(self, "action", None) == "appliquer":
            return [CanApproveBudget()]
        return [CanManageGestion()]

    def get_queryset(self):
        qs = super().get_queryset()
        budget = self.request.query_params.get("budget")
        if budget:
            qs = qs.filter(budget_id=budget)
        return qs

    def perform_create(self, serializer):
        budget = serializer.validated_data.get("budget")
        numero = budget.revisions.count() + 1
        if numero > 4:
            raise DRFValidationError(
                "Au plus 4 révisions budgétaires annuelles par budget (R1-R4, RF-ERP-A1)."
            )
        nouveau = serializer.validated_data.get("nouveau_montant") or budget.montant
        serializer.save(
            code=None,
            numero=numero,
            ancien_montant=budget.montant,
            nouveau_montant=nouveau,
            statut=BudgetRevision.Statut.BROUILLON,
            created_by=self.request.user,
        )

    @action(detail=True, methods=["post"])
    def appliquer(self, request, pk=None):
        """Applique une révision : ajuste le montant du budget (R1-R4)."""
        revision = self.get_object()
        if revision.statut != BudgetRevision.Statut.BROUILLON:
            raise DRFValidationError("Révision déjà appliquée ou annulée.")
        budget = revision.budget
        budget.montant = revision.nouveau_montant
        budget.save(update_fields=["montant", "updated_at"])
        revision.statut = BudgetRevision.Statut.APPLIQUEE
        revision.save(update_fields=["statut", "updated_at"])
        return Response(
            BudgetSerializer(budget, context=self.get_serializer_context()).data
        )


class ClotureGestionViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    queryset = ClotureGestion.objects.select_related("period", "created_by").all()
    serializer_class = ClotureGestionSerializer

    def get_permissions(self):
        if getattr(self, "action", None) == "realiser":
            return [CanApproveBudget()]
        return [CanManageGestion()]

    def get_queryset(self):
        qs = super().get_queryset()
        fiscal_year = self.request.query_params.get("fiscal_year")
        statut = self.request.query_params.get("statut")
        if fiscal_year:
            if not fiscal_year.isdigit():
                raise DRFValidationError("Paramètre `fiscal_year` doit être un entier.")
            qs = qs.filter(period__fiscal_year_id=fiscal_year)
        if statut:
            qs = qs.filter(statut=statut)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def realiser(self, request, pk=None):
        cloture = self.get_object()
        if cloture.statut == ClotureGestion.Statut.REALISEE:
            raise DRFValidationError("Clôture déjà réalisée.")
        valeur = request.data.get("date_cloture")
        if isinstance(valeur, str):
            try:
                valeur = date.fromisoformat(valeur)
            except (TypeError, ValueError):
                raise DRFValidationError("`date_cloture` doit être une date ISO.")
        cloture.date_cloture = valeur or (cloture.period.end_date + timedelta(days=2))
        cloture.statut = ClotureGestion.Statut.REALISEE
        cloture.save(update_fields=["date_cloture", "statut", "updated_at"])
        return Response(self.get_serializer(cloture).data)

    @action(detail=False, methods=["get"])
    def stats(self, request):
        fiscal_year = request.query_params.get("fiscal_year") or None
        if fiscal_year and not fiscal_year.isdigit():
            raise DRFValidationError("Paramètre `fiscal_year` doit être un entier.")
        result = compute_clotures_stats(fiscal_year)
        return Response(result)


@extend_schema(
    parameters=[
        OpenApiParameter("fiscal_year", type=int, required=True, description="Exercice (année)."),
        OpenApiParameter("axis", type=str, required=False, description="Code axe analytique."),
        OpenApiParameter("analytic", type=str, required=False, description="Code compte analytique."),
    ],
    responses={200: OpenApiTypes.OBJECT},
)
class MargesView(viewsets.ViewSet):
    """Marges par axe analytique (RF-ERP-A2) — coût GR isolé (A4)."""

    permission_classes = [IsAuthenticated]

    def list(self, request):
        fiscal_year = request.query_params.get("fiscal_year")
        if not fiscal_year:
            raise DRFValidationError("Paramètre `fiscal_year` requis.")
        if not fiscal_year.isdigit():
            raise DRFValidationError("Paramètre `fiscal_year` doit être un entier.")
        axis = request.query_params.get("axis")
        analytic = request.query_params.get("analytic")
        if axis and not axis.isdigit():
            raise DRFValidationError("Paramètre `axis` doit être un entier (id d'axe).")
        if analytic and not analytic.isdigit():
            raise DRFValidationError("Paramètre `analytic` doit être un entier (id de compte analytique).")
        result = compute_marges(fiscal_year, axis=axis, analytic=analytic)
        return Response(result, status=status.HTTP_200_OK)