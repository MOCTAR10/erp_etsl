from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    """Profil utilisateur exposé via l'API."""

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "role", "is_active"]
        read_only_fields = ["id", "email", "role", "is_active"]


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
