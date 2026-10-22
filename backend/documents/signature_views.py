"""API de signature électronique avancée (CL-OM-06) — demandes, code à usage unique, signature, certificat."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users import mfa
from users.journal import journaliser
from users.models import JournalAcces, User

from . import signatures
from .audit import log_audit, request_ip
from .models import AuditLog, SignatureRequest, Signer, Version
from .services import can_read_document, can_write_document, is_admin_or_staff


class SignerSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    email = serializers.EmailField(source="user.email", read_only=True)
    verrouille = serializers.SerializerMethodField()

    class Meta:
        model = Signer
        fields = ["id", "user", "name", "email", "order", "status", "signed_at", "refusal_reason", "methode",
                  "verrouille"]

    def get_verrouille(self, obj):
        """Bloqué après trop d'essais (déblocage par l'émetteur ou l'administration, bouton de l'écran)."""
        return obj.status == Signer.Status.PENDING and obj.otp_attempts >= signatures.MAX_ATTEMPTS

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
    peut_debloquer = serializers.SerializerMethodField()
    expired = serializers.BooleanField(source="is_expired", read_only=True)

    class Meta:
        model = SignatureRequest
        fields = [
            "id", "version", "version_number", "document_title", "title", "message", "status", "expired",
            "document_sha256", "created_by", "created_at", "expires_at", "completed_at",
            "signers", "expires_in_days", "signataires", "a_mon_tour", "peut_debloquer",
        ]
        read_only_fields = ["id", "status", "document_sha256", "created_by", "created_at", "expires_at", "completed_at"]

    def get_a_mon_tour(self, obj):
        user = self.context["request"].user
        cur = signatures.current_signer(obj) if obj.status == SignatureRequest.Status.PENDING else None
        return bool(cur and cur.user_id == user.id and not obj.is_expired)

    def get_peut_debloquer(self, obj):
        """Demande en cours avec un signataire bloqué, et lecteur = émetteur ou administration (action `unlock`)."""
        user = self.context["request"].user
        if obj.status != SignatureRequest.Status.PENDING:
            return False
        if not (is_admin_or_staff(user) or obj.created_by_id == user.id):
            return False
        return any(
            s.status == Signer.Status.PENDING and s.otp_attempts >= signatures.MAX_ATTEMPTS for s in obj.signers.all()
        )


def qr_svg_data_uri(texte):
    """QR code SVG (data URI) du lien otpauth, scanné par l'application d'authentification ; vide si indisponible."""
    try:
        import segno
    except ImportError:  # dépendance absente : l'écran garde la clé et le lien
        return ""
    return segno.make(texte, error="m").svg_data_uri(scale=4, border=2)


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

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"], url_path="signataires")
    def signataires(self, request):
        """Annuaire minimal (id, nom, rôle) des comptes actifs pour composer une demande de signature."""
        users = User.objects.filter(is_active=True).order_by("first_name", "last_name", "email")
        return Response([{"id": u.pk, "name": u.get_full_name() or u.email, "role": u.role} for u in users])

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

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"], url_path="mode")
    def mode(self, request):
        """Second facteur offert au signataire connecté : code e-mail (messagerie active) et/ou TOTP (MFA active)."""
        return Response(signatures.mode_signature(User.objects.get(pk=request.user.pk)))

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"], url_path="enrolement-totp")
    def enrolement_totp(self, request):
        """Enrôlement de la double authentification depuis l'écran Signatures (sans messagerie, seul second facteur).

        Même secret et même vérification que la MFA de connexion (users/mfa.py) : une fois activée, la connexion
        demandera aussi le code de l'application d'authentification.
        """
        user = User.objects.get(pk=request.user.pk)
        if user.mfa_active:
            return Response({"detail": "Double authentification déjà activée."}, status=status.HTTP_400_BAD_REQUEST)
        if not user.mfa_secret:
            user.mfa_secret = mfa.generer_secret()
            user.save(update_fields=["mfa_secret"])
        journaliser(request, JournalAcces.Evenement.MFA_ENROLEMENT, user=user, details={"origine": "signatures"})
        uri = mfa.uri_otpauth(user.mfa_secret, user.email)
        return Response({"secret": user.mfa_secret, "otpauth_uri": uri, "qr_svg": qr_svg_data_uri(uri)})

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"], url_path="activation-totp")
    def activation_totp(self, request):
        """Active la double authentification après un premier code TOTP valide (non rejouable)."""
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            if user.mfa_active:
                return Response({"detail": "Double authentification déjà activée."},
                                status=status.HTTP_400_BAD_REQUEST)
            pas = mfa.verifier(user.mfa_secret, request.data.get("code"), user.mfa_dernier_pas)
            if pas is not None:
                user.mfa_dernier_pas, user.mfa_active, user.mfa_active_le = pas, True, timezone.now()
                user.save(update_fields=["mfa_dernier_pas", "mfa_active", "mfa_active_le"])
        if pas is None:
            journaliser(request, JournalAcces.Evenement.MFA_ECHEC, user=user, details={"origine": "signatures"})
            return Response({"code": "Code invalide ou expiré."}, status=status.HTTP_400_BAD_REQUEST)
        journaliser(request, JournalAcces.Evenement.MFA_SUCCES, user=user, details={"origine": "signatures"})
        return Response(signatures.mode_signature(user))

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
        """Signe : code (e-mail ou TOTP, `methode`) + mot de passe (ré-authentification) ; preuve scellée et chaînée."""
        req = self.get_object()
        try:
            signer = signatures.sign(
                req, request.user, request.data.get("otp", ""), request.data.get("password", ""),
                ip=request_ip(request), user_agent=request.META.get("HTTP_USER_AGENT", ""),
                methode=str(request.data.get("methode", "") or ""),
            )
        except DjangoValidationError as exc:
            return _bad_request(exc)
        log_audit(request.user, AuditLog.Action.UPDATE, "signature", req.pk,
                  {"event": "signed", "order": signer.order, "sha256": signer.document_sha256,
                   "methode": signer.methode}, request_ip(request))
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
