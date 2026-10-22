"""API des écarts M6 (lot ecarts-m6m7) : référentiel des organismes agréés (M6.1-09) et WPS requis par profil
contractuel M1.3."""

from django.utils import timezone
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from config.serializers import ModelCleanMixin

from .models import ControleQualite, OrganismeAgree, WpsRequis
from .services import CanManageQualite, CanValidatePv


class OrganismeAgreeSerializer(ModelCleanMixin, serializers.ModelSerializer):
    valide = serializers.SerializerMethodField()
    nb_controles = serializers.SerializerMethodField()

    class Meta:
        model = OrganismeAgree
        fields = [
            "id", "nom", "numero_agrement", "autorite", "methodes", "date_fin_validite", "actif", "valide",
            "nb_controles", "notes", "created_at",
        ]

    def get_valide(self, obj):
        return obj.est_valide()

    def get_nb_controles(self, obj):
        return obj.controles.count()

    def validate_methodes(self, value):
        codes = [c.strip().upper() for c in (value or "").split(",") if c.strip()]
        inconnues = sorted(set(codes) - set(ControleQualite.MethodeCnd.values))
        if inconnues:
            raise serializers.ValidationError(f"Méthode(s) inconnue(s) : {', '.join(inconnues)} (RT, UT, PT, MT).")
        return ",".join(codes)


class WpsRequisSerializer(ModelCleanMixin, serializers.ModelSerializer):
    wps_code = serializers.CharField(source="wps.code", read_only=True)
    wps_statut = serializers.CharField(source="wps.statut", read_only=True)
    contract_code = serializers.CharField(source="contract.code", read_only=True, default=None)

    class Meta:
        model = WpsRequis
        fields = ["id", "contract", "contract_code", "profile", "wps", "wps_code", "wps_statut", "libelle", "created_at"]

    def validate(self, attrs):
        contract = attrs.get("contract", getattr(self.instance, "contract", None))
        profile = attrs.get("profile", getattr(self.instance, "profile", ""))
        wps = attrs.get("wps", getattr(self.instance, "wps", None))
        doublon = WpsRequis.objects.filter(contract=contract, profile=profile or "", wps=wps)
        if self.instance:
            doublon = doublon.exclude(pk=self.instance.pk)
        if doublon.exists():
            raise serializers.ValidationError({"wps": "Ce WPS est déjà exigé pour ce profil / contrat."})
        return super().validate(attrs)


class OrganismeAgreeViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                            mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Référentiel des organismes agréés : écriture QA/QC + hiérarchie ; désactivation plutôt que suppression."""

    queryset = OrganismeAgree.objects.all()
    serializer_class = OrganismeAgreeSerializer
    search_fields = ("nom", "numero_agrement")
    permission_classes = [CanValidatePv]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [CanManageQualite()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("valides") == "1":
            qs = qs.filter(actif=True, date_fin_validite__gte=timezone.localdate())
        return qs


class WpsRequisViewSet(viewsets.ModelViewSet):
    """WPS requis par profil contractuel M1.3 (défaut) ou par contrat ; `conformite/?affaire=` = couverture."""

    queryset = WpsRequis.objects.select_related("wps", "contract").all()
    serializer_class = WpsRequisSerializer
    permission_classes = [CanValidatePv]

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [CanManageQualite()]
        return super().get_permissions()

    @action(detail=False, methods=["get"], url_path="conformite")
    def conformite(self, request):
        from commercial.models import Affaire

        from .ecarts import conformite_wps_affaire

        import uuid

        from operations.models import OrdreFabrication

        params = request.query_params
        try:
            if params.get("ordre"):  # depuis un OF (le QA/QC ne lit pas le module commercial)
                ordre = OrdreFabrication.objects.select_related("affaire").filter(pk=uuid.UUID(str(params["ordre"]))).first()
                affaire = ordre.affaire if ordre else None
            else:
                affaire = Affaire.objects.filter(pk=uuid.UUID(str(params.get("affaire")))).first()
        except ValueError:
            affaire = None
        if affaire is None:
            raise DRFValidationError({"affaire": "Affaire introuvable."})
        return Response(conformite_wps_affaire(affaire))
