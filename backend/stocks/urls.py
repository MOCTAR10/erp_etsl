from rest_framework.routers import DefaultRouter

from .views import (
    ArticleStockViewSet,
    CertificatMatiereViewSet,
    DepotViewSet,
    InventaireLigneViewSet,
    InventaireViewSet,
    LotMatiereViewSet,
    MouvementStockViewSet,
    StockQuantViewSet,
)

router = DefaultRouter()
router.register("depots", DepotViewSet, basename="stocks-depots")
router.register("lots", LotMatiereViewSet, basename="stocks-lots")
router.register("certificats", CertificatMatiereViewSet, basename="stocks-certificats")
router.register("configs", ArticleStockViewSet, basename="stocks-configs")
router.register("mouvements", MouvementStockViewSet, basename="stocks-mouvements")
router.register("quants", StockQuantViewSet, basename="stocks-quants")
router.register("inventaires", InventaireViewSet, basename="stocks-inventaires")
router.register("inventaire-lignes", InventaireLigneViewSet, basename="stocks-inventaire-lignes")

urlpatterns = router.urls