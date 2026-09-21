"""API du noyau comptable (M10/M9/M5) — écritures, journaux, périodes, extournes."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.permissions import IsAdminOrStaff

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
from .services import close_period, post_move, reopen_period, reverse_move


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

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        period = close_period(self.get_object())
        return Response(self.get_serializer(period).data)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        period = reopen_period(self.get_object())
        return Response(self.get_serializer(period).data)


class JournalViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    serializer_class = JournalSerializer

    def get_queryset(self):
        qs = Journal.objects.all()
        journal_type = self.request.query_params.get("journal_type")
        if journal_type:
            qs = qs.filter(journal_type=journal_type)
        return qs


class SequenceViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = Sequence.objects.select_related("journal").all()
    serializer_class = SequenceSerializer


class AccountMoveViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    """Écritures comptables : brouillon → comptabilisée (immuable) → extournée."""

    serializer_class = AccountMoveSerializer

    def get_permissions(self):
        if self.action in ("post", "reverse"):
            return [CanPostAccounting()]
        return [IsAuthenticated()]

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
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def post(self, request, pk=None):
        move = post_move(self.get_object(), user=request.user)
        return Response(self.get_serializer(move).data)

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        move = reverse_move(
            self.get_object(),
            user=request.user,
            date=request.data.get("date"),
            reference=request.data.get("reference", ""),
            label=request.data.get("label", ""),
        )
        return Response(self.get_serializer(move).data, status=status.HTTP_201_CREATED)


class AccountMoveLineViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    serializer_class = AccountMoveLineSerializer

    def get_queryset(self):
        qs = AccountMoveLine.objects.select_related("account", "move").all()
        move = self.request.query_params.get("move")
        if move:
            qs = qs.filter(move_id=move)
        return qs
