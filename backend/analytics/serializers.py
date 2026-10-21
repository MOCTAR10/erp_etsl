from rest_framework import serializers

from . import cubes
from .models import CubeArchive, ParametreCube, ScelleMart


class CubeArchiveSerializer(serializers.ModelSerializer):
    integre = serializers.SerializerMethodField()

    def get_integre(self, obj):
        return cubes.verifier_archive(obj)

    class Meta:
        model = CubeArchive
        fields = [
            "id", "periode", "faits", "nb_faits", "produits", "charges", "cout_gr", "sha256",
            "conserve_jusqu_au", "retention_provisoire", "integre", "document", "created_by", "created_at",
        ]
        read_only_fields = fields


class ParametreCubeSerializer(serializers.ModelSerializer):
    est_provisoire = serializers.BooleanField(read_only=True)

    class Meta:
        model = ParametreCube
        fields = [
            "id", "code", "label", "valeur", "unite", "statut_valeur", "est_provisoire",
            "confirme_par", "confirme_le",
        ]
        read_only_fields = ["code", "label", "unite", "statut_valeur", "confirme_par", "confirme_le"]

    def validate_valeur(self, value):
        code = getattr(self.instance, "code", None)
        if code in cubes.PARAMETRES_ZERO_AUTORISE:
            if value < 0 or (code == "BLOCAGE_AVANT_CLOTURE" and value not in (0, 1)):
                raise serializers.ValidationError("Valeur attendue : 0 ou une valeur positive (0/1 pour un interrupteur).")
            return value
        if value <= 0:
            raise serializers.ValidationError("La valeur doit être strictement positive.")
        return value

    def update(self, instance, validated_data):
        # Une valeur modifiée redevient provisoire jusqu'à nouvelle confirmation.
        if "valeur" in validated_data and validated_data["valeur"] != instance.valeur:
            instance.statut_valeur = ParametreCube.StatutValeur.PROVISOIRE
            instance.confirme_par = None
            instance.confirme_le = None
        return super().update(instance, validated_data)


class ScelleMartSerializer(serializers.ModelSerializer):
    integre = serializers.SerializerMethodField()

    def get_integre(self, obj):
        from .pilotage import verifier_scelle

        return verifier_scelle(obj)

    class Meta:
        model = ScelleMart
        fields = [
            "id", "mart", "type_donnees", "source", "nb_lignes", "sha256", "conserve_jusqu_au", "integre",
            "created_by", "created_at",
        ]
        read_only_fields = fields
