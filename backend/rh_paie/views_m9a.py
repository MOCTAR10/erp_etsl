"""Écarts M9-A : grille de salaires, primes récurrentes, carrière, absences, calendrier des déclarations."""

from datetime import date

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Absence, BulletinPaie, EcheanceDeclaration, ElementFixe, EvenementCarriere, GrilleSalaire
from .paie_m9a import calendrier_declarations, enregistrer_evenement
from .serializers import (
    AbsenceSerializer, EcheanceDeclarationSerializer, ElementFixeSerializer, EvenementCarriereInputSerializer,
    EvenementCarriereSerializer, GrilleSalaireSerializer,
)
from .services import CanManagePaie, CanManageRh, confirmer_valeur


class ConfirmableMixin:
    """Une valeur confirmée ne se modifie plus : créer une nouvelle version (date d'effet postérieure)."""

    objet = ""

    def perform_update(self, serializer):
        if not serializer.instance.est_provisoire:
            raise serializers.ValidationError({"detail": "Valeur confirmée : créer une nouvelle version datée."})
        serializer.save()

    @extend_schema(request=None)
    @action(detail=True, methods=["post"], url_path="confirmer")
    def confirmer(self, request, pk=None):
        return Response(self.get_serializer(confirmer_valeur(self.get_object(), self.objet, request.user)).data)


class GrilleSalaireViewSet(ConfirmableMixin, viewsets.ModelViewSet):
    queryset = GrilleSalaire.objects.all()
    serializer_class = GrilleSalaireSerializer
    permission_classes = [CanManagePaie]
    http_method_names = ["get", "post", "patch", "head", "options"]
    search_fields = ("convention", "classe")
    objet = "grille"


class ElementFixeViewSet(viewsets.ModelViewSet):
    queryset = ElementFixe.objects.select_related("contrat__employe", "rubrique").all()
    serializer_class = ElementFixeSerializer
    permission_classes = [CanManagePaie]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        if contrat := self.request.query_params.get("contrat"):
            qs = qs.filter(contrat_id=contrat)
        return qs


class EvenementCarriereViewSet(viewsets.ReadOnlyModelViewSet):
    """Historique de carrière inaltérable : un événement s'ajoute, ne se modifie ni ne se supprime."""

    queryset = EvenementCarriere.objects.select_related("employe", "cree_par", "grille_avant", "grille_apres").all()
    serializer_class = EvenementCarriereSerializer
    permission_classes = [CanManagePaie]
    search_fields = ("employe__code", "employe__nom")

    def get_queryset(self):
        qs = super().get_queryset()
        if employe := self.request.query_params.get("employe"):
            qs = qs.filter(employe_id=employe)
        return qs

    @extend_schema(request=EvenementCarriereInputSerializer, responses=EvenementCarriereSerializer)
    def create(self, request, *args, **kwargs):
        entree = EvenementCarriereInputSerializer(data=request.data)
        entree.is_valid(raise_exception=True)
        d = entree.validated_data
        try:
            ev = enregistrer_evenement(
                d["employe"], d["type"], d["date_effet"], request.user, categorie=d.get("categorie") or "",
                fonction=d.get("fonction") or "", grille=d.get("grille"), salaire=d.get("salaire"),
                motif=d.get("motif") or "",
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"detail": exc.messages})
        return Response(self.get_serializer(ev).data, status=status.HTTP_201_CREATED)


class AbsenceViewSet(viewsets.ModelViewSet):
    queryset = Absence.objects.select_related("employe", "valide_par").all()
    serializer_class = AbsenceSerializer
    permission_classes = [CanManageRh]
    http_method_names = ["get", "post", "head", "options"]
    search_fields = ("code", "employe__nom", "employe__code")

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if employe := params.get("employe"):
            qs = qs.filter(employe_id=employe)
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        return qs

    def _transition(self, depuis, vers, message, **champs):
        with transaction.atomic():
            absence = Absence.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
            if absence.statut not in depuis:
                return Response({"detail": message}, status=status.HTTP_400_BAD_REQUEST)
            if absence.statut == Absence.Statut.VALIDEE and vers == Absence.Statut.ANNULEE:
                mois = date(absence.date_debut.year, absence.date_debut.month, 1)
                if BulletinPaie.objects.filter(
                    employe=absence.employe, periode__gte=mois, periode__lte=absence.date_fin,
                    statut__in=(BulletinPaie.Statut.VALIDE, BulletinPaie.Statut.CLOTURE),
                ).exists():
                    return Response(
                        {"detail": "Absence déjà retenue sur un bulletin validé : régulariser sur le mois suivant."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            absence.statut = vers
            for champ, valeur in champs.items():
                setattr(absence, champ, valeur)
            absence.save(update_fields=["statut", "updated_at", *champs])
        return Response(self.get_serializer(absence).data)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"], url_path="valider")
    def valider(self, request, pk=None):
        """Valide l'absence : non rémunérée, elle est retenue au bulletin préparé du mois."""
        return self._transition(
            (Absence.Statut.SAISIE,), Absence.Statut.VALIDEE, "Seule une absence saisie peut être validée.",
            valide_par=request.user, valide_le=timezone.now(),
        )

    @extend_schema(request=None)
    @action(detail=True, methods=["post"], url_path="annuler")
    def annuler(self, request, pk=None):
        return self._transition(
            (Absence.Statut.SAISIE, Absence.Statut.VALIDEE), Absence.Statut.ANNULEE, "Absence déjà annulée."
        )


class EcheanceDeclarationViewSet(ConfirmableMixin, viewsets.ModelViewSet):
    queryset = EcheanceDeclaration.objects.all()
    serializer_class = EcheanceDeclarationSerializer
    permission_classes = [CanManagePaie]
    http_method_names = ["get", "post", "patch", "head", "options"]
    objet = "echeance"

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"], url_path="calendrier")
    def calendrier(self, request):
        """Dates limites des 90 derniers et 90 prochains jours, avec l'état de dépôt de chaque déclaration."""
        return Response(calendrier_declarations())
