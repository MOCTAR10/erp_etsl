"""API GLOBAL RENTAL (CL-OM-09) — flux entrants authentifiés par jeton + administration (clients, webhooks)."""

import re
from datetime import date

from django.db import transaction
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from logistique.models import EquipementParc, LectureCompteur, LocationGR
from logistique.services import reporter_compteur
from users.permissions import IsAdminOrStaff

from .auth import ApiKeyAuthentication, HasApiScope
from .gr import validate_webhook_url
from .idempotency import idempotent
from .models import ApiClient, WebhookDelivery, WebhookEndpoint
from config.i18n import tr

REFERENCE_RE = re.compile(r"^[A-Za-z0-9._/\- ]{1,40}$")


# ------------------------------------------------------------------ flux entrants (jeton)
class GrAPIView(APIView):
    """Base : authentification par jeton uniquement + scope par méthode."""

    authentication_classes = [ApiKeyAuthentication]
    permission_classes = [HasApiScope]
    required_scopes = {"GET": "gr:read", "HEAD": "gr:read", "OPTIONS": "gr:read", "POST": "gr:write"}


IDEMPOTENCY = OpenApiParameter(
    "Idempotency-Key", str, OpenApiParameter.HEADER, required=False,
    description="Clé unique par envoi (80 car. max) : un rejeu avec la même clé renvoie la réponse d'origine "
    "(`Idempotent-Replay: true`) sans dupliquer l'effet.",
)


class GrEquipementsView(GrAPIView):
    @extend_schema(responses=OpenApiTypes.OBJECT, tags=["GLOBAL RENTAL"], description="Équipements du parc GR (scope gr:read).")
    def get(self, request):
        rows = EquipementParc.objects.filter(is_global_rental=True).order_by("code")
        return Response(
            [
                {
                    "code": e.code, "label": e.label, "categorie": e.categorie, "statut": e.statut,
                    "compteur": str(e.compteur_value) if e.compteur_value is not None else None,
                }
                for e in rows
            ]
        )


class GrLocationsView(GrAPIView):
    @extend_schema(responses=OpenApiTypes.OBJECT, tags=["GLOBAL RENTAL"], description="Prestations GR (scope gr:read).")
    def get(self, request):
        rows = LocationGR.objects.select_related("equipement").order_by("-created_at")[:200]
        return Response(
            [
                {
                    "code": loc.code, "statut": loc.statut, "equipement": loc.equipement.code,
                    "reference_bc": loc.reference_bc, "reference_bl": loc.reference_bl,
                    "reference_retour": loc.reference_retour,
                    "date_debut": loc.date_debut, "date_fin": loc.date_fin,
                    "lecture_initiale": loc.lecture_initiale, "lecture_finale": loc.lecture_finale,
                }
                for loc in rows
            ]
        )


def _location(code):
    try:
        return LocationGR.objects.select_for_update().get(code=code)
    except LocationGR.DoesNotExist:
        raise serializers.ValidationError({"location": tr("Prestation %(code)s inconnue.") % {"code": code}})


class CompteurEntrantSerializer(serializers.Serializer):
    location = serializers.CharField(max_length=20)
    date = serializers.DateField()
    valeur = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)
    type_lecture = serializers.ChoiceField(choices=["periodique", "initiale"], default="periodique")

    def validate_date(self, value):
        if value > date.today():
            raise serializers.ValidationError("Date de relevé dans le futur.")
        return value


class GrCompteursView(GrAPIView):
    """BCI_GR / compteurs : relevé reçu de GLOBAL RENTAL (source `gr`), rejouable (Idempotency-Key)."""

    @extend_schema(
        request=CompteurEntrantSerializer, responses={201: OpenApiTypes.OBJECT}, parameters=[IDEMPOTENCY],
        tags=["GLOBAL RENTAL"], description="Relevé de compteur reçu de GR (scope gr:write) : jamais en baisse, prestation active.",
    )
    @idempotent
    def post(self, request):
        s = CompteurEntrantSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        with transaction.atomic():
            loc = _location(d["location"])
            if loc.statut != LocationGR.Statut.ACTIVE:
                raise serializers.ValidationError({"location": "La prestation n'est pas active."})
            dernier = loc.lectures.order_by("-valeur").values_list("valeur", flat=True).first()
            plancher = max(x for x in (dernier, loc.lecture_initiale) if x is not None) if (
                dernier is not None or loc.lecture_initiale is not None
            ) else None
            if plancher is not None and d["valeur"] < plancher:
                raise serializers.ValidationError(
                    {"valeur": tr("Compteur en baisse : %(valeur)s < dernier relevé connu %(plancher)s.") % {"valeur": d['valeur'], "plancher": plancher}}
                )
            lecture = LectureCompteur.objects.create(
                location=loc, date=d["date"], valeur=d["valeur"], type_lecture=d["type_lecture"],
                source=LectureCompteur.Source.GR,
            )
            # Compteur du parc mis à jour (jamais à la baisse) et seuils préventifs M8 évalués (CDC M4 §12.7 / §12.11).
            reporter_compteur(loc.equipement, lecture.valeur)
        return Response(
            {"id": str(lecture.pk), "code": lecture.code, "location": loc.code, "valeur": str(lecture.valeur)},
            status=status.HTTP_201_CREATED,
        )


DOC_FIELDS = {"bci_gr": "reference_bc", "bl_gr": "reference_bl", "retour_gr": "reference_retour"}


class DocumentEntrantSerializer(serializers.Serializer):
    location = serializers.CharField(max_length=20)
    type = serializers.ChoiceField(choices=list(DOC_FIELDS))
    reference = serializers.CharField(max_length=40)

    def validate_reference(self, value):
        if not REFERENCE_RE.match(value):
            raise serializers.ValidationError("Caractères autorisés : lettres, chiffres, . _ / - et espace (40 max).")
        return value.strip()


class GrDocumentsView(GrAPIView):
    """BCI_GR / BL_GR / retour GR : enregistre la référence du document sur la prestation (rejouable)."""

    @extend_schema(
        request=DocumentEntrantSerializer, responses={200: OpenApiTypes.OBJECT, 409: OpenApiTypes.OBJECT},
        parameters=[IDEMPOTENCY], tags=["GLOBAL RENTAL"],
        description="BCI_GR / BL_GR / retour GR (scope gr:write) : 409 si une autre référence est déjà enregistrée.",
    )
    @idempotent
    def post(self, request):
        s = DocumentEntrantSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        with transaction.atomic():
            loc = _location(d["location"])
            champ = DOC_FIELDS[d["type"]]
            actuel = getattr(loc, champ)
            if actuel and actuel != d["reference"]:
                return Response(
                    {"detail": tr("%(champ)s déjà renseignée (%(actuel)s) : correction par l'ETSL uniquement.") % {"champ": champ, "actuel": actuel}},
                    status=status.HTTP_409_CONFLICT,
                )
            setattr(loc, champ, d["reference"])
            loc.save(update_fields=[champ, "updated_at"])
        return Response({"location": loc.code, "type": d["type"], "reference": d["reference"]})


# ------------------------------------------------------------------ administration (admin ETSL)
class ApiClientSerializer(serializers.ModelSerializer):
    api_key = serializers.CharField(read_only=True)

    class Meta:
        model = ApiClient
        fields = ["id", "name", "key_prefix", "scopes", "is_active", "last_used_at", "created_at", "api_key"]
        read_only_fields = ["id", "key_prefix", "last_used_at", "created_at", "api_key"]

    def validate_scopes(self, value):
        allowed = {"gr:read", "gr:write"}
        if not value or not set(value) <= allowed:
            raise serializers.ValidationError(tr("Scopes autorisés : %(sorted)s.") % {"sorted": sorted(allowed)})
        return value


class ApiClientViewSet(viewsets.ModelViewSet):
    """Clients d'API : la clé n'est renvoyée qu'à la création ; révocation = `is_active=false`."""

    queryset = ApiClient.objects.all()
    serializer_class = ApiClientSerializer
    permission_classes = [IsAdminOrStaff]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        client, key = ApiClient.issue(s.validated_data["name"], s.validated_data["scopes"], request.user)
        data = self.get_serializer(client).data
        data["api_key"] = key
        return Response(data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True  # seuls le nom, les scopes et l'état sont modifiables
        return super().update(request, *args, **kwargs)


class WebhookEndpointSerializer(serializers.ModelSerializer):
    secret = serializers.CharField(write_only=True, required=False, allow_blank=True)
    secret_once = serializers.CharField(read_only=True)

    class Meta:
        model = WebhookEndpoint
        fields = ["id", "name", "url", "secret", "secret_once", "topics", "is_active", "created_at"]
        read_only_fields = ["id", "created_at", "secret_once"]

    def validate_url(self, value):
        try:
            validate_webhook_url(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))
        return value

    def validate_topics(self, value):
        if not value or not all(isinstance(t, str) and re.match(r"^[a-z0-9_.]{3,60}$", t) for t in value):
            raise serializers.ValidationError("Liste de sujets attendue (ex. gr.location.demarree).")
        return value


class WebhookEndpointViewSet(viewsets.ModelViewSet):
    queryset = WebhookEndpoint.objects.all()
    serializer_class = WebhookEndpointSerializer
    permission_classes = [IsAdminOrStaff]

    def perform_create(self, serializer):
        import secrets

        secret = serializer.validated_data.pop("secret", "") or secrets.token_urlsafe(32)
        serializer.save(secret=secret)
        serializer.instance.secret_once = secret  # montré une seule fois, à la création


class WebhookDeliverySerializer(serializers.ModelSerializer):
    endpoint_name = serializers.CharField(source="endpoint.name", read_only=True)

    class Meta:
        model = WebhookDelivery
        fields = [
            "id", "endpoint", "endpoint_name", "topic", "status", "attempts", "response_code",
            "last_error", "next_attempt_at", "created_at", "delivered_at",
        ]


class WebhookDeliveryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = WebhookDelivery.objects.select_related("endpoint").all()
    serializer_class = WebhookDeliverySerializer
    permission_classes = [IsAdminOrStaff]

    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        from .gr import deliver

        d = self.get_object()
        if d.status == WebhookDelivery.Status.DELIVERED:
            return Response({"detail": "Déjà livrée."}, status=status.HTTP_400_BAD_REQUEST)
        d.status = WebhookDelivery.Status.PENDING
        d.attempts = 0
        deliver(d)
        return Response(self.get_serializer(d).data)
