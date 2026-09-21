"""Permissions basées sur les rôles ETSL (RF-62)."""

from rest_framework.permissions import BasePermission

from .models import User


class IsRole(BasePermission):
    """Échoue sauf si l'utilisateur a un des rôles attendus (ou est staff)."""

    allowed_roles = ()

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_staff:
            return True
        return user.role in self.allowed_roles


def role_permission(*roles):
    """Fabrique une classe de permission limitée à des rôles donnés."""

    class _RolePermission(IsRole):
        allowed_roles = roles

    _RolePermission.__name__ = "Can" + "".join(r.title().replace("_", "") for r in roles)
    return _RolePermission


IsAdmin = role_permission(User.Role.ADMIN)
IsAdminOrDirection = role_permission(User.Role.ADMIN, User.Role.DIRECTION)


class IsAdminOrStaff(BasePermission):
    """Accès réservé à l'administration (staff ou rôle admin)."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return user.is_staff or user.role == User.Role.ADMIN
