from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AffectationParcViewSet,
    ArchiveCompteurGRViewSet,
    AuditEquipementViewSet,
    HistoriqueEquipementViewSet,
    LigneLocationGRViewSet,
    ReceptionBLGRViewSet,
    ReleveCompteurParcViewSet,
    DemandeMobilisationViewSet,
    EquipementParcViewSet,
    LectureCompteurViewSet,
    LocationGRViewSet,
    ParametreLogistiqueViewSet,
    TarifGRViewSet,
)

router = DefaultRouter()
router.register("equipements", EquipementParcViewSet, basename="equipementparc")
router.register("demandes", DemandeMobilisationViewSet, basename="demandemobilisation")
router.register("affectations", AffectationParcViewSet, basename="affectationparc")
router.register("locations", LocationGRViewSet, basename="locationgr")
router.register("lectures", LectureCompteurViewSet, basename="lecturecompteur")
router.register("parametres", ParametreLogistiqueViewSet, basename="parametrelogistique")
router.register("tarifs-gr", TarifGRViewSet, basename="tarifgr")
router.register("releves-parc", ReleveCompteurParcViewSet, basename="relevecompteurparc")
router.register("historique-equipements", HistoriqueEquipementViewSet, basename="historiqueequipement")
router.register("audits", AuditEquipementViewSet, basename="auditequipement")
router.register("lignes-gr", LigneLocationGRViewSet, basename="lignelocationgr")
router.register("receptions-bl", ReceptionBLGRViewSet, basename="receptionblgr")
router.register("archives-gr", ArchiveCompteurGRViewSet, basename="archivecompteurgr")

urlpatterns = [
    path("", include(router.urls)),
]