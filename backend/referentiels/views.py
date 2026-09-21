from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from users.permissions import IsAdminOrStaff

from .models import (
    Account,
    AnalyticAccount,
    AnalyticAxis,
    Annexe,
    Article,
    Currency,
    Partner,
    UnitOfMeasure,
)
from .serializers import (
    AccountSerializer,
    AnalyticAccountSerializer,
    AnalyticAxisSerializer,
    AnnexeSerializer,
    ArticleSerializer,
    CurrencySerializer,
    PartnerSerializer,
    UnitOfMeasureSerializer,
)


class AdminWriteMixin:
    """Lecture pour tout utilisateur authentifié, écriture réservée aux admins."""

    http_method_names = ["get", "post", "patch", "delete"]

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAuthenticated()]
        return [IsAdminOrStaff()]


class AnnexeViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    """Référentiel des 270 annexes du MANUEL — lecture pour tous, écriture admin."""

    queryset = Annexe.objects.all()
    serializer_class = AnnexeSerializer

    def get_queryset(self):
        qs = Annexe.objects.all()
        kind = self.request.query_params.get("kind")
        domain = self.request.query_params.get("domain")
        active = self.request.query_params.get("active")
        if kind:
            qs = qs.filter(kind=kind)
        if domain:
            qs = qs.filter(domain=domain)
        if active is not None:
            qs = qs.filter(is_active=active.lower() in ("1", "true", "yes"))
        return qs


class CurrencyViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = Currency.objects.all()
    serializer_class = CurrencySerializer

    def get_queryset(self):
        qs = Currency.objects.all()
        active = self.request.query_params.get("active")
        if active is not None:
            qs = qs.filter(is_active=active.lower() in ("1", "true", "yes"))
        return qs


class UnitOfMeasureViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = UnitOfMeasure.objects.all()
    serializer_class = UnitOfMeasureSerializer


class AccountViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    """Plan de comptes SYSCOHADA révisée."""

    serializer_class = AccountSerializer

    def get_queryset(self):
        qs = Account.objects.all()
        account_class = self.request.query_params.get("account_class")
        account_type = self.request.query_params.get("account_type")
        active = self.request.query_params.get("active")
        if account_class:
            qs = qs.filter(account_class=account_class)
        if account_type:
            qs = qs.filter(account_type=account_type)
        if active is not None:
            qs = qs.filter(is_active=active.lower() in ("1", "true", "yes"))
        return qs


class PartnerViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    """Tiers unifié (clients, fournisseurs, intra-groupe GR)."""

    serializer_class = PartnerSerializer

    def get_queryset(self):
        qs = Partner.objects.select_related("currency").all()
        kind = self.request.query_params.get("kind")
        active = self.request.query_params.get("active")
        if kind:
            qs = qs.filter(kind=kind)
        if active is not None:
            qs = qs.filter(is_active=active.lower() in ("1", "true", "yes"))
        return qs


class ArticleViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    serializer_class = ArticleSerializer

    def get_queryset(self):
        qs = Article.objects.select_related("unit", "account").all()
        article_type = self.request.query_params.get("article_type")
        stockable = self.request.query_params.get("stockable")
        active = self.request.query_params.get("active")
        if article_type:
            qs = qs.filter(article_type=article_type)
        if stockable is not None:
            qs = qs.filter(is_stockable=stockable.lower() in ("1", "true", "yes"))
        if active is not None:
            qs = qs.filter(is_active=active.lower() in ("1", "true", "yes"))
        return qs


class AnalyticAxisViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    serializer_class = AnalyticAxisSerializer

    def get_queryset(self):
        qs = AnalyticAxis.objects.all()
        axis_type = self.request.query_params.get("axis_type")
        if axis_type:
            qs = qs.filter(axis_type=axis_type)
        return qs


class AnalyticAccountViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    serializer_class = AnalyticAccountSerializer

    def get_queryset(self):
        qs = AnalyticAccount.objects.select_related("axis").all()
        axis = self.request.query_params.get("axis")
        if axis:
            qs = qs.filter(axis_id=axis)
        return qs
