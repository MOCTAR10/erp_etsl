from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AptitudeMedicaleViewSet,
    ParametreHseViewSet,
    PersonnelHseViewSet,
    ActionHseViewSet,
    AuditHseViewSet,
    BordereauDechetViewSet,
    ConstatAuditViewSet,
    DuerViewSet,
    EpiViewSet,
    EquipementAtexViewSet,
    EvaluationRisqueViewSet,
    ExerciceUrgenceViewSet,
    ExigenceHabilitationViewSet,
    FormationSecuriteViewSet,
    IncidentViewSet,
    PermisTravailViewSet,
    PlanUrgenceViewSet,
)

router = DefaultRouter()
router.register("permis", PermisTravailViewSet, basename="permis")
router.register("incidents", IncidentViewSet, basename="incidents")
router.register("evaluations-risques", EvaluationRisqueViewSet, basename="evaluations-risques")
router.register("equipements-atex", EquipementAtexViewSet, basename="equipements-atex")
router.register("actions", ActionHseViewSet, basename="actions")
router.register("formations", FormationSecuriteViewSet, basename="formations")
router.register("epis", EpiViewSet, basename="epis")
router.register("bordereaux-dechets", BordereauDechetViewSet, basename="bordereaux-dechets")
router.register("exigences-habilitation", ExigenceHabilitationViewSet, basename="exigences-habilitation")
router.register("audits", AuditHseViewSet, basename="audits")
router.register("constats-audit", ConstatAuditViewSet, basename="constats-audit")
router.register("duer", DuerViewSet, basename="duer")
router.register("plans-urgence", PlanUrgenceViewSet, basename="plans-urgence")
router.register("exercices-urgence", ExerciceUrgenceViewSet, basename="exercices-urgence")

router.register("aptitudes", AptitudeMedicaleViewSet, basename="hse-aptitudes")
router.register("personnel", PersonnelHseViewSet, basename="hse-personnel")
router.register("parametres", ParametreHseViewSet, basename="hse-parametres")

urlpatterns = [
    path("", include(router.urls)),
]