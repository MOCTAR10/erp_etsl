"""Vues API M7 — HSE : Hygiène, Sécurité & Environnement."""

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    ActionHse,
    BordereauDechet,
    Epi,
    EquipementAtex,
    EvaluationRisque,
    FormationSecurite,
    Incident,
    PermisTravail,
)
from .serializers import (
    ActionHseSerializer,
    BordereauDechetSerializer,
    EpiSerializer,
    EquipementAtexSerializer,
    EvaluationRisqueSerializer,
    FormationSecuriteSerializer,
    IncidentSerializer,
    PermisTravailSerializer,
)
from .services import (
    CanManageHse,
    CanValidateHse,
    can_validate_hse,
)


def _as_bool(value):
    """Booléen tolérant multipart (DRF renvoie des chaînes "True"/"False")."""
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("true", "1", "yes")


class PermisTravailViewSet(viewsets.ModelViewSet):
    queryset = PermisTravail.objects.select_related(
        "affaire", "ordre", "demandeur", "validateur"
    ).all()
    serializer_class = PermisTravailSerializer
    permission_classes = [CanValidateHse]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if type_permis := params.get("type"):
            qs = qs.filter(type_permis=type_permis)
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        if params.get("actifs") == "1":
            qs = qs.filter(statut=PermisTravail.Statut.ACTIF)
        return qs

    @action(detail=True, methods=["post"], url_path="valider")
    def valider(self, request, pk=None):
        permis = self.get_object()
        if permis.statut not in (PermisTravail.Statut.DEMANDE, PermisTravail.Statut.ANNULE):
            return Response(
                {"detail": "Le permis n'est plus en attente de validation."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not can_validate_hse(request.user):
            return Response(
                {"detail": "Réservé au HSE et à la hiérarchie."},
                status=status.HTTP_403_FORBIDDEN,
            )
        accept = _as_bool(request.data.get("accept", True))
        permis.statut = PermisTravail.Statut.VALIDE if accept else PermisTravail.Statut.REFUSE
        permis.validateur = request.user
        permis.date_validation = timezone.now()
        if not accept and request.data.get("motif"):
            permis.notes = request.data.get("motif")
        permis.save()
        return Response(self.get_serializer(permis).data)

    @action(detail=True, methods=["post"], url_path="demarrer")
    def demarrer(self, request, pk=None):
        permis = self.get_object()
        if permis.statut != PermisTravail.Statut.VALIDE:
            return Response(
                {"detail": "Seul un permis validé peut être démarré."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        permis.statut = PermisTravail.Statut.ACTIF
        permis.save()
        return Response(self.get_serializer(permis).data)

    @action(detail=True, methods=["post"], url_path="cloturer")
    def cloturer(self, request, pk=None):
        permis = self.get_object()
        if permis.statut not in (PermisTravail.Statut.ACTIF, PermisTravail.Statut.VALIDE):
            return Response(
                {"detail": "Le permis n'est pas clôturable."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        permis.statut = PermisTravail.Statut.CLOTURE
        permis.date_cloture = timezone.now()
        permis.save()
        return Response(self.get_serializer(permis).data)


class EvaluationRisqueViewSet(viewsets.ModelViewSet):
    queryset = EvaluationRisque.objects.select_related("responsable", "affaire").all()
    serializer_class = EvaluationRisqueSerializer
    permission_classes = [CanManageHse]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        if params.get("critiques") == "1":
            qs = [r for r in qs if r.criticite == EvaluationRisque.Criticite.CRITIQUE]
        if params.get("ouverts") == "1":
            qs = qs.exclude(statut=EvaluationRisque.Statut.CLOTUREE)
        return qs


class EquipementAtexViewSet(viewsets.ModelViewSet):
    queryset = EquipementAtex.objects.all()
    serializer_class = EquipementAtexSerializer
    permission_classes = [CanManageHse]

    def get_queryset(self):
        qs = super().get_queryset()
        if statut := self.request.query_params.get("statut"):
            qs = qs.filter(statut=statut)
        if self.request.query_params.get("expires") == "1":
            qs = [
                eq for eq in qs
                if eq.certificat_expire
            ]
        return qs


class IncidentViewSet(viewsets.ModelViewSet):
    queryset = Incident.objects.select_related(
        "declared_by", "enqueteur"
    ).prefetch_related("actions").all()
    serializer_class = IncidentSerializer
    permission_classes = [CanManageHse]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if type_incident := params.get("type"):
            qs = qs.filter(type_incident=type_incident)
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        if gravite := params.get("gravite"):
            qs = qs.filter(gravite=gravite)
        if params.get("ouverts") == "1":
            qs = qs.exclude(statut=Incident.Statut.CLOTURE)
        if params.get("archive") == "1":
            qs = qs.filter(archive=True)
        return qs

    @action(detail=True, methods=["post"], url_path="ouvrir-enquete")
    def ouvrir_enquete(self, request, pk=None):
        incident = self.get_object()
        if incident.statut == Incident.Statut.CLOTURE:
            return Response(
                {"detail": "Incident clôturé : enquête impossible."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not can_validate_hse(request.user):
            return Response(
                {"detail": "Réservé au HSE et à la hiérarchie."},
                status=status.HTTP_403_FORBIDDEN,
            )
        incident.statut = Incident.Statut.EN_ENQUETE
        incident.enqueteur = request.user
        incident.date_ouverture_enquete = timezone.now()
        incident.save()
        return Response(self.get_serializer(incident).data)

    @action(detail=True, methods=["post"], url_path="cloturer")
    def cloturer(self, request, pk=None):
        incident = self.get_object()
        if incident.statut == Incident.Statut.CLOTURE:
            return Response(
                {"detail": "Incident déjà clôturé."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        incident.statut = Incident.Statut.CLOTURE
        incident.archive = True
        if request.data.get("rapport"):
            incident.rapport = request.data.get("rapport")
        if request.data.get("date_rapport"):
            incident.date_rapport = request.data.get("date_rapport")
        incident.save()
        return Response(self.get_serializer(incident).data)

    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        today = timezone.localdate()
        j30 = today + timezone.timedelta(days=30)

        last_accident = (
            Incident.objects.filter(
                type_incident__in=[
                    Incident.TypeIncident.ACCIDENT,
                    Incident.TypeIncident.BLESSURE,
                ],
                date_evenement__lte=timezone.now(),
            ).order_by("-date_evenement").first()
        )
        jours_sans_accident = None
        if last_accident:
            jours_sans_accident = max(
                (timezone.now() - last_accident.date_evenement).days,
                0,
            )

        risques_ouverts = EvaluationRisque.objects.exclude(
            statut=EvaluationRisque.Statut.CLOTUREE
        )
        risques_critiques = sum(
            1
            for r in risques_ouverts
            if r.criticite == EvaluationRisque.Criticite.CRITIQUE
        )

        return Response(
            {
                "jours_sans_accident": jours_sans_accident,
                "incidents_ouverts": Incident.objects.exclude(
                    statut=Incident.Statut.CLOTURE
                ).count(),
                "incidents_critiques": Incident.objects.filter(
                    gravite=Incident.Gravite.CRITIQUE
                ).exclude(statut=Incident.Statut.CLOTURE).count(),
                "actions_ouvertes": ActionHse.objects.exclude(
                    statut=ActionHse.Statut.CLOTUREE
                ).count(),
                "permis_actifs": PermisTravail.objects.filter(
                    statut=PermisTravail.Statut.ACTIF
                ).count(),
                "risques_critiques": risques_critiques,
                "epi_a_renouveler": Epi.objects.filter(
                    statut=Epi.Statut.EN_USAGE,
                    date_renouvellement__lte=j30,
                ).count(),
                "formations_prevues": FormationSecurite.objects.filter(
                    statut=FormationSecurite.Statut.PLANIFIEE
                ).count(),
                "bsd_en_attente": BordereauDechet.objects.filter(
                    statut=BordereauDechet.Statut.EN_ATTENTE
                ).count(),
                "atex_quarantaine": EquipementAtex.objects.filter(
                    statut=EquipementAtex.Statut.QUARANTAINE
                ).count(),
            }
        )


class ActionHseViewSet(viewsets.ModelViewSet):
    queryset = ActionHse.objects.select_related("incident", "risque", "responsable").all()
    serializer_class = ActionHseSerializer
    permission_classes = [CanManageHse]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if incident := params.get("incident"):
            qs = qs.filter(incident_id=incident)
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        if params.get("ouvertes") == "1":
            qs = qs.exclude(statut=ActionHse.Statut.CLOTUREE)
        return qs

    @action(detail=True, methods=["post"], url_path="cloturer")
    def cloturer(self, request, pk=None):
        action = self.get_object()
        action.statut = ActionHse.Statut.CLOTUREE
        action.closed_at = timezone.now()
        if "efficace" in request.data:
            action.efficace = _as_bool(request.data.get("efficace"))
        action.save()
        return Response(self.get_serializer(action).data)


class FormationSecuriteViewSet(viewsets.ModelViewSet):
    queryset = FormationSecurite.objects.all()
    serializer_class = FormationSecuriteSerializer
    permission_classes = [CanManageHse]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if type_session := params.get("type"):
            qs = qs.filter(type_session=type_session)
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        if params.get("prevues") == "1":
            qs = qs.filter(statut=FormationSecurite.Statut.PLANIFIEE)
        return qs


class EpiViewSet(viewsets.ModelViewSet):
    queryset = Epi.objects.select_related("beneficiaire").all()
    serializer_class = EpiSerializer
    permission_classes = [CanManageHse]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if type_epi := params.get("type"):
            qs = qs.filter(type_epi=type_epi)
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        if params.get("a_renouveler") == "1":
            j30 = timezone.localdate() + timezone.timedelta(days=30)
            qs = qs.filter(
                statut=Epi.Statut.EN_USAGE,
                date_renouvellement__lte=j30,
            )
        return qs


class BordereauDechetViewSet(viewsets.ModelViewSet):
    queryset = BordereauDechet.objects.select_related("transporteur").all()
    serializer_class = BordereauDechetSerializer
    permission_classes = [CanManageHse]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if type_dechet := params.get("type"):
            qs = qs.filter(type_dechet=type_dechet)
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        if params.get("dangereux") == "1":
            qs = qs.filter(type_dechet__in=[
                BordereauDechet.TypeDechet.HUILES,
                BordereauDechet.TypeDechet.SOLVANTS,
                BordereauDechet.TypeDechet.BATTERIES,
                BordereauDechet.TypeDechet.PEINTURES,
            ])
        return qs