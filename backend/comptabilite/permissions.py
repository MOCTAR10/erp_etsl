from rest_framework.permissions import BasePermission

from users.models import User


class IsComptaAdmin(BasePermission):
    """Écriture des référentiels TVA / comptes : cercle restreint (RF-33)."""

    message = "Rôle non autorisé à modifier les taux de TVA."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        from .services import is_admin_or_staff

        return is_admin_or_staff(user) or user.role in (
            User.Role.FINANCE,
            User.Role.COMPTABLE,
            User.Role.DIRECTION,
        )