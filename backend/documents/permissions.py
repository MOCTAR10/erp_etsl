"""Permissions des documents (matrice §3.3, RF-33/57/58)."""

from rest_framework.permissions import BasePermission

from users.models import User

WRITE_ROLES = (User.Role.ADMIN, User.Role.CHEF_SERVICE, User.Role.COMPTABLE)


class DocumentPermission(BasePermission):
    """
    Lecture : tout utilisateur authentifié.
    Écriture : admin / chef de service / compta (matrice §3.3), ou le créateur du document.
    Les droits fins par document / dossier (ACL) et la règle paie→RH arrivent avec
    le module Sécurité (RF-57/58/33).
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return user.role in WRITE_ROLES or user.is_staff

    def has_object_permission(self, request, view, obj):
        user = request.user
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return user.role in WRITE_ROLES or user.is_staff or obj.created_by_id == user.id


class DossierPermission(BasePermission):
    """Les dossiers suivent la même règle que les documents."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return user.role in WRITE_ROLES or user.is_staff

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)
