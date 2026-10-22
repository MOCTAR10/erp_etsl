from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CritereControleViewSet,
    IndicateursQualiteViewSet,
    ParametreQualiteViewSet,
    PersonnelQualiteViewSet,
    PunchItemViewSet,
    EpreuvePressionViewSet,
    ImageControleViewSet,
    InstrumentMesureViewSet,
    JointSoudeViewSet,
    PointInspectionViewSet,
    ActionCorrectiveViewSet,
    ControleQualiteViewSet,
    NonConformiteViewSet,
    PvControleViewSet,
    QualificationSoudeurViewSet,
    SoudeurViewSet,
    WpsWpqrViewSet,
)

from .views_systeme import (
    AuditQualiteViewSet,
    CompetencesQualiteViewSet,
    ConstatAuditQualiteViewSet,
    DocumentQualiteViewSet,
    ProcessusQualiteViewSet,
    ResponsabiliteQualiteViewSet,
    RevueDirectionQualiteViewSet,
)

from .views_m6m7 import OrganismeAgreeViewSet, WpsRequisViewSet
from .ecarts_a3 import CoutNonQualiteViewSet

router = DefaultRouter()
router.register("soudeurs", SoudeurViewSet, basename="soudeurs")
router.register("qualifications", QualificationSoudeurViewSet, basename="qualifications")
router.register("wps", WpsWpqrViewSet, basename="wps")
router.register("controles", ControleQualiteViewSet, basename="controles")
router.register("points-inspection", PointInspectionViewSet, basename="points-inspection")
router.register("pvs", PvControleViewSet, basename="pvs")
router.register("non-conformites", NonConformiteViewSet, basename="non-conformites")
router.register("actions-correctives", ActionCorrectiveViewSet, basename="actions-correctives")
router.register("instruments", InstrumentMesureViewSet, basename="instruments")
router.register("joints", JointSoudeViewSet, basename="joints")
router.register("images-controle", ImageControleViewSet, basename="images-controle")
router.register("epreuves", EpreuvePressionViewSet, basename="epreuves")
router.register("punch-list", PunchItemViewSet, basename="punch-list")
router.register("criteres", CritereControleViewSet, basename="criteres-controle")
router.register("parametres", ParametreQualiteViewSet, basename="parametres-qualite")
router.register("indicateurs", IndicateursQualiteViewSet, basename="indicateurs-qualite")
router.register("personnel", PersonnelQualiteViewSet, basename="personnel-qualite")
router.register("processus", ProcessusQualiteViewSet, basename="processus-qualite")
router.register("organisation", ResponsabiliteQualiteViewSet, basename="organisation-qualite")
router.register("documents-qualite", DocumentQualiteViewSet, basename="documents-qualite")
router.register("audits", AuditQualiteViewSet, basename="audits-qualite")
router.register("constats-audit", ConstatAuditQualiteViewSet, basename="constats-audit-qualite")
router.register("revues-direction", RevueDirectionQualiteViewSet, basename="revues-direction-qualite")
router.register("competences", CompetencesQualiteViewSet, basename="competences-qualite")

# Écarts M6 (lot ecarts-m6m7)
router.register("organismes-agrees", OrganismeAgreeViewSet, basename="organismes-agrees")
router.register("wps-requis", WpsRequisViewSet, basename="wps-requis")
router.register("couts-non-qualite", CoutNonQualiteViewSet, basename="couts-non-qualite")

urlpatterns = [
    path("", include(router.urls)),
]