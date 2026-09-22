from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    BulletinViewSet,
    ContratViewSet,
    DemandeCongeViewSet,
    EmployeViewSet,
    FormationsViewSet,
    QualificationViewSet,
    RecrutementViewSet,
    RubriqueViewSet,
    SaisieTempsViewSet,
    SanctionViewSet,
)

router = DefaultRouter()
router.register("employes", EmployeViewSet, basename="rh-employes")
router.register("contrats", ContratViewSet, basename="rh-contrats")
router.register("qualifications", QualificationViewSet, basename="rh-qualifications")
router.register("recrutements", RecrutementViewSet, basename="rh-recrutements")
router.register("formations", FormationsViewSet, basename="rh-formations")
router.register("conges", DemandeCongeViewSet, basename="rh-conges")
router.register("sanctions", SanctionViewSet, basename="rh-sanctions")
router.register("temps", SaisieTempsViewSet, basename="rh-temps")
router.register("rubriques", RubriqueViewSet, basename="rh-rubriques")
router.register("bulletins", BulletinViewSet, basename="rh-bulletins")

urlpatterns = [
    path("", include(router.urls)),
]