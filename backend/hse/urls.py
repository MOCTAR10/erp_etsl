from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ConsommationEnvironnementViewSet,
    PlanReductionImpactViewSet,
    RevueDirectionHseViewSet,
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

from .views_ecarts import (
    FicheSecuriteViewSet,
    ListeHseViewSet,
    ModeleChecklistHseViewSet,
    PlanPreventionViewSet,
    PrestataireDechetViewSet,
    ReponseChecklistHseViewSet,
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
router.register("consommations", ConsommationEnvironnementViewSet, basename="hse-consommations")
router.register("plans-reduction", PlanReductionImpactViewSet, basename="hse-plans-reduction")
router.register("revues-direction", RevueDirectionHseViewSet, basename="hse-revues-direction")

# Écarts M7 (lot ecarts-m6m7)
router.register("listes", ListeHseViewSet, basename="hse-listes")
router.register("modeles-checklist", ModeleChecklistHseViewSet, basename="hse-modeles-checklist")
router.register("reponses-checklist", ReponseChecklistHseViewSet, basename="hse-reponses-checklist")
router.register("plans-prevention", PlanPreventionViewSet, basename="hse-plans-prevention")
router.register("prestataires-dechets", PrestataireDechetViewSet, basename="hse-prestataires-dechets")
router.register("fiches-securite", FicheSecuriteViewSet, basename="hse-fiches-securite")

urlpatterns = [
    path("", include(router.urls)),
]