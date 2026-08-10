import hashlib

from rest_framework import serializers

from .models import Document, DocumentType, Dossier, Version

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # RF-03 : upload max 10 Mo


def compute_sha256(uploaded_file):
    """Empreinte SHA-256 du fichier (RF-67), en lecture par blocs."""
    digest = hashlib.sha256()
    uploaded_file.seek(0)
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    uploaded_file.seek(0)
    return digest.hexdigest()


class DocumentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentType
        fields = ["id", "code", "label", "retention_years", "is_restricted_rh"]


class DossierSerializer(serializers.ModelSerializer):
    path = serializers.CharField(read_only=True)
    children_count = serializers.IntegerField(source="children.count", read_only=True)

    class Meta:
        model = Dossier
        fields = [
            "id",
            "name",
            "parent",
            "path",
            "children_count",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class VersionSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = Version
        fields = [
            "id",
            "number",
            "url",
            "sha256",
            "size",
            "original_filename",
            "note",
            "created_at",
        ]
        read_only_fields = ["id", "number", "url", "sha256", "size", "created_at"]

    def get_url(self, obj):
        return obj.file.url


class DocumentSerializer(serializers.ModelSerializer):
    """Création d'un document avec upload du fichier initial (nouvelle Version v1)."""

    file = serializers.FileField(write_only=True, required=True)
    sha256 = serializers.CharField(read_only=True)
    current_version = VersionSerializer(read_only=True)
    created_by_email = serializers.CharField(source="created_by.email", read_only=True)

    class Meta:
        model = Document
        fields = [
            "id",
            "title",
            "status",
            "dossier",
            "type",
            "document_date",
            "counterparty",
            "project",
            "reference",
            "amount",
            "keywords",
            "sha256",
            "current_version",
            "is_checked_out",
            "checked_out_by",
            "created_by_email",
            "created_at",
            "updated_at",
            "file",
        ]
        read_only_fields = [
            "id",
            "status",
            "sha256",
            "current_version",
            "is_checked_out",
            "checked_out_by",
            "created_by_email",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {"dossier": {"required": False}, "type": {"required": False}}

    def validate_file(self, value):
        if value.size > MAX_UPLOAD_SIZE:
            raise serializers.ValidationError(
                f"Fichier trop volumineux (max {MAX_UPLOAD_SIZE // 1024 // 1024} Mo, RF-03)."
            )
        return value

    def create(self, validated_data):
        uploaded = validated_data.pop("file")
        sha256 = compute_sha256(uploaded)
        user = self.context["request"].user

        document = Document.objects.create(
            **validated_data,
            created_by=user,
            sha256=sha256,
        )
        version = Version.objects.create(
            document=document,
            number=1,
            file=uploaded,
            sha256=sha256,
            size=uploaded.size,
            original_filename=uploaded.name,
            created_by=user,
        )
        document.current_version = version
        document.save(update_fields=["current_version"])
        return document


class NewVersionSerializer(serializers.Serializer):
    """Ajout d'une nouvelle version (RF-42) — le verrouillage RF-44 doit être respecté."""

    file = serializers.FileField(required=True)
    note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_file(self, value):
        if value.size > MAX_UPLOAD_SIZE:
            raise serializers.ValidationError(
                f"Fichier trop volumineux (max {MAX_UPLOAD_SIZE // 1024 // 1024} Mo, RF-03)."
            )
        return value


class DocumentListSerializer(serializers.ModelSerializer):
    """Vue légère pour les listes (sans le contenu binaire)."""

    type_label = serializers.CharField(source="type.label", read_only=True)
    dossier_path = serializers.CharField(source="dossier.path", read_only=True)

    class Meta:
        model = Document
        fields = [
            "id",
            "title",
            "status",
            "type",
            "type_label",
            "dossier",
            "dossier_path",
            "document_date",
            "counterparty",
            "project",
            "reference",
            "amount",
            "sha256",
            "created_at",
            "updated_at",
        ]
