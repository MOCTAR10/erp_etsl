"""API du noyau comptable (M10/M9/M5) — écritures, journaux, périodes, extournes."""

from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from config.inputs import date_input
from users.permissions import IsAdminOrStaff, can_read_module

from .models import AccountMove, AccountMoveLine, FiscalYear, Journal, Period, Sequence
from .permissions import CanPostAccounting
from .serializers import (
    AccountMoveLineSerializer,
    AccountMoveSerializer,
    FiscalYearSerializer,
    JournalSerializer,
    PeriodSerializer,
    SequenceSerializer,
)
from .services import post_move, reverse_move


class DjangoValidationMixin:
    """Convertit les `ValidationError` Django (immuabilité…) en réponses HTTP 400."""

    def handle_exception(self, exc):
        if isinstance(exc, DjangoValidationError):
            exc = DRFValidationError(getattr(exc, "messages", [str(exc)]))
        return super().handle_exception(exc)


class AdminWriteMixin(DjangoValidationMixin):
    http_method_names = ["get", "post", "patch", "delete"]

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAuthenticated()]
        return [IsAdminOrStaff()]


class FiscalYearViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = FiscalYear.objects.prefetch_related("periods").all()
    serializer_class = FiscalYearSerializer

    def destroy(self, request, *args, **kwargs):
        # Conservation des écritures (10 ans) : un exercice portant des écritures comptabilisées ne se supprime pas.
        fy = self.get_object()
        if AccountMove.objects.filter(period__fiscal_year=fy).exclude(status=AccountMove.Status.DRAFT).exists():
            raise DRFValidationError("Exercice portant des écritures comptabilisées : conservation obligatoire, suppression impossible.")
        return super().destroy(request, *args, **kwargs)


class PeriodViewSet(DjangoValidationMixin, viewsets.ReadOnlyModelViewSet):
    """Périodes comptables — clôture/réouverture réservées aux admins."""

    serializer_class = PeriodSerializer

    def get_queryset(self):
        qs = Period.objects.select_related("fiscal_year").all()
        year = self.request.query_params.get("year")
        state = self.request.query_params.get("status")
        if year:
            qs = qs.filter(fiscal_year__year=year)
        if state:
            qs = qs.filter(status=state)
        return qs

    def get_permissions(self):
        if self.action in ("close", "reopen"):
            return [IsAdminOrStaff()]
        return [IsAuthenticated()]

    MESSAGE_CLOTURE = (
        "Clôture et réouverture d'une période : passez par Comptabilité → Clôture mensuelle "
        "(contrôles, chrono < 2 h, synthèse Direction) — /api/comptabilite/clotures-mensuelles/."
    )

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        # Clôture directe interdite : elle contournait les contrôles et le chrono de la clôture mensuelle M10.
        self.get_object()
        raise DRFValidationError(self.MESSAGE_CLOTURE)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        self.get_object()
        raise DRFValidationError(self.MESSAGE_CLOTURE)


class JournalViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    serializer_class = JournalSerializer

    def get_queryset(self):
        qs = Journal.objects.all()
        journal_type = self.request.query_params.get("journal_type")
        if journal_type:
            qs = qs.filter(journal_type=journal_type)
        return qs


class SequenceViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = Sequence.objects.select_related("journal").order_by("pk")
    serializer_class = SequenceSerializer


class AccountMoveViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    """Écritures comptables : brouillon → comptabilisée (immuable) → extournée."""

    serializer_class = AccountMoveSerializer
    search_fields = ("number", "reference", "label",)

    def get_permissions(self):
        # Grand livre = données financières sensibles (dont journal de paie) :
        # lecture = lecteurs du module M10 ; écriture/comptabilisation = cercle comptable.
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [can_read_module("comptabilite")()]
        return [CanPostAccounting()]

    def get_queryset(self):
        qs = AccountMove.objects.select_related("journal", "period").prefetch_related(
            "lines__account"
        )
        journal = self.request.query_params.get("journal")
        move_status = self.request.query_params.get("status")
        period = self.request.query_params.get("period")
        source = self.request.query_params.get("source")
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")
        if journal:
            qs = qs.filter(journal_id=journal)
        if move_status:
            qs = qs.filter(status=move_status)
        if period:
            qs = qs.filter(period_id=period)
        if source:
            qs = qs.filter(source=source)
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, source=AccountMove.SOURCE_MANUELLE, source_ref="")

    @action(detail=False, methods=["get"], url_path="taux-saisie-manuelle")
    def taux_saisie_manuelle(self, request):
        """Part des écritures comptabilisées saisies à la main (RG-M10.01 : 95 % issues des modules)."""
        exercice = request.query_params.get("exercice") or str(timezone.localdate().year)
        if not exercice.isdigit():
            raise DRFValidationError({"exercice": "Année attendue."})
        posted = AccountMove.objects.filter(
            period__fiscal_year__year=int(exercice),
            status__in=[AccountMove.Status.POSTED, AccountMove.Status.REVERSED],
        )
        total = posted.count()
        manuelles = posted.filter(source=AccountMove.SOURCE_MANUELLE).count()
        taux = (Decimal(manuelles) * 100 / total).quantize(Decimal("0.01")) if total else Decimal("0.00")
        return Response({
            "exercice": int(exercice), "total": total, "manuelles": manuelles,
            "taux": str(taux), "seuil": "5.00", "alerte": taux > 5,
        })

    @action(detail=True, methods=["post"])
    def post(self, request, pk=None):
        move = post_move(self.get_object(), user=request.user)
        return Response(self.get_serializer(move).data)

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        move = reverse_move(
            self.get_object(),
            user=request.user,
            date=date_input(request.data.get("date"), "date"),
            reference=request.data.get("reference", ""),
            label=request.data.get("label", ""),
        )
        return Response(self.get_serializer(move).data, status=status.HTTP_201_CREATED)


class AccountMoveLineViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    serializer_class = AccountMoveLineSerializer

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [can_read_module("comptabilite")()]
        return super().get_permissions()

    def get_queryset(self):
        qs = AccountMoveLine.objects.select_related("account", "move").all()
        move = self.request.query_params.get("move")
        if move:
            qs = qs.filter(move_id=move)
        return qs
