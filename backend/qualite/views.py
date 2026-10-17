"""Vues API M6 — Qualité industrielle, Soudage & Contrôle Qualité / Inspection."""

from django.utils import timezone
from integrations.idempotency import idempotent
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from .models import (
    PointInspection,
    ActionCorrective,
    ControleQualite,
    NonConformite,
    PvControle,
    QualificationSoudeur,
    Soudeur,
    WpsWpqr,
)
from .serializers import (
    PointInspectionSerializer,
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

    @action(detail=True, methods=["post"], permission_classes=[CanValidatePv])
    def valider(self, request, pk=None):
        """Validation d'un WPS/WPQR : QA/QC + hiérarchie ; date et validateur posés par le serveur."""
        wps = self.get_object()
        if wps.statut != WpsWpqr.Statut.BROUILLON:
            return Response(
                {"detail": f"WPS {wps.get_statut_display().lower()} : validation impossible."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        wps.statut = WpsWpqr.Statut.VALIDE
        wps.date_validation = timezone.localdate()
        wps.validated_by = request.user
        wps.save(update_fields=["statut", "date_validation", "validated_by", "updated_at"])
        return Response(self.get_serializer(wps).data)


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

    @idempotent
    def create(self, request, *args, **kwargs):  # contrôle / CND saisi sur le terrain, rejouable
        return super().create(request, *args, **kwargs)


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
        if nc.statut == NonConformite.Statut.CLOTUREE:
            return Response({"detail": "NC clôturée : traitement impossible (ouvrir une nouvelle NC)."},
                            status=status.HTTP_400_BAD_REQUEST)
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
        # MANUEL 5.8 : une NC se clôture après décision de traitement (pas directement depuis « signalée »).
        if nc.statut != NonConformite.Statut.EN_TRAITEMENT:
            return Response({"detail": f"NC {nc.get_statut_display().lower()} : décidez d'abord du traitement."},
                            status=status.HTTP_400_BAD_REQUEST)
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
        if params.get("en_retard") == "1":
            qs = qs.exclude(statut=ActionCorrective.Statut.CLOTUREE).filter(echeance__lt=timezone.localdate())
        return qs

    @action(detail=True, methods=["post"], url_path="cloturer")
    def cloturer(self, request, pk=None):
        capa = self.get_object()
        # Une CAPA clôturée est une preuve : date et évaluation d'efficacité ne se réécrivent pas.
        if capa.statut == ActionCorrective.Statut.CLOTUREE:
            return Response({"detail": "Action déjà clôturée."}, status=status.HTTP_400_BAD_REQUEST)
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


class PointInspectionViewSet(viewsets.ModelViewSet):
    """Points d'un ITP : création/édition tant qu'ils sont en attente ; levée tracée (QA/QC)."""

    queryset = PointInspection.objects.select_related("controle", "leve_par").all()
    serializer_class = PointInspectionSerializer
    permission_classes = [CanManageQualite]

    def get_queryset(self):
        qs = super().get_queryset()
        if controle := self.request.query_params.get("controle"):
            qs = qs.filter(controle_id=controle)
        return qs

    def get_permissions(self):
        if self.action == "lever":
            return [CanValidatePv()]
        return super().get_permissions()

    def _assert_en_attente(self):
        if self.get_object().statut != PointInspection.Statut.EN_ATTENTE:
            raise DRFValidationError("Point déjà traité : non modifiable ni supprimable.")

    def update(self, request, *args, **kwargs):
        self._assert_en_attente()
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._assert_en_attente()
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="lever")
    def lever(self, request, pk=None):
        """Lève un point (conforme) ou le déclare non conforme. Points d'arrêt : dans l'ordre."""
        point = self.get_object()
        if point.statut != PointInspection.Statut.EN_ATTENTE:
            raise DRFValidationError("Point déjà levé ou déclaré non conforme.")
        resultat = request.data.get("resultat", "conforme")
        if resultat not in ("conforme", "non_conforme"):
            raise DRFValidationError({"resultat": "Attendu : conforme ou non_conforme."})
        if point.type_point == PointInspection.TypePoint.ARRET:
            precedents = PointInspection.objects.filter(
                controle=point.controle, type_point=PointInspection.TypePoint.ARRET, ordre__lt=point.ordre
            ).exclude(statut=PointInspection.Statut.LEVE)
            if precedents.exists():
                raise DRFValidationError(
                    "Levez d'abord les points d'arrêt précédents (l'ITP se déroule dans l'ordre)."
                )
        point.statut = (
            PointInspection.Statut.LEVE if resultat == "conforme" else PointInspection.Statut.NON_CONFORME
        )
        point.leve_par = request.user
        point.leve_le = timezone.now()
        point.commentaire = str(request.data.get("commentaire", ""))[:250]
        point.save()
        return Response(self.get_serializer(point).data)
