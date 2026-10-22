from rest_framework import serializers

from .models import JournalAcces, ParametreTransverse, User
from .rbac import modules_for_role


class UserSerializer(serializers.ModelSerializer):
    """Profil utilisateur exposé via l'API."""

    modules = serializers.SerializerMethodField()
    mfa_requise = serializers.SerializerMethodField()
    site_etsl_code = serializers.CharField(source="site_etsl.code", read_only=True, default=None)

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "role", "is_active", "modules", "mfa_active", "mfa_requise",
            "doit_changer_mdp", "site_etsl", "site_etsl_code",
        ]
        read_only_fields = [
            "id", "email", "role", "is_active", "modules", "mfa_active", "mfa_requise", "doit_changer_mdp", "site_etsl",
        ]

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


class AdminUserSerializer(UserSerializer):
    """Édition d'un compte par l'administrateur (EX-G-01) : nom, rôle, activation. L'email reste l'identifiant."""

    role_label = serializers.CharField(source="get_role_display", read_only=True)

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ["role_label", "last_login", "created_at"]
        read_only_fields = [
            "id", "email", "modules", "mfa_active", "mfa_requise", "role_label", "last_login", "created_at", "doit_changer_mdp",
        ]

    def validate(self, attrs):
        request = self.context.get("request")
        if request and self.instance is not None and self.instance.pk == request.user.pk:
            if attrs.get("is_active") is False:
                raise serializers.ValidationError({"is_active": "Vous ne pouvez pas désactiver votre propre compte."})
            if "role" in attrs and attrs["role"] != self.instance.role:
                raise serializers.ValidationError({"role": "Vous ne pouvez pas modifier votre propre rôle."})
        return attrs


class ParametreTransverseSerializer(serializers.ModelSerializer):
    est_provisoire = serializers.BooleanField(read_only=True)
    confirme_par_email = serializers.CharField(source="confirme_par.email", read_only=True, default=None)

    class Meta:
        model = ParametreTransverse
        fields = [
            "id", "code", "label", "valeur", "texte", "unite", "statut_valeur", "est_provisoire",
            "confirme_par", "confirme_par_email", "confirme_le",
        ]
        read_only_fields = [
            "id", "code", "label", "unite", "statut_valeur", "est_provisoire", "confirme_par", "confirme_par_email",
            "confirme_le",
        ]
