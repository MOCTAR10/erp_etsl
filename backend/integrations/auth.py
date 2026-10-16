"""Authentification des clients d'API externes par jeton (`Authorization: Api-Key <clé>`).

Volontairement SÉPARÉE de l'authentification des utilisateurs : elle n'est branchée que sur les vues
`/api/integrations/gr/*` (jamais dans `DEFAULT_AUTHENTICATION_CLASSES`) → une clé d'API ne donne accès à
aucun autre endpoint de l'ERP.
"""

import hmac

from django.utils import timezone
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.permissions import BasePermission

from .models import ApiClient


class ApiClientPrincipal:
    """Identité d'un client d'API (ce n'est pas un utilisateur Django)."""

    is_authenticated = True
    is_anonymous = False
    is_staff = False
    is_superuser = False
    is_active = True
    role = "api_client"

    def __init__(self, client):
        self.api_client = client
        self.pk = client.pk  # séparé par client pour la limitation de débit
        self.id = client.pk

    def __str__(self):
        return f"api:{self.api_client.name}"


class ApiKeyAuthentication(BaseAuthentication):
    keyword = b"api-key"

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if len(parts) != 2 or parts[0].lower() != self.keyword:
            return None
        try:
            key = parts[1].decode()
        except UnicodeError:
            raise exceptions.AuthenticationFailed("Clé d'API invalide.")
        if not key.startswith(ApiClient.KEY_PREFIX):
            raise exceptions.AuthenticationFailed("Clé d'API invalide.")
        digest = ApiClient.hash_key(key)
        client = ApiClient.objects.filter(key_prefix=key[:12]).filter(is_active=True).first()
        # comparaison à temps constant ; message identique quel que soit l'échec (pas d'oracle)
        if client is None or not hmac.compare_digest(client.key_hash, digest):
            raise exceptions.AuthenticationFailed("Clé d'API invalide.")
        ApiClient.objects.filter(pk=client.pk).update(last_used_at=timezone.now())
        return ApiClientPrincipal(client), client

    def authenticate_header(self, request):
        return "Api-Key"


class HasApiScope(BasePermission):
    """Exige le scope `view.required_scope` (ou `required_scopes[method]`) sur le client d'API."""

    message = "Droit (scope) insuffisant pour cette opération."

    def has_permission(self, request, view):
        client = getattr(request.user, "api_client", None)
        if client is None:
            return False
        scopes = getattr(view, "required_scopes", None)
        scope = scopes.get(request.method) if scopes else getattr(view, "required_scope", None)
        return bool(scope) and client.has_scope(scope)
