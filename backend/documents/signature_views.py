"""API de signature électronique avancée (CL-OM-06) — demandes, code à usage unique, signature, certificat."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.models import User

from . import signatures
from .audit import log_audit, request_ip
from .models import AuditLog, SignatureRequest, Signer, Version
from .services import can_read_document, can_write_document, is_admin_or_staff


class SignerSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Signer
        fields = ["id", "user", "name", "email", "order", "status", "signed_at", "refusal_reason"]

    def get_name(self, obj):
        return obj.user.get_full_name() or obj.user.email


class SignatureRequestSerializer(serializers.ModelSerializer):
    version = serializers.PrimaryKeyRelatedField(queryset=Version.objects.all())
    signers = serializers.ListField(child=serializers.UUIDField(), write_only=True)
    expires_in_days = serializers.IntegerField(write_only=True, required=False, min_value=1, max_value=90)
    signataires = SignerSerializer(source="signers", many=True, read_only=True)
    document_title = serializers.CharField(source="version.document.title", read_only=True)
    version_number = serializers.IntegerField(source="version.number", read_only=True)
    a_mon_tour = serializers.SerializerMethodField()
    expired = serializers.BooleanField(source="is_expired", read_only=True)

    class Meta:
        model = SignatureRequest
        fields = [
            "id", "version", "version_number", "document_title", "title", "message", "status", "expired",
            "document_sha256", "created_by", "created_at", "expires_at", "completed_at",
            "signers", "expires_in_days", "signataires", "a_mon_tour",
        ]
        read_only_fields = ["id", "status", "document_sha256", "created_by", "created_at", "expires_at", "completed_at"]

    def get_a_mon_tour(self, obj):
        user = self.context["request"].user
        cur = signatures.current_signer(obj) if obj.status == SignatureRequest.Status.PENDING else None
        return bool(cur and cur.user_id == user.id and not obj.is_expired)


def _bad_request(exc: DjangoValidationError):
    return Response({"detail": " ".join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)


class SignatureRequestViewSet(
    mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Visible par l'émetteur, les signataires et les administrateurs uniquement."""

    serializer_class = SignatureRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = SignatureRequest.objects.select_related("version__document", "created_by").prefetch_related(
            "signers__user"
        )
        user = self.request.user
        if not is_admin_or_staff(user):
            qs = qs.filter(Q(created_by=user) | Q(signers__user=user)).distinct()
        if self.request.query_params.get("a_signer") == "1":
            qs = qs.filter(
                status=SignatureRequest.Status.PENDING, signers__user=user, signers__status=Signer.Status.PENDING
            )
        return qs

    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        version = s.validated_data["version"]
        if not can_read_document(request.user, version.document) or not can_write_document(
            request.user, version.document
        ):
            return Response({"detail": "Droit insuffisant sur ce document."}, status=status.HTTP_403_FORBIDDEN)
        users = list(User.objects.filter(pk__in=s.validated_data["signers"]))
        by_id = {str(u.pk): u for u in users}
        ordered = [by_id[str(i)] for i in s.validated_data["signers"] if str(i) in by_id]
        if len(ordered) != len(s.validated_data["signers"]):
            return Response({"signers": "Signataire inconnu."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            req = signatures.create_request(
                version, ordered, request.user,
                title=s.validated_data.get("title", ""), message=s.validated_data.get("message", ""),
                validity_days=s.validated_data.get("expires_in_days", signatures.DEFAULT_VALIDITY_DAYS),
            )
        except DjangoValidationError as exc:
            return Response({"signers": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        log_audit(request.user, AuditLog.Action.CREATE, "signature", req.pk,
                  {"document": str(version.document_id), "version": version.number, "signers": len(ordered)},
                  request_ip(request))
        return Response(self.get_serializer(req).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def otp(self, request, pk=None):
        """Envoie par e-mail le code à usage unique (10 min) au signataire dont c'est le tour."""
        try:
            signatures.send_otp(self.get_object(), request.user)
        except DjangoValidationError as exc:
            return _bad_request(exc)
        return Response({"detail": "Code envoyé par e-mail.", "expires_in_minutes": signatures.OTP_TTL_MINUTES})

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def sign(self, request, pk=None):
        """Signe : code e-mail + mot de passe (ré-authentification) ; preuve scellée et chaînée."""
        req = self.get_object()
        try:
            signer = signatures.sign(
                req, request.user, request.data.get("otp", ""), request.data.get("password", ""),
                ip=request_ip(request), user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except DjangoValidationError as exc:
            return _bad_request(exc)
        log_audit(request.user, AuditLog.Action.UPDATE, "signature", req.pk,
                  {"event": "signed", "order": signer.order, "sha256": signer.document_sha256}, request_ip(request))
        req.refresh_from_db()
        return Response(self.get_serializer(req).data)

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def refuse(self, request, pk=None):
        req = self.get_object()
        try:
            signatures.refuse(req, request.user, request.data.get("reason", ""))
        except DjangoValidationError as exc:
            return _bad_request(exc)
        log_audit(request.user, AuditLog.Action.UPDATE, "signature", req.pk,
                  {"event": "refused", "reason": request.data.get("reason", "")}, request_ip(request))
        req.refresh_from_db()
        return Response(self.get_serializer(req).data)

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def unlock(self, request, pk=None):
        """Déverrouille les signataires bloqués (trop d'essais) — émetteur ou administrateur."""
        req = self.get_object()
        if not (is_admin_or_staff(request.user) or req.created_by_id == request.user.id):
            return Response({"detail": "Réservé à l'émetteur."}, status=status.HTTP_403_FORBIDDEN)
        signatures.unlock(req)
        return Response({"detail": "Signataires déverrouillés."})

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def certificate(self, request, pk=None):
        """Certificat de signature : chaîne de preuves rejouée + intégrité du fichier."""
        return Response(signatures.certificate(self.get_object()))
