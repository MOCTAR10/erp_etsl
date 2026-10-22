from django.db import transaction
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAuthenticated
from rest_framework.response import Response

from config.filtres_vues import FiltresMulticriteresMixin

from users.permissions import IsAdminOrStaff

from .models import (
    Account,
    AnalyticAccount,
    AnalyticAxis,
    Annexe,
    Article,
    Currency,
    Partner,
    Site,
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
    SiteSerializer,
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
    search_fields = ("code", "label",)

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
    search_fields = ("code", "name", "tax_id",)

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
    search_fields = ("code", "label",)

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
    search_fields = ("code", "label",)

    def get_queryset(self):
        qs = AnalyticAxis.objects.all()
        axis_type = self.request.query_params.get("axis_type")
        if axis_type:
            qs = qs.filter(axis_type=axis_type)
        return qs


class AnalyticAccountViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    serializer_class = AnalyticAccountSerializer
    search_fields = ("code", "label",)

    def get_queryset(self):
        qs = AnalyticAccount.objects.select_related("axis").all()
        axis = self.request.query_params.get("axis")
        if axis:
            qs = qs.filter(axis_id=axis)
        return qs


class CanEditerSites(BasePermission):
    message = "Sites ETSL : modification réservée à l'administrateur et à la Direction Générale."

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        from users.parametres import peut_editer

        return peut_editer(request.user)


class SiteViewSet(FiltresMulticriteresMixin, viewsets.ModelViewSet):
    """Sites ETSL (EX-G-03) : liste provisoire paramétrable ; lecture pour tout compte, modification par admin / PDG /
    DGA. Pas de suppression (un site rattaché se désactive) ; une modification repasse le site en provisoire."""

    serializer_class = SiteSerializer
    permission_classes = [IsAuthenticated, CanEditerSites]
    http_method_names = ["get", "post", "patch", "head", "options"]
    search_fields = ("code", "libelle", "ville")
    champs_filtrables = ("type_site", "actif")

    def get_queryset(self):
        return Site.objects.select_related("confirme_par")

    def perform_update(self, serializer):
        serializer.save(statut_valeur=Site.StatutValeur.PROVISOIRE, confirme_par=None, confirme_le=None)

    @extend_schema(request=None, responses=SiteSerializer)
    @action(detail=True, methods=["post"])
    def confirmer(self, request, pk=None):
        with transaction.atomic():
            site = Site.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
            site.statut_valeur = Site.StatutValeur.CONFIRME
            site.confirme_par, site.confirme_le = request.user, timezone.now()
            site.save(update_fields=["statut_valeur", "confirme_par", "confirme_le"])
        return Response(self.get_serializer(site).data)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def repartition(self, request):
        """Ressources rattachées par site (dépôts, équipements, actifs, salariés, affaires, OF, comptes)."""
        from .sites import CODE_RESTRICTION, repartition, restriction_active

        data = repartition()
        data["restriction"] = {"code": CODE_RESTRICTION, "active": restriction_active()}
        return Response(data)

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def rattacher(self, request):
        """Rattache les fiches non rattachées dont le texte libre « site » contient un mot-clé d'un site actif."""
        from .sites import rattacher_tout

        return Response({"rattaches": rattacher_tout()})
