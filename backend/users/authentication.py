"""Authentification JWT de l'API (module léger : chargé par les réglages DRF, sans import de vues)."""

from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.authentication import JWTAuthentication

#: Chemins accessibles tant que le changement de mot de passe imposé n'est pas fait.
CHEMINS_LIBRES = ("/api/users/me/", "/api/users/token/refresh/")


class JWTAuthenticationMdp(JWTAuthentication):
    """JWT + changement de mot de passe imposé : tant qu'il n'est pas fait, seules les routes du profil répondent."""

    def authenticate(self, request):
        resultat = super().authenticate(request)
        if resultat is not None and getattr(resultat[0], "doit_changer_mdp", False):
            chemin = request.path
            if not (chemin in CHEMINS_LIBRES or chemin.startswith("/api/users/me/")):
                raise PermissionDenied("Changement de mot de passe obligatoire avant de continuer.")
        return resultat
