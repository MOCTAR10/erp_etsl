from rest_framework import serializers

from .models import JournalAcces, User
from .rbac import modules_for_role


class UserSerializer(serializers.ModelSerializer):
    """Profil utilisateur exposé via l'API."""

    modules = serializers.SerializerMethodField()
    mfa_requise = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "role", "is_active", "modules", "mfa_active", "mfa_requise"]
        read_only_fields = ["id", "email", "role", "is_active", "modules", "mfa_active", "mfa_requise"]

    def get_mfa_requise(self, obj) -> bool:
        from .mfa import mfa_requise

        return mfa_requise(obj)

    def get_modules(self, obj) -> list[str]:
        """Modules ERP lisibles par l'utilisateur (pilote le menu du SPA)."""
        return list(modules_for_role(obj.role))


class UserCreateSerializer(serializers.ModelSerializer):
    """Création d'un utilisateur (admin uniquement, RF-62)."""

    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "role", "password"]

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class JournalAccesSerializer(serializers.ModelSerializer):
    evenement_label = serializers.CharField(source="get_evenement_display", read_only=True)

    class Meta:
        model = JournalAcces
        fields = ["id", "cree_le", "evenement", "evenement_label", "user", "email", "ip", "user_agent", "chemin", "details"]
        read_only_fields = fields
