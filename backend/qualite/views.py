"""Vues API M6 — Qualité industrielle, Soudage & Contrôle Qualité / Inspection."""

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    ActionCorrective,
    ControleQualite,
    NonConformite,
    PvControle,
    QualificationSoudeur,
    Soudeur,
    WpsWpqr,
)
from .serializers import (
    ActionCorrectiveSerializer,
    ControleQualiteSerializer,
    NonConformiteSerializer,
    PvControleSerializer,
    QualificationSoudeurSerializer,
    SoudeurSerializer,
    WpsWpqrSerializer,
)
from .services import CanManageQualite, CanValidatePv, can_validate_pv


def _as_bool(value):
    """Booléen tolérant multipart (DRF renvoie des chaînes "True"/"False")."""
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("true", "1", "yes")


class SoudeurViewSet(viewsets.ModelViewSet):
    queryset = Soudeur.objects.all()
    serializer_class = SoudeurSerializer
    permission_classes = [CanManageQualite]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("active") == "1":
            qs = qs.filter(is_active=True)
        return qs


class QualificationSoudeurViewSet(viewsets.ModelViewSet):
    queryset = QualificationSoudeur.objects.select_related("soudeur").all()
    serializer_class = QualificationSoudeurSerializer
    permission_classes = [CanManageQualite]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if soudeur := params.get("soudeur"):
            qs = qs.filter(soudeur_id=soudeur)
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        if params.get("valides") == "1":
            qs = qs.filter(
                statut=QualificationSoudeur.Statut.VALIDE,
                date_validite__gte=timezone.localdate(),
            )
        if params.get("expirees") == "1":
            qs = qs.filter(date_validite__lt=timezone.localdate())
        return qs

    def perform_create(self, serializer):
        serializer.save()


class WpsWpqrViewSet(viewsets.ModelViewSet):
    queryset = WpsWpqr.objects.select_related("validated_by").all()
    serializer_class = WpsWpqrSerializer
    permission_classes = [CanManageQualite]

    def get_queryset(self):
        qs = super().get_queryset()
        if statut := self.request.query_params.get("statut"):
            qs = qs.filter(statut=statut)
        if self.request.query_params.get("valides") == "1":
            qs = qs.filter(statut=WpsWpqr.Statut.VALIDE)
        return qs

    def perform_update(self, serializer):
        instance = serializer.save()
        if (
            instance.statut == WpsWpqr.Statut.VALIDE
            and instance.date_validation is None
        ):
            instance.date_validation = timezone.localdate()
            instance.validated_by = self.request.user
            instance.save(update_fields=["date_validation", "validated_by", "updated_at"])


class ControleQualiteViewSet(viewsets.ModelViewSet):
    queryset = ControleQualite.objects.select_related(
        "affaire", "ordre", "wps", "lot", "created_by"
    ).all()
    serializer_class = ControleQualiteSerializer
    permission_classes = [CanManageQualite]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if type_controle := params.get("type"):
            qs = qs.filter(type_controle=type_controle)
        if resultat := params.get("resultat"):
            qs = qs.filter(resultat=resultat)
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        if affaire := params.get("affaire"):
            qs = qs.filter(affaire_id=affaire)
        if ordre := params.get("ordre"):
            qs = qs.filter(ordre_id=ordre)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class NonConformiteViewSet(viewsets.ModelViewSet):
    queryset = NonConformite.objects.select_related(
        "controle", "decided_by"
    ).prefetch_related("actions_correctives").all()
    serializer_class = NonConformiteSerializer
    permission_classes = [CanManageQualite]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        if gravite := params.get("gravite"):
            qs = qs.filter(gravite=gravite)
        if params.get("archive") == "1":
            qs = qs.filter(archive=True)
        if params.get("ouvertes") == "1":
            qs = qs.exclude(statut=NonConformite.Statut.CLOTUREE)
        return qs

    @action(detail=True, methods=["post"], url_path="traiter")
    def traiter(self, request, pk=None):
        """Applique le traitement décidé par QA/QC (reprise, rejet, arbitrage…)."""
        nc = self.get_object()
        traitement = request.data.get("traitement") or nc.traitement
        if traitement not in NonConformite.Traitement.values:
            return Response(
                {"detail": "Traitement invalide."}, status=status.HTTP_400_BAD_REQUEST
            )
        nc.traitement = traitement
        nc.statut = NonConformite.Statut.EN_TRAITEMENT
        nc.decided_by = request.user
        nc.date_decision = timezone.localdate()
        nc.save()
        if traitement == NonConformite.Traitement.REJET:
            nc.statut = NonConformite.Statut.CLOTUREE
            nc.archive = True
            nc.save()
        return Response(self.get_serializer(nc).data)

    @action(detail=True, methods=["post"], url_path="cloturer")
    def cloturer(self, request, pk=None):
        nc = self.get_object()
        nc.statut = NonConformite.Statut.CLOTUREE
        nc.archive = True
        nc.save()
        return Response(self.get_serializer(nc).data)


class ActionCorrectiveViewSet(viewsets.ModelViewSet):
    queryset = ActionCorrective.objects.select_related(
        "non_conformite", "responsable"
    ).all()
    serializer_class = ActionCorrectiveSerializer
    permission_classes = [CanManageQualite]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if nc := params.get("non_conformite"):
            qs = qs.filter(non_conformite_id=nc)
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        if params.get("ouvertes") == "1":
            qs = qs.exclude(statut=ActionCorrective.Statut.CLOTUREE)
        return qs

    @action(detail=True, methods=["post"], url_path="cloturer")
    def cloturer(self, request, pk=None):
        capa = self.get_object()
        capa.statut = ActionCorrective.Statut.CLOTUREE
        capa.closed_at = timezone.now()
        if "efficace" in request.data:
            capa.efficace = _as_bool(request.data.get("efficace"))
        capa.save()
        return Response(self.get_serializer(capa).data)


class PvControleViewSet(viewsets.ModelViewSet):
    queryset = PvControle.objects.select_related(
        "affaire", "ordre", "validated_by"
    ).prefetch_related("controles__wps").all()
    serializer_class = PvControleSerializer
    permission_classes = [CanValidatePv]

    def get_queryset(self):
        qs = super().get_queryset()
        if statut := self.request.query_params.get("statut"):
            qs = qs.filter(statut=statut)
        if affaire := self.request.query_params.get("affaire"):
            qs = qs.filter(affaire_id=affaire)
        if self.request.query_params.get("en_cours") == "1":
            qs = qs.filter(statut=PvControle.Statut.EN_COURS)
        return qs

    @action(detail=True, methods=["post"], url_path="levee-reserve")
    def levee_reserve(self, request, pk=None):
        """Levée de réserve / réception interne (RF-ERP-51/53)."""
        pv = self.get_object()
        if not can_validate_pv(request.user):
            return Response(
                {"detail": "Réservé au QA/QC et à la hiérarchie."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if pv.statut == PvControle.Statut.REJETE:
            return Response(
                {"detail": "PV rejeté : levée de réserve impossible."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        reserve = _as_bool(request.data.get("reserve"))
        pv.statut = (
            PvControle.Statut.RESERVE
            if reserve
            else PvControle.Statut.RECEPTIONNE
        )
        pv.resultat = (
            ControleQualite.Resultat.RESERVE
            if reserve
            else ControleQualite.Resultat.CONFORME
        )
        pv.levee_reserve = (
            None if reserve else timezone.localdate()
        )
        pv.reserve_motif = request.data.get("motif", "")
        pv.validated_by = request.user
        pv.save()
        return Response(self.get_serializer(pv).data)