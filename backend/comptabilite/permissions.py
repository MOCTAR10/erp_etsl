from rest_framework.permissions import BasePermission

from users.models import User


#: Confirmation des paramètres provisoires M10 (paramètres, modèle de facture, gabarits d'états) : DAF (Finance) et
#: Direction ; le comptable modifie mais ne confirme pas.
COMPTA_PARAM_CONFIRM_ROLES = (User.Role.ADMIN, User.Role.PDG, User.Role.DGA, User.Role.FINANCE, User.Role.DIRECTION)


class CanConfirmerParametreCompta(BasePermission):
    message = "Confirmation des paramètres comptables réservée au DAF (Finance) et à la Direction."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        from .services import is_admin_or_staff

        return is_admin_or_staff(user) or user.role in COMPTA_PARAM_CONFIRM_ROLES


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