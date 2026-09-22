"""Vues API M5 — Stocks & Traçabilité matière (RF-ERP-40…43)."""

from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    ArticleStock,
    CertificatMatiere,
    Depot,
    Inventaire,
    InventaireLigne,
    LotMatiere,
    MouvementStock,
    StockQuant,
)
from .serializers import (
    ArticleStockSerializer,
    CertificatMatiereSerializer,
    DepotSerializer,
    InventaireLigneSerializer,
    InventaireSerializer,
    LotMatiereSerializer,
    MouvementStockSerializer,
    StockQuantSerializer,
    TraceabiliteEntrySerializer,
    ValorisationEntrySerializer,
)
from .services import (
    CanManageStocks,
    apply_move,
    can_see_amount,
    cloturer_inventaire,
    traceabilite,
    valuation,
)


class DepotViewSet(viewsets.ModelViewSet):
    queryset = Depot.objects.select_related("responsable").all()
    serializer_class = DepotSerializer
    permission_classes = [CanManageStocks]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("active") == "1":
            qs = qs.filter(is_active=True)
        return qs


class LotMatiereViewSet(viewsets.ModelViewSet):
    queryset = LotMatiere.objects.select_related("article").all()
    serializer_class = LotMatiereSerializer
    permission_classes = [CanManageStocks]

    def get_queryset(self):
        qs = super().get_queryset()
        if article := self.request.query_params.get("article"):
            qs = qs.filter(article_id=article)
        if statut := self.request.query_params.get("statut"):
            qs = qs.filter(statut=statut)
        return qs


class CertificatMatiereViewSet(viewsets.ModelViewSet):
    queryset = CertificatMatiere.objects.select_related("lot", "lot__article", "fournisseur").all()
    serializer_class = CertificatMatiereSerializer
    permission_classes = [CanManageStocks]

    def get_queryset(self):
        qs = super().get_queryset()
        if lot := self.request.query_params.get("lot"):
            qs = qs.filter(lot_id=lot)
        return qs


class MouvementStockViewSet(viewsets.ModelViewSet):
    queryset = MouvementStock.objects.select_related(
        "article", "source", "destination", "lot", "ordre", "devise", "created_by"
    ).all()
    serializer_class = MouvementStockSerializer
    permission_classes = [CanManageStocks]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if article := params.get("article"):
            qs = qs.filter(article_id=article)
        if lot := params.get("lot"):
            qs = qs.filter(lot_id=lot)
        if depot := params.get("depot"):
            qs = qs.filter(source_id=depot) | qs.filter(destination_id=depot)
        if type_mouvement := params.get("type"):
            qs = qs.filter(type_mouvement=type_mouvement)
        return qs.distinct()

    @transaction.atomic
    def perform_create(self, serializer):
        mouvement = serializer.save(created_by=self.request.user)
        try:
            apply_move(mouvement)
        except ValueError as exc:
            from django.db import transaction as t

            t.set_rollback(True)
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"detail": str(exc)})

    @action(detail=False, methods=["get"], url_path="tracabilite")
    def traceabilite(self, request):
        article = request.query_params.get("article")
        lot = request.query_params.get("lot")
        if not (article or lot):
            return Response(
                {"detail": "Paramètre `article` ou `lot` requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        rows = traceabilite(article_id=article, lot_id=lot)
        return Response(TraceabiliteEntrySerializer(rows, many=True).data)


class StockQuantViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = StockQuant.objects.select_related("depot", "article", "lot").all()
    serializer_class = StockQuantSerializer
    permission_classes = [CanManageStocks]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if depot := params.get("depot"):
            qs = qs.filter(depot_id=depot)
        if article := params.get("article"):
            qs = qs.filter(article_id=article)
        if lot := params.get("lot"):
            qs = qs.filter(lot_id=lot)
        if params.get("positive") == "1":
            qs = qs.filter(quantity__gt=0)
        return qs

    @action(detail=False, methods=["get"], url_path="valorisation")
    def valorisation(self, request):
        rows = valuation(depot_id=request.query_params.get("depot"))
        return Response(ValorisationEntrySerializer(rows, many=True).data)


class InventaireViewSet(viewsets.ModelViewSet):
    queryset = Inventaire.objects.select_related(
        "depot", "responsable", "created_by"
    ).prefetch_related("lignes__article", "lignes__lot").all()
    serializer_class = InventaireSerializer
    permission_classes = [CanManageStocks]

    def get_queryset(self):
        qs = super().get_queryset()
        if depot := self.request.query_params.get("depot"):
            qs = qs.filter(depot_id=depot)
        if statut := self.request.query_params.get("statut"):
            qs = qs.filter(statut=statut)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"], url_path="cloturer")
    def cloturer(self, request, pk=None):
        inventaire = self.get_object()
        try:
            inventaire = cloturer_inventaire(inventaire, request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(inventaire).data)


class InventaireLigneViewSet(viewsets.ModelViewSet):
    queryset = InventaireLigne.objects.select_related("inventaire", "article", "lot").all()
    serializer_class = InventaireLigneSerializer
    permission_classes = [CanManageStocks]

    def get_queryset(self):
        qs = super().get_queryset()
        if inventaire := self.request.query_params.get("inventaire"):
            qs = qs.filter(inventaire_id=inventaire)
        return qs


class ArticleStockViewSet(viewsets.ModelViewSet):
    queryset = ArticleStock.objects.select_related("article").all()
    serializer_class = ArticleStockSerializer
    permission_classes = [CanManageStocks]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("active") == "1":
            qs = qs.filter(is_active=True)
        return qs