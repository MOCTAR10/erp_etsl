from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CompteBancaireViewSet,
    ControleInterneViewSet,
    DeclarationTvaViewSet,
    ClotureMensuelleViewSet,
    EngagementViewSet,
    FactureClientViewSet,
    ModeleFactureViewSet,
    LettrageViewSet,
    ParametreComptaViewSet,
    PaiementViewSet,
    RapprochementBancaireViewSet,
    ReleveBancaireViewSet,
    TauxTvaViewSet,
    EtatsViewSet,
    PrevisionTresorerieViewSet,
    AutoFactureViewSet,
    GabaritEtatViewSet,
    LocationGrComptaViewSet,
)

router = DefaultRouter()
router.register("taux-tva", TauxTvaViewSet, basename="compta-taux-tva")
router.register("comptes-bancaires", CompteBancaireViewSet, basename="compta-comptes-bancaires")
router.register("releves", ReleveBancaireViewSet, basename="compta-releves")
router.register("rapprochements", RapprochementBancaireViewSet, basename="compta-rapprochements")
router.register("engagements", EngagementViewSet, basename="compta-engagements")
router.register("paiements", PaiementViewSet, basename="compta-paiements")
router.register("declarations-tva", DeclarationTvaViewSet, basename="compta-declarations-tva")
router.register("controles", ControleInterneViewSet, basename="compta-controles")
router.register("lettrages", LettrageViewSet, basename="compta-lettrages")
router.register("parametres", ParametreComptaViewSet, basename="compta-parametres")
router.register("factures-clients", FactureClientViewSet, basename="compta-factures-clients")
router.register("modele-facture", ModeleFactureViewSet, basename="compta-modele-facture")
router.register("clotures-mensuelles", ClotureMensuelleViewSet, basename="compta-clotures-mensuelles")
router.register("etats", EtatsViewSet, basename="compta-etats")
router.register("previsions-tresorerie", PrevisionTresorerieViewSet, basename="compta-previsions-tresorerie")
router.register("autofactures", AutoFactureViewSet, basename="compta-autofactures")
router.register("gabarits", GabaritEtatViewSet, basename="compta-gabarits")
router.register("locations-gr", LocationGrComptaViewSet, basename="compta-locations-gr")

urlpatterns = [
    path("", include(router.urls)),
]