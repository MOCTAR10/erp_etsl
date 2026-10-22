from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    JournalAccesViewSet,
    MeView,
    MfaEnrolementView,
    MfaVerificationView,
    RolesView,
    ThrottledTokenObtainPairView,
    UserViewSet,
)
from .motdepasse import ChangerMotDePasseView, ConfigMotDePasseView, MotDePasseOublieView, ReinitialiserMotDePasseView
from .parametres import ParametreTransverseViewSet

router = DefaultRouter()
router.register("users", UserViewSet, basename="users")
router.register("journal-acces", JournalAccesViewSet, basename="journal-acces")
router.register("parametres", ParametreTransverseViewSet, basename="parametres-transverses")

urlpatterns = [
    path("token/", ThrottledTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("mfa/enrolement/", MfaEnrolementView.as_view(), name="mfa_enrolement"),
    path("mfa/verification/", MfaVerificationView.as_view(), name="mfa_verification"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("me/", MeView.as_view(), name="me"),
    path("roles/", RolesView.as_view(), name="roles"),
    path("me/mot-de-passe/", ChangerMotDePasseView.as_view(), name="mot_de_passe_changer"),
    path("mot-de-passe/config/", ConfigMotDePasseView.as_view(), name="mot_de_passe_config"),
    path("mot-de-passe/oubli/", MotDePasseOublieView.as_view(), name="mot_de_passe_oubli"),
    path("mot-de-passe/reinitialiser/", ReinitialiserMotDePasseView.as_view(), name="mot_de_passe_reinitialiser"),
    path("", include(router.urls)),
    path("", include("rest_framework.urls")),
]
