from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    JournalAccesViewSet,
    MeView,
    MfaEnrolementView,
    MfaVerificationView,
    ThrottledTokenObtainPairView,
    UserViewSet,
)

router = DefaultRouter()
router.register("users", UserViewSet, basename="users")
router.register("journal-acces", JournalAccesViewSet, basename="journal-acces")

urlpatterns = [
    path("token/", ThrottledTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("mfa/enrolement/", MfaEnrolementView.as_view(), name="mfa_enrolement"),
    path("mfa/verification/", MfaVerificationView.as_view(), name="mfa_verification"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("me/", MeView.as_view(), name="me"),
    path("", include(router.urls)),
    path("", include("rest_framework.urls")),
]
