"""API de l'export des écritures vers SAGE (interface transitoire de double tenue)."""

from django.http import HttpResponse
from django.utils import timezone
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from accounting_kernel.permissions import CanPostAccounting
from config.inputs import date_input

from . import export_sage
from .models import ExportEcritures


class ExportEcrituresSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExportEcritures
        fields = [
            "id", "date_from", "date_to", "journal", "seulement_nouvelles", "nb_ecritures", "nb_lignes",
            "total_debit", "total_credit", "nom_fichier", "sha256", "gabarit_code", "gabarit_provisoire",
            "cree_par", "created_at",
        ]
        read_only_fields = fields


class ExportSageViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Exports d'écritures au gabarit `SAGE_EXPORT` : création, historique, téléchargement du fichier conservé."""

    permission_classes = [CanPostAccounting]
    serializer_class = ExportEcrituresSerializer
    queryset = ExportEcritures.objects.all()

    def create(self, request):
        from django.core.exceptions import ValidationError

        debut = date_input(request.data.get("date_from"), "date_from")
        fin = date_input(request.data.get("date_to"), "date_to", default=timezone.localdate())
        if debut is None:
            raise DRFValidationError({"date_from": "Date de début obligatoire."})
        nouvelles = str(request.data.get("seulement_nouvelles", "true")).lower() not in ("false", "0", "non", "")
        try:
            exp = export_sage.exporter(debut, fin, request.user, journal=str(request.data.get("journal") or "").strip(),
                                       seulement_nouvelles=nouvelles)
        except ValidationError as exc:
            raise DRFValidationError(exc.message_dict if hasattr(exc, "error_dict") else {"detail": exc.messages})
        return Response(self.get_serializer(exp).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def gabarit(self, request):
        g = export_sage.gabarit_export_sage()
        return Response({"id": str(g.id), "code": g.code, "label": g.label, "separateur": g.separateur,
                         "encodage": g.encodage, "format_date": g.format_date, "separateur_decimal": g.separateur_decimal,
                         "colonnes": g.colonnes, "provisoire": g.statut_valeur != g.StatutValeur.CONFIRME})

    @action(detail=True, methods=["get"])
    def telecharger(self, request, pk=None):
        exp = self.get_object()
        enc = export_sage.gabarit_export_sage().encodage or "cp1252"
        resp = HttpResponse(bytes(exp.contenu), content_type=f"text/csv; charset={enc}")
        resp["Content-Disposition"] = f'attachment; filename="{exp.nom_fichier}"'
        return resp
