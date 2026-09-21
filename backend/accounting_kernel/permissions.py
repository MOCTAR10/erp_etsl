from rest_framework.permissions import BasePermission

from users.models import User

# Rôles autorisés à comptabiliser / extourner (M10).
POSTING_ROLES = (
    User.Role.ADMIN,
    User.Role.COMPTABLE,
    User.Role.FINANCE,
    User.Role.DIRECTION,
)


class CanPostAccounting(BasePermission):
    """Comptabilisation / extourne : admin, comptable, finance, direction."""

    message = "Rôle non autorisé à comptabiliser."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return user.is_staff or user.is_superuser or user.role in POSTING_ROLES
