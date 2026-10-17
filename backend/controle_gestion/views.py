"""API module M11 — Contrôle de gestion (RF-ERP-A0…A4)."""

from datetime import date, timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from django.db.models import Prefetch

from .models import Budget, BudgetLigne, BudgetRevision, ClotureGestion
from .serializers import (
    BudgetLigneSerializer,
    BudgetRevisionSerializer,
    BudgetSerializer,
    ClotureGestionSerializer,
)
from users.permissions import can_read_module
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


def _apposer_visa(obj, request):
    """Pose le visa DAF ou CG demandé ; retourne True quand les DEUX visas sont réunis (CDC M11 §4.4).

    Deux personnes distinctes : celui qui a posé un visa ne pose pas l'autre (séparation des tâches).
    """
    visa = (request.data.get("visa") or "").strip().lower()
    if visa not in ("daf", "cg"):
        raise DRFValidationError({"visa": "Préciser le visa apposé : « daf » ou « cg »."})
    champ, autre = (("visa_daf_par", "visa_cg_par") if visa == "daf" else ("visa_cg_par", "visa_daf_par"))
    if getattr(obj, f"{champ}_id"):
        raise DRFValidationError({"visa": f"Visa {visa.upper()} déjà apposé."})
    if getattr(obj, f"{autre}_id") == request.user.id:
        raise DRFValidationError({"visa": "Double visa : le second visa doit être apposé par une autre personne."})
    setattr(obj, champ, request.user)
    setattr(obj, champ.replace("_par", "_le"), timezone.now())
    obj.save(update_fields=[champ, champ.replace("_par", "_le"), "updated_at"])
    return bool(obj.visa_daf_par_id and obj.visa_cg_par_id)


class BudgetViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    queryset = Budget.objects.select_related(
        "fiscal_year", "axis", "analytic"
    ).prefetch_related(
        Prefetch("lignes", queryset=BudgetLigne.objects.select_related("period__fiscal_year")),
        "revisions",
    )
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

    def perform_update(self, serializer):
        # Version budgétaire scellée : un budget approuvé ou clôturé ne se modifie que par révision (R1-R4).
        if serializer.instance.statut != Budget.Statut.BROUILLON:
            raise DRFValidationError("Budget approuvé (version scellée) : modification par révision R1-R4 uniquement.")
        serializer.save()

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def approuver(self, request, pk=None):
        """Visa DAF ou CG sur la version V0 ; le budget entre en vigueur au second visa."""
        budget = Budget.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if budget.statut != Budget.Statut.BROUILLON:
            raise DRFValidationError("Seul un budget brouillon peut être approuvé.")
        if _apposer_visa(budget, request):
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
    queryset = BudgetLigne.objects.select_related("budget", "period__fiscal_year").all()
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
        if budget.statut == Budget.Statut.CLOTURE:
            raise DRFValidationError("Budget clôturé : aucune révision possible.")
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
    @transaction.atomic
    def appliquer(self, request, pk=None):
        """Visa DAF ou CG sur la révision ; elle s'applique au budget au second visa (R1-R4)."""
        revision = BudgetRevision.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if revision.statut != BudgetRevision.Statut.BROUILLON:
            raise DRFValidationError("Révision déjà appliquée ou annulée.")
        budget = revision.budget
        if budget.statut == Budget.Statut.CLOTURE:
            raise DRFValidationError("Budget clôturé : révision non applicable.")
        # Révision préparée sur un montant périmé (une autre révision a été appliquée entre-temps) : l'appliquer
        # écraserait silencieusement la précédente. Il faut la refaire sur le montant en vigueur.
        if revision.ancien_montant is not None and revision.ancien_montant != budget.montant:
            raise DRFValidationError(
                f"Le budget a changé depuis la préparation de {revision.code} "
                f"({revision.ancien_montant} → {budget.montant}) : préparez une nouvelle révision."
            )
        if not _apposer_visa(revision, request):
            return Response(self.get_serializer(revision).data)
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

    permission_classes = [can_read_module("controle_gestion")]

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