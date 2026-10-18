"""Vues API M8 — Maintenance & GMAO (parc machines & équipements)."""

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from config.inputs import choice_input, date_input, fk_input
from users.models import User

from .models import Actif, Inspection, OrdreTravail, ParametreMaintenance, PlanPreventif
from .preventif import declencher_plans, rearmer_plan
from .serializers import (
    ActifSerializer,
    InspectionSerializer,
    OrdreTravailSerializer,
    ParametreMaintenanceSerializer,
    PlanPreventifSerializer,
)
from .services import (
    PARAMETRES_DEFAUT,
    CanManageMaintenance,
    IsConfirmateurMaintenance,
    fiabilite_actifs,
    get_param_maintenance,
)


def _montant_positif(raw, field):
    """Décimal >= 0 saisi dans une transition (heures, coûts) : 400 explicite au lieu d'une erreur 500."""
    try:
        value = Decimal(str(raw).replace(",", "."))
    except (InvalidOperation, ValueError):
        raise ValidationError({field: "Nombre attendu."})
    if not value.is_finite() or value < 0:
        raise ValidationError({field: "Valeur positive attendue."})
    return value


def _choix(raw, choices, field):
    if raw not in choices.values:
        raise ValidationError({field: f"Valeur inconnue : {raw!r}."})
    return raw


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

    @action(detail=False, methods=["get"], url_path="fiabilite")
    def fiabilite(self, request):
        """MTBF / MTTR / disponibilité par machine (période d'observation paramétrable, valeurs provisoires signalées)."""
        return Response(fiabilite_actifs())

    @action(detail=True, methods=["post"], url_path="releve-compteur")
    @transaction.atomic
    def releve_compteur(self, request, pk=None):
        """Relevé du compteur machine ; un seuil préventif dépassé génère l'OT (lot 14, CDC M8 §13.11)."""
        actif = Actif.objects.select_for_update().get(pk=self.get_object().pk)
        if actif.is_global_rental:
            raise ValidationError(
                {"valeur": "Compteur GLOBAL RENTAL en lecture seule : le relevé se saisit en logistique (M4)."}
            )
        if actif.compteur_type == Actif.Compteur.AUCUN:
            raise ValidationError({"valeur": "Cet équipement n'a pas de compteur."})
        valeur = _montant_positif(request.data.get("valeur"), "valeur")
        if valeur < actif.compteur_value:
            raise ValidationError(
                {"valeur": f"Le compteur ne peut pas reculer (valeur actuelle {actif.compteur_value})."}
            )
        actif.compteur_value = valeur
        actif.save(update_fields=["compteur_value", "updated_at"])
        ots = declencher_plans([actif], user=request.user)
        data = self.get_serializer(actif).data
        data["ot_generes"] = [ot.code for ot in ots]
        return Response(data)


class PlanPreventifViewSet(viewsets.ModelViewSet):
    queryset = PlanPreventif.objects.select_related("actif", "actif__equipement_gr").all()
    serializer_class = PlanPreventifSerializer
    permission_classes = [CanManageMaintenance]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if actif := params.get("actif"):
            qs = qs.filter(actif_id=actif)
        if params.get("en_vigueur") == "1":
            qs = qs.filter(en_vigueur=True)
        return qs

    @action(detail=False, methods=["post"], url_path="declencher")
    def declencher(self, request):
        """Déclenchement manuel des plans échus (même règle que la tâche quotidienne)."""
        return Response({"ot_generes": [ot.code for ot in declencher_plans(user=request.user)]})


class OrdreTravailViewSet(viewsets.ModelViewSet):
    queryset = OrdreTravail.objects.select_related("actif", "demandeur", "technicien").all()
    serializer_class = OrdreTravailSerializer
    permission_classes = [CanManageMaintenance]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, demandeur=self.request.user)

    def perform_destroy(self, instance):
        if instance.statut in OrdreTravail.STATUTS_SCELLES:
            raise ValidationError({"detail": "OT clôturé ou archivé : pièce scellée, non supprimable."})
        instance.delete()

    def _locked(self):
        return OrdreTravail.objects.select_for_update().select_related("actif").get(pk=self.get_object().pk)

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
            qs = qs.exclude(statut__in=OrdreTravail.STATUTS_CLOS)
        return qs

    @action(detail=True, methods=["post"], url_path="planifier")
    @transaction.atomic
    def planifier(self, request, pk=None):
        ot = self._locked()
        if ot.statut != OrdreTravail.Statut.DEMANDE:
            return Response(
                {"detail": "Seul un OT demandé peut être planifié."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        date_planifiee = date_input(request.data.get("date_planifiee"), "date_planifiee")
        technicien = fk_input(request.data.get("technicien"), User.objects.filter(is_active=True), "technicien")
        ot.statut = OrdreTravail.Statut.PLANIFIE
        if date_planifiee:
            ot.date_planifiee = date_planifiee
        if technicien:
            ot.technicien = technicien
        if request.data.get("priorite"):
            ot.priorite = _choix(request.data.get("priorite"), OrdreTravail.Priorite, "priorite")
        ot.save()
        return Response(self.get_serializer(ot).data)

    @action(detail=True, methods=["post"], url_path="demarrer")
    @transaction.atomic
    def demarrer(self, request, pk=None):
        ot = self._locked()
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
    @transaction.atomic
    def terminer(self, request, pk=None):
        ot = self._locked()
        if ot.statut != OrdreTravail.Statut.EN_COURS:
            return Response(
                {"detail": "Seul un OT en cours peut être terminé."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Saisies validées AVANT tout changement d'état.
        heures_mo = request.data.get("heures_mo")
        if heures_mo not in (None, ""):
            ot.heures_mo = _montant_positif(heures_mo, "heures_mo")
        cout_pieces = request.data.get("cout_pieces")
        if cout_pieces not in (None, ""):
            ot.cout_pieces = _montant_positif(cout_pieces, "cout_pieces")
        if request.data.get("decision"):
            ot.decision = _choix(request.data.get("decision"), OrdreTravail.Decision, "decision")
        ot.statut = OrdreTravail.Statut.TERMINE
        ot.date_fin = timezone.now()
        if request.data.get("rapport"):
            ot.rapport = request.data.get("rapport")
        ot.save()
        return Response(self.get_serializer(ot).data)

    @action(detail=True, methods=["post"], url_path="cloturer")
    @transaction.atomic
    def cloturer(self, request, pk=None):
        ot = self._locked()
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
        rearmer_plan(ot)
        return Response(self.get_serializer(ot).data)

    @action(detail=True, methods=["post"], url_path="archiver")
    @transaction.atomic
    def archiver(self, request, pk=None):
        """5e état du cycle OT (CDC M8 §13.4) : archivage d'un OT clôturé, rapport d'intervention exigé."""
        ot = self._locked()
        if ot.statut != OrdreTravail.Statut.CLOTURE:
            return Response(
                {"detail": "Seul un OT clôturé peut être archivé."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not ot.rapport.strip():
            return Response(
                {"rapport": "Rapport d'intervention requis avant archivage."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ot.statut = OrdreTravail.Statut.ARCHIVE
        ot.archive_le = timezone.now()
        ot.archive_par = request.user
        ot.save(update_fields=["statut", "archive_le", "archive_par", "updated_at"])
        return Response(self.get_serializer(ot).data)

    @action(detail=True, methods=["post"], url_path="annuler")
    @transaction.atomic
    def annuler(self, request, pk=None):
        ot = self._locked()
        if ot.statut in OrdreTravail.STATUTS_CLOS:
            return Response(
                {"detail": "L'OT est déjà clos ou annulé."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        etait_en_cours = ot.statut == OrdreTravail.Statut.EN_COURS
        ot.statut = OrdreTravail.Statut.ANNULE
        ot.save()
        # L'OT avait mis l'équipement en maintenance : l'annulation le libère, sauf autre OT en cours dessus.
        if (
            etait_en_cours
            and ot.actif.statut == Actif.Statut.EN_MAINTENANCE
            and not ot.actif.ordres_travail.filter(statut=OrdreTravail.Statut.EN_COURS).exclude(pk=ot.pk).exists()
        ):
            ot.actif.statut = Actif.Statut.OPERATIONNEL
            ot.actif.save(update_fields=["statut", "updated_at"])
        return Response(self.get_serializer(ot).data)

    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        ouverts = OrdreTravail.objects.exclude(statut__in=OrdreTravail.STATUTS_CLOS)
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
        # Saisies validées avant tout changement d'état (400 explicite, jamais de valeur hors choix stockée).
        resultat = choice_input(request.data.get("resultat"), Inspection.Resultat, "resultat")
        prochaine = date_input(request.data.get("prochaine_inspection"), "prochaine_inspection")
        intervenant = fk_input(request.data.get("intervenant"), User.objects.filter(is_active=True), "intervenant")
        inspection.statut = Inspection.Statut.REALISEE
        if resultat:
            inspection.resultat = resultat
        if request.data.get("constat"):
            inspection.constat = request.data.get("constat")
        if prochaine:
            inspection.prochaine_inspection = prochaine
        if intervenant:
            inspection.intervenant = intervenant
        inspection.save()
        return Response(self.get_serializer(inspection).data)

    @action(detail=True, methods=["post"], url_path="creer-ot")
    @transaction.atomic
    def creer_ot(self, request, pk=None):
        """Génère un OT correctif depuis une inspection non conforme (5.9.5 → 5.9.4)."""
        # Verrou : un double clic ne crée pas deux OT pour la même inspection.
        inspection = Inspection.objects.select_for_update().get(pk=self.get_object().pk)
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

class ParametreMaintenanceViewSet(viewsets.ModelViewSet):
    """Paramètres M8 modifiables par ETSL ; création/suppression interdites (définis par le code)."""

    queryset = ParametreMaintenance.objects.all()
    serializer_class = ParametreMaintenanceSerializer
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_queryset(self):
        for code in PARAMETRES_DEFAUT:
            get_param_maintenance(code)
        return super().get_queryset()

    def get_permissions(self):
        if getattr(self, "action", None) == "confirmer":
            return [IsConfirmateurMaintenance()]
        return [CanManageMaintenance()]

    def create(self, request, *args, **kwargs):
        return Response({"detail": "Les paramètres sont prédéfinis : modifiez leur valeur."}, status=405)

    @action(detail=True, methods=["post"], url_path="confirmer")
    def confirmer(self, request, pk=None):
        p = self.get_object()
        p.statut_valeur = ParametreMaintenance.StatutValeur.CONFIRME
        p.confirme_par = request.user
        p.confirme_le = timezone.now()
        p.save(update_fields=["statut_valeur", "confirme_par", "confirme_le"])
        return Response(self.get_serializer(p).data)
