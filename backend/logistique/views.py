"""API module M4 — Logistique ETSL & GLOBAL RENTAL (RF-ERP-30…33)."""

from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    AffectationParc,
    DemandeMobilisation,
    EquipementParc,
    LectureCompteur,
    LocationGR,
)
from .serializers import (
    AffectationParcSerializer,
    DemandeMobilisationSerializer,
    EquipementParcSerializer,
    LectureCompteurSerializer,
    LocationGRSerializer,
)
from .services import CanManageLogistique, can_see_amount, stats_parc


class _CommonViewSet(viewsets.ModelViewSet):
    """Lecture authentifiée ; écriture réservée aux rôles Logistique."""

    http_method_names = ["get", "post", "patch", "delete"]

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAuthenticated()]
        return [CanManageLogistique()]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["can_view_amount"] = can_see_amount(self.request.user)
        return context


class EquipementParcViewSet(_CommonViewSet):
    serializer_class = EquipementParcSerializer

    def get_queryset(self):
        qs = EquipementParc.objects.select_related("proprietaire")
        statut_ = self.request.query_params.get("statut")
        if statut_:
            qs = qs.filter(statut=statut_)
        gr = self.request.query_params.get("global_rental")
        if gr in ("true", "1"):
            qs = qs.filter(is_global_rental=True)
        elif gr in ("false", "0"):
            qs = qs.filter(is_global_rental=False)
        categorie = self.request.query_params.get("categorie")
        if categorie:
            qs = qs.filter(categorie=categorie)
        return qs

    @action(detail=False, methods=["post"], url_path="disponibilite")
    def set_disponible(self, request):
        """Remet un équipement du parc disponible (RF-ERP-30)."""
        equipement = EquipementParc.objects.filter(pk=request.data.get("id")).first()
        if not equipement:
            raise ValidationError({"id": "Équipement introuvable."})
        equipement.statut = EquipementParc.Statut.DISPONIBLE
        equipement.save(update_fields=["statut", "updated_at"])
        return Response(self.get_serializer(equipement).data)


class DemandeMobilisationViewSet(_CommonViewSet):
    serializer_class = DemandeMobilisationSerializer

    def get_queryset(self):
        qs = DemandeMobilisation.objects.select_related("affaire", "ordre", "created_by")
        statut_ = self.request.query_params.get("statut")
        if statut_:
            qs = qs.filter(statut=statut_)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"], url_path="soumettre")
    def soumettre(self, request, pk=None):
        """Soumission d'un besoin opérationnel (RF-ERP-31)."""
        demande = self.get_object()
        demande.statut = DemandeMobilisation.Statut.SOUMISE
        demande.save(update_fields=["statut", "updated_at"])
        return Response(self.get_serializer(demande).data)

    @action(detail=True, methods=["post"], url_path="traiter")
    def traiter(self, request, pk=None):
        """Marque le besoin traité (affectation réalisée)."""
        demande = self.get_object()
        demande.statut = DemandeMobilisation.Statut.TRAITEE
        demande.save(update_fields=["statut", "updated_at"])
        return Response(self.get_serializer(demande).data)


class AffectationParcViewSet(_CommonViewSet):
    serializer_class = AffectationParcSerializer

    def get_queryset(self):
        qs = AffectationParc.objects.select_related(
            "equipement", "demande", "affaire", "ordre", "responsable", "created_by"
        )
        statut_ = self.request.query_params.get("statut")
        if statut_:
            qs = qs.filter(statut=statut_)
        equipement = self.request.query_params.get("equipement")
        if equipement:
            qs = qs.filter(equipement_id=equipement)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        instance = self.get_object()
        if instance.statut == AffectationParc.Statut.TERMINEE:
            raise ValidationError("Affectation déjà terminée : modifiable via retour.")
        serializer.save()

    @action(detail=True, methods=["post"], url_path="terminer")
    def terminer(self, request, pk=None):
        """Fin d'affectation ; l'équipement redevient disponible (RF-ERP-31)."""
        affectation = self.get_object()
        affectation.statut = AffectationParc.Statut.TERMINEE
        affectation.date_fin = timezone.now().date()
        affectation.save(update_fields=["statut", "date_fin", "updated_at"])
        equipement = affectation.equipement
        if equipement.statut == EquipementParc.Statut.AFFECTE:
            equipement.statut = EquipementParc.Statut.DISPONIBLE
            equipement.save(update_fields=["statut", "updated_at"])
        return Response(self.get_serializer(affectation).data)


class LocationGRViewSet(_CommonViewSet):
    serializer_class = LocationGRSerializer

    def get_queryset(self):
        qs = LocationGR.objects.select_related(
            "partenaire", "equipement", "affaire", "devise", "created_by"
        )
        statut_ = self.request.query_params.get("statut")
        if statut_:
            qs = qs.filter(statut=statut_)
        gr = self.request.query_params.get("global_rental")
        if gr in ("true", "1"):
            qs = qs.filter(partenaire__is_global_rental=True)
        affaire = self.request.query_params.get("affaire")
        if affaire:
            qs = qs.filter(affaire_id=affaire)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        """Parc, locations actives, compteurs (RF-ERP-30/32/33)."""
        return Response(stats_parc())

    @action(detail=True, methods=["post"], url_path="demarrer")
    def demarrer(self, request, pk=None):
        """Démarrage location GR : compteur initial + statut actif (RF-ERP-32)."""
        location = self.get_object()
        lecture = request.data.get("lecture_initiale")
        if lecture is None:
            raise ValidationError({"lecture_initiale": "Compteur de départ requis."})
        location.lecture_initiale = lecture
        location.statut = LocationGR.Statut.ACTIVE
        location.save(update_fields=["lecture_initiale", "statut", "updated_at"])
        equipement = location.equipement
        if equipement.statut != EquipementParc.Statut.EN_LOCATION:
            equipement.statut = EquipementParc.Statut.EN_LOCATION
            equipement.save(update_fields=["statut", "updated_at"])
        return Response(self.get_serializer(location).data)

    @action(detail=True, methods=["post"], url_path="cloturer")
    def cloturer(self, request, pk=None):
        """Clôture location GR : compteur final + consommation + statut (RF-ERP-32/33)."""
        location = self.get_object()
        if location.statut != LocationGR.Statut.ACTIVE:
            raise ValidationError("Seule une location active peut être clôturée.")
        lecture = request.data.get("lecture_finale")
        if lecture is None:
            raise ValidationError({"lecture_finale": "Compteur de retour requis."})
        location.lecture_finale = lecture
        if location.consommation is not None and location.consommation < 0:
            raise ValidationError("Compteur de retour inférieur au compteur de départ.")
        location.statut = LocationGR.Statut.TERMINEE
        location.save(update_fields=["lecture_finale", "statut", "updated_at"])
        equipement = location.equipement
        if equipement.statut == EquipementParc.Statut.EN_LOCATION:
            equipement.statut = EquipementParc.Statut.DISPONIBLE
            equipement.save(update_fields=["statut", "updated_at"])
        return Response(self.get_serializer(location).data)


class LectureCompteurViewSet(_CommonViewSet):
    serializer_class = LectureCompteurSerializer

    def get_queryset(self):
        qs = LectureCompteur.objects.select_related(
            "location", "location__equipement", "releve_par"
        )
        location = self.request.query_params.get("location")
        if location:
            qs = qs.filter(location_id=location)
        equipement = self.request.query_params.get("equipement")
        if equipement:
            qs = qs.filter(location__equipement_id=equipement)
        if self.request.query_params.get("from"):
            qs = qs.filter(date__gte=self.request.query_params["from"])
        if self.request.query_params.get("to"):
            qs = qs.filter(date__lte=self.request.query_params["to"])
        return qs

    def perform_create(self, serializer):
        serializer.save(releve_par=self.request.user)