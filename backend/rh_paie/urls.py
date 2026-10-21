from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    MesBulletinsView,
    MesCongesView,
    MonBulletinView,
    MonCongeAnnulerView,
    MonProfilView,
    BaremeCotisationViewSet,
    BaremeImpotViewSet,
    CompteEmetteurViewSet,
    DeclarationSocialeViewSet,
    ReportingRhView,
    MonBulletinPdfView,
    OrdreVirementViewSet,
    HistoriqueBaremeViewSet,
    ParametrePaieViewSet,
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

from .views_m9a import (  # noqa: E402
    AbsenceViewSet, EcheanceDeclarationViewSet, ElementFixeViewSet, EvenementCarriereViewSet, GrilleSalaireViewSet,
)

router = DefaultRouter()
router.register("grilles-salaire", GrilleSalaireViewSet, basename="rh-grilles-salaire")
router.register("elements-fixes", ElementFixeViewSet, basename="rh-elements-fixes")
router.register("carriere", EvenementCarriereViewSet, basename="rh-carriere")
router.register("absences", AbsenceViewSet, basename="rh-absences")
router.register("echeances-declarations", EcheanceDeclarationViewSet, basename="rh-echeances-declarations")
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
router.register("baremes", BaremeCotisationViewSet, basename="rh-baremes")
router.register("baremes-impot", BaremeImpotViewSet, basename="rh-baremes-impot")
router.register("comptes-emetteurs", CompteEmetteurViewSet, basename="rh-comptes-emetteurs")
router.register("declarations", DeclarationSocialeViewSet, basename="rh-declarations")
router.register("ordres-virement", OrdreVirementViewSet, basename="rh-ordres-virement")
router.register("parametres-paie", ParametrePaieViewSet, basename="rh-parametres-paie")
router.register("historique-baremes", HistoriqueBaremeViewSet, basename="rh-historique-baremes")

urlpatterns = [
    path("reporting/", ReportingRhView.as_view(), name="rh-reporting"),
    path("mon-espace/profil/", MonProfilView.as_view(), name="mon-profil"),
    path("mon-espace/bulletins/", MesBulletinsView.as_view(), name="mes-bulletins"),
    path("mon-espace/bulletins/<uuid:pk>/", MonBulletinView.as_view(), name="mon-bulletin"),
    path("mon-espace/bulletins/<uuid:pk>/pdf/", MonBulletinPdfView.as_view(), name="mon-bulletin-pdf"),
    path("mon-espace/conges/", MesCongesView.as_view(), name="mes-conges"),
    path("mon-espace/conges/<uuid:pk>/annuler/", MonCongeAnnulerView.as_view(), name="mon-conge-annuler"),
    path("", include(router.urls)),
]