"""Écarts M9-B : comptes de paie, provision des congés payés, coût de main-d'œuvre chargé (aval M3 / M11)."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from accounting_kernel.permissions import CanPostAccounting

from .compta_m9b import cout_main_oeuvre, provisionner_conges
from .models import ComptePaie, ProvisionConges
from .serializers import ComptePaieSerializer, ProvisionCongesSerializer
from .services import CanManagePaie, can_see_amount


class ComptePaieViewSet(viewsets.ModelViewSet):
    queryset = ComptePaie.objects.select_related("compte").all()
    serializer_class = ComptePaieSerializer
    permission_classes = [CanManagePaie]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]


class ProvisionCongesViewSet(viewsets.ReadOnlyModelViewSet):
    """Dotation mensuelle aux provisions pour congés payés : une écriture scellée par mois."""

    queryset = ProvisionConges.objects.select_related("move", "created_by").all()
    serializer_class = ProvisionCongesSerializer
    permission_classes = [CanManagePaie]

    def get_permissions(self):
        if self.action == "create":
            return [CanManagePaie(), CanPostAccounting()]
        return super().get_permissions()

    @extend_schema(request=OpenApiTypes.OBJECT, responses=ProvisionCongesSerializer)
    def create(self, request, *args, **kwargs):
        """`{"periode": "AAAA-MM-01"}`."""
        periode = serializers.DateField().run_validation(request.data.get("periode"))
        try:
            provision = provisionner_conges(periode, user=request.user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"detail": exc.messages})
        return Response(self.get_serializer(provision).data, status=status.HTTP_201_CREATED)


class CanVoirCoutMainOeuvre(BasePermission):
    """Coût chargé = donnée salariale agrégée : cercle des montants de la paie ou des opérations."""

    def has_permission(self, request, view):
        from operations.services import can_see_amount as voit_montants_operations

        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated) and (can_see_amount(user) or voit_montants_operations(user))


class CoutMainOeuvreView(APIView):
    permission_classes = [CanVoirCoutMainOeuvre]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        """Coût chargé des pointages transférés en paie par OF : `?debut=AAAA-MM-JJ&fin=AAAA-MM-JJ&ordre=<id>`."""
        aujourdhui = timezone.localdate()
        debut = serializers.DateField().run_validation(request.query_params.get("debut") or aujourdhui.replace(day=1))
        fin = serializers.DateField().run_validation(request.query_params.get("fin") or aujourdhui)
        ordre = request.query_params.get("ordre") or None
        if ordre:
            ordre = serializers.UUIDField().run_validation(ordre)
        return Response(cout_main_oeuvre(debut, fin, ordre=ordre))
