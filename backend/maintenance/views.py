"""Vues API M8 — Maintenance & GMAO (parc machines & équipements)."""

from decimal import Decimal

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Actif, Inspection, OrdreTravail
from .serializers import ActifSerializer, InspectionSerializer, OrdreTravailSerializer
from .services import CanManageMaintenance


class ActifViewSet(viewsets.ModelViewSet):
    queryset = Actif.objects.select_related("equipement_gr").all()
    serializer_class = ActifSerializer
    permission_classes = [CanManageMaintenance]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if categorie := params.get("categorie"):
            qs = qs.filter(categorie=categorie)
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        if params.get("arretes") == "1":
            qs = qs.filter(statut__in=[Actif.Statut.EN_MAINTENANCE, Actif.Statut.EN_PANNE])
        if params.get("global_rental") == "1":
            qs = qs.filter(is_global_rental=True)
        return qs


class OrdreTravailViewSet(viewsets.ModelViewSet):
    queryset = OrdreTravail.objects.select_related("actif", "demandeur", "technicien").all()
    serializer_class = OrdreTravailSerializer
    permission_classes = [CanManageMaintenance]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if actif := params.get("actif"):
            qs = qs.filter(actif_id=actif)
        if type_ot := params.get("type"):
            qs = qs.filter(type_ot=type_ot)
        if priorite := params.get("priorite"):
            qs = qs.filter(priorite=priorite)
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        if params.get("ouverts") == "1":
            qs = qs.exclude(statut__in=[OrdreTravail.Statut.CLOTURE, OrdreTravail.Statut.ANNULE])
        return qs

    @action(detail=True, methods=["post"], url_path="planifier")
    def planifier(self, request, pk=None):
        ot = self.get_object()
        if ot.statut != OrdreTravail.Statut.DEMANDE:
            return Response(
                {"detail": "Seul un OT demandé peut être planifié."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ot.statut = OrdreTravail.Statut.PLANIFIE
        if request.data.get("date_planifiee"):
            ot.date_planifiee = request.data.get("date_planifiee")
        if request.data.get("technicien"):
            ot.technicien_id = request.data.get("technicien")
        if request.data.get("priorite"):
            ot.priorite = request.data.get("priorite")
        ot.save()
        return Response(self.get_serializer(ot).data)

    @action(detail=True, methods=["post"], url_path="demarrer")
    def demarrer(self, request, pk=None):
        ot = self.get_object()
        if ot.statut not in (OrdreTravail.Statut.PLANIFIE, OrdreTravail.Statut.DEMANDE):
            return Response(
                {"detail": "L'OT doit être planifié ou demandé pour démarrer."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ot.statut = OrdreTravail.Statut.EN_COURS
        ot.date_debut = timezone.now()
        if request.data.get("technicien"):
            ot.technicien_id = request.data.get("technicien")
        ot.actif.statut = Actif.Statut.EN_MAINTENANCE
        ot.actif.save(update_fields=["statut", "updated_at"])
        ot.save()
        return Response(self.get_serializer(ot).data)

    @action(detail=True, methods=["post"], url_path="terminer")
    def terminer(self, request, pk=None):
        ot = self.get_object()
        if ot.statut != OrdreTravail.Statut.EN_COURS:
            return Response(
                {"detail": "Seul un OT en cours peut être terminé."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ot.statut = OrdreTravail.Statut.TERMINE
        ot.date_fin = timezone.now()
        if request.data.get("rapport"):
            ot.rapport = request.data.get("rapport")
        heures_mo = request.data.get("heures_mo")
        if heures_mo not in (None, ""):
            ot.heures_mo = Decimal(str(heures_mo))
        cout_pieces = request.data.get("cout_pieces")
        if cout_pieces not in (None, ""):
            ot.cout_pieces = Decimal(str(cout_pieces))
        if request.data.get("decision"):
            ot.decision = request.data.get("decision")
        ot.save()
        return Response(self.get_serializer(ot).data)

    @action(detail=True, methods=["post"], url_path="cloturer")
    def cloturer(self, request, pk=None):
        ot = self.get_object()
        if ot.statut not in (OrdreTravail.Statut.TERMINE, OrdreTravail.Statut.EN_COURS):
            return Response(
                {"detail": "L'OT n'est pas clôturable."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ot.statut = OrdreTravail.Statut.CLOTURE
        if not ot.date_fin:
            ot.date_fin = timezone.now()
        if ot.decision == OrdreTravail.Decision.MISE_HORS_SERVICE:
            ot.actif.statut = Actif.Statut.HORS_SERVICE
        elif ot.decision == OrdreTravail.Decision.REFORME:
            ot.actif.statut = Actif.Statut.REFORME
        elif ot.actif.statut == Actif.Statut.EN_MAINTENANCE:
            ot.actif.statut = Actif.Statut.OPERATIONNEL
        ot.actif.save(update_fields=["statut", "updated_at"])
        ot.save()
        return Response(self.get_serializer(ot).data)

    @action(detail=True, methods=["post"], url_path="annuler")
    def annuler(self, request, pk=None):
        ot = self.get_object()
        if ot.statut in (OrdreTravail.Statut.CLOTURE, OrdreTravail.Statut.ANNULE):
            return Response(
                {"detail": "L'OT est déjà clos ou annulé."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ot.statut = OrdreTravail.Statut.ANNULE
        ot.save()
        return Response(self.get_serializer(ot).data)

    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        ouverts = OrdreTravail.objects.exclude(
            statut__in=[OrdreTravail.Statut.CLOTURE, OrdreTravail.Statut.ANNULE]
        )
        return Response(
            {
                "ot_ouverts": ouverts.count(),
                "ot_en_cours": OrdreTravail.objects.filter(
                    statut=OrdreTravail.Statut.EN_COURS
                ).count(),
                "ot_critiques": ouverts.filter(priorite=OrdreTravail.Priorite.CRITIQUE).count(),
                "actifs_arret": Actif.objects.filter(
                    statut__in=[Actif.Statut.EN_MAINTENANCE, Actif.Statut.EN_PANNE]
                ).count(),
                "actifs_operationnels": Actif.objects.filter(
                    statut=Actif.Statut.OPERATIONNEL
                ).count(),
                "inspections_prevues": Inspection.objects.filter(
                    statut=Inspection.Statut.PLANIFIEE
                ).count(),
                "cout_total": sum(ot.cout_total for ot in ouverts),
                "heures_total": sum(ot.heures_mo for ot in ouverts),
            }
        )


class InspectionViewSet(viewsets.ModelViewSet):
    queryset = Inspection.objects.select_related("actif", "intervenant", "ot_genere").all()
    serializer_class = InspectionSerializer
    permission_classes = [CanManageMaintenance]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if actif := params.get("actif"):
            qs = qs.filter(actif_id=actif)
        if type_inspection := params.get("type"):
            qs = qs.filter(type_inspection=type_inspection)
        if resultat := params.get("resultat"):
            qs = qs.filter(resultat=resultat)
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        if params.get("prevues") == "1":
            qs = qs.filter(statut=Inspection.Statut.PLANIFIEE)
        return qs

    @action(detail=True, methods=["post"], url_path="realiser")
    def realiser(self, request, pk=None):
        inspection = self.get_object()
        if inspection.statut != Inspection.Statut.PLANIFIEE:
            return Response(
                {"detail": "Seule une inspection planifiée peut être réalisée."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        inspection.statut = Inspection.Statut.REALISEE
        if request.data.get("resultat"):
            inspection.resultat = request.data.get("resultat")
        if request.data.get("constat"):
            inspection.constat = request.data.get("constat")
        if request.data.get("prochaine_inspection"):
            inspection.prochaine_inspection = request.data.get("prochaine_inspection")
        if request.data.get("intervenant"):
            inspection.intervenant_id = request.data.get("intervenant")
        inspection.save()
        return Response(self.get_serializer(inspection).data)

    @action(detail=True, methods=["post"], url_path="creer-ot")
    def creer_ot(self, request, pk=None):
        """Génère un OT correctif depuis une inspection non conforme (5.9.5 → 5.9.4)."""
        inspection = self.get_object()
        if inspection.statut != Inspection.Statut.REALISEE:
            return Response(
                {"detail": "L'inspection doit être réalisée pour générer un OT."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if inspection.ot_genere:
            return Response(
                {"detail": "Un OT a déjà été généré pour cette inspection."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ot = OrdreTravail.objects.create(
            actif=inspection.actif,
            type_ot=OrdreTravail.TypeOT.CORRECTIF,
            priorite=OrdreTravail.Priorite.MOYENNE,
            description=f"Correctif issue de inspection {inspection.code} : {inspection.constat or ''}",
            cause=inspection.constat,
            created_by=request.user,
        )
        inspection.ot_genere = ot
        inspection.save(update_fields=["ot_genere", "updated_at"])
        return Response(
            {"id": str(ot.pk), "code": ot.code, "statut": ot.statut},
            status=status.HTTP_201_CREATED,
        )