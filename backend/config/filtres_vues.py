"""Action `GET <liste>/filtres/` (EX-G-09) : séparée de `config.filtres` (chargé par les réglages DRF, sans import
circulaire avec drf-spectacular)."""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.response import Response

from .filtres import decrire_filtres


class FiltresMulticriteresMixin:
    """Ajoute `GET <liste>/filtres/` (description des critères) à un ViewSet déclarant `champs_filtrables`."""

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def filtres(self, request):
        model = self.get_queryset().model
        return Response({"results": decrire_filtres(model, self.champs_filtrables, getattr(self, "libelles_filtres", None))})
