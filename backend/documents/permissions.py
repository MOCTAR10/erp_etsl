"""Permissions des documents (matrice §3.3, RF-33/57/58)."""

from rest_framework.permissions import BasePermission

from users.permissions import IsAdminOrStaff  # noqa: F401  (ré-export historique)

from .services import (  # noqa: F401  (WRITE_ROLES ré-exporté)
    WRITE_ROLES,
    can_manage_acl,
    can_read_document,
    can_write_document,
    can_write_dossier,
)


class DocumentPermission(BasePermission):
    """
    Lecture / écriture résolues via la matrice des rôles, la règle paie→RH
    (RF-33) et les ACL document / dossier (RF-57/58).
    La matrice des rôles pour la création est vérifiée dans perform_create
    (l'ACL "write" peut ouvrir l'écriture sur un objet existant, ex. Direction).
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return can_read_document(user, obj)
        return can_write_document(user, obj)


class DossierPermission(BasePermission):
    """Les dossiers suivent la matrice des rôles + ACL héritée (RF-58)."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return can_write_dossier(user, obj)


class CanManageACL(BasePermission):
    """Gestion des ACL : admin / staff ou créateur de l'objet."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        return can_manage_acl(request.user, document=getattr(obj, "document", None), dossier=getattr(obj, "dossier", None))
