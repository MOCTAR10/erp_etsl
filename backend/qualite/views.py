"""Vues API M6 — Qualité industrielle, Soudage & Contrôle Qualité / Inspection."""

import hashlib
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from integrations.idempotency import idempotent
from rest_framework import mixins, serializers as drf_serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from .models import (
    Etalonnage,
    EpreuvePression,
    ImageControle,
    InstrumentMesure,
    JointSoude,
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
    EpreuvePressionSerializer,
    ImageControleSerializer,
    InstrumentMesureSerializer,
    JointSoudeSerializer,
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


def _uuid_or_none(value):
    import uuid

    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


class SoudeurViewSet(viewsets.ModelViewSet):
    queryset = Soudeur.objects.all()
    serializer_class = SoudeurSerializer
    search_fields = ("code", "nom", "prenoms", "matricule",)
    permission_classes = [CanManageQualite]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("active") == "1":
            qs = qs.filter(is_active=True)
        return qs


class QualificationSoudeurViewSet(viewsets.ModelViewSet):
    queryset = QualificationSoudeur.objects.select_related("soudeur").all()
    serializer_class = QualificationSoudeurSerializer
    search_fields = ("code", "soudeur__nom", "soudeur__matricule")
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
    search_fields = ("code", "reference",)
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
    search_fields = ("code", "point_controle",)
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

    @action(detail=True, methods=["post"], url_path="approuver")
    @transaction.atomic
    def approuver(self, request, pk=None):
        """Approuve l'ITP (préalable au soudage) : plan figé, approbation tracée."""
        if not can_validate_pv(request.user):
            return Response({"detail": "Approbation réservée à QA/QC et à la hiérarchie."},
                            status=status.HTTP_403_FORBIDDEN)
        itp = ControleQualite.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if itp.type_controle != ControleQualite.TypeControle.ITP:
            raise DRFValidationError("Seul un contrôle de type ITP s'approuve.")
        if itp.approuve_le:
            raise DRFValidationError("ITP déjà approuvé.")
        if not itp.points.exists():
            raise DRFValidationError("ITP sans point d'inspection : rien à approuver.")
        itp.approuve_par = request.user
        itp.approuve_le = timezone.now()
        itp.save(update_fields=["approuve_par", "approuve_le", "updated_at"])
        return Response(self.get_serializer(itp).data)

    @idempotent
    def create(self, request, *args, **kwargs):  # contrôle / CND saisi sur le terrain, rejouable
        return super().create(request, *args, **kwargs)


class NonConformiteViewSet(viewsets.ModelViewSet):
    queryset = NonConformite.objects.select_related(
        "controle", "decided_by"
    ).prefetch_related("actions_correctives").all()
    serializer_class = NonConformiteSerializer
    search_fields = ("code",)
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
        if traitement == NonConformite.Traitement.REJET and nc.type_ncr != "soudage":
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
        if nc.type_ncr == "soudage":
            # NCR-SD : seule une CND de recontrôle validée et conforme clôt la non-conformité.
            recontrole = ControleQualite.objects.filter(pk=_uuid_or_none(request.data.get("recontrole"))).first()
            if recontrole is None:
                return Response({"detail": "NCR-SD : renseignez le re-CND (contrôle CND de recontrôle)."},
                                status=status.HTTP_400_BAD_REQUEST)
            if (
                recontrole.type_controle != ControleQualite.TypeControle.CND
                or recontrole.statut != ControleQualite.Statut.VALIDE
                or recontrole.resultat != ControleQualite.Resultat.CONFORME
            ):
                return Response({"detail": "Le re-CND doit être un contrôle CND validé et conforme."},
                                status=status.HTTP_400_BAD_REQUEST)
            nc.recontrole = recontrole
        nc.statut = NonConformite.Statut.CLOTUREE
        nc.archive = True
        nc.save()
        return Response(self.get_serializer(nc).data)


class ActionCorrectiveViewSet(viewsets.ModelViewSet):
    queryset = ActionCorrective.objects.select_related(
        "non_conformite", "responsable"
    ).all()
    serializer_class = ActionCorrectiveSerializer
    search_fields = ("code",)
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
    search_fields = ("code", "intitule",)
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


class InstrumentMesureViewSet(viewsets.ModelViewSet):
    queryset = InstrumentMesure.objects.prefetch_related("etalonnages").all()
    serializer_class = InstrumentMesureSerializer
    search_fields = ("code", "designation", "numero_serie",)
    permission_classes = [CanManageQualite]

    def get_queryset(self):
        qs = super().get_queryset()
        if jours := self.request.query_params.get("a_etalonner"):
            try:
                limite = timezone.localdate() + timedelta(days=int(jours))
            except ValueError:
                raise DRFValidationError({"a_etalonner": "Nombre de jours attendu."})
            qs = qs.filter(echeance_etalonnage__lte=limite)
        return qs

    @action(detail=True, methods=["post"], url_path="etalonner")
    @transaction.atomic
    def etalonner(self, request, pk=None):
        """Enregistre un étalonnage : hors tolérance => usage bloqué ; conforme => nouvelle échéance, déblocage."""
        inst = InstrumentMesure.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        conforme = _as_bool(request.data.get("conforme", True))
        aujourdhui = timezone.localdate()
        echeance = None
        if conforme:
            raw = request.data.get("echeance")
            if not raw:
                raise DRFValidationError({"echeance": "Nouvelle échéance requise pour un étalonnage conforme."})
            echeance = drf_serializers.DateField().run_validation(raw)
            if echeance <= aujourdhui:
                raise DRFValidationError({"echeance": "L'échéance doit être postérieure à aujourd'hui."})
            inst.statut = InstrumentMesure.Statut.ACTIF
            inst.date_etalonnage = aujourdhui
            inst.echeance_etalonnage = echeance
        else:
            inst.statut = InstrumentMesure.Statut.BLOQUE
        inst.save()
        Etalonnage.objects.create(
            instrument=inst, date=aujourdhui, echeance=echeance, conforme=conforme,
            certificat=str(request.data.get("certificat", ""))[:80], par=request.user,
        )
        return Response(self.get_serializer(inst).data)


class JointSoudeViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                        viewsets.GenericViewSet):
    """Registre des joints : inscription seule (la traçabilité ne se réécrit pas)."""

    queryset = JointSoude.objects.select_related("ordre", "soudeur", "wps").all()
    serializer_class = JointSoudeSerializer
    search_fields = ("code", "repere",)
    permission_classes = [CanManageQualite]

    def get_queryset(self):
        qs = super().get_queryset()
        if ordre := self.request.query_params.get("ordre"):
            qs = qs.filter(ordre_id=ordre)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ImageControleViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                           viewsets.GenericViewSet):
    """Archive des films / images CND : dépôt et lecture, jamais de modification ni suppression."""

    queryset = ImageControle.objects.all()
    serializer_class = ImageControleSerializer
    permission_classes = [CanManageQualite]

    def get_queryset(self):
        qs = super().get_queryset()
        if controle := self.request.query_params.get("controle"):
            qs = qs.filter(controle_id=controle)
        return qs

    def perform_create(self, serializer):
        fichier = serializer.validated_data["fichier"]
        digest = hashlib.sha256()
        for chunk in fichier.chunks():
            digest.update(chunk)
        fichier.seek(0)
        serializer.save(created_by=self.request.user, sha256=digest.hexdigest())


class EpreuvePressionViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                             viewsets.GenericViewSet):
    queryset = EpreuvePression.objects.select_related("ordre").all()
    serializer_class = EpreuvePressionSerializer
    search_fields = ("code",)
    permission_classes = [CanManageQualite]

    def get_queryset(self):
        qs = super().get_queryset()
        if ordre := self.request.query_params.get("ordre"):
            qs = qs.filter(ordre_id=ordre)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def _en_cours(self, pk):
        ep = EpreuvePression.objects.select_for_update(of=("self",)).get(pk=pk)
        if ep.statut == EpreuvePression.Statut.CONCLUE:
            raise DRFValidationError("Épreuve conclue : relevés scellés.")
        return ep

    @action(detail=True, methods=["post"], url_path="releve")
    @transaction.atomic
    def releve(self, request, pk=None):
        ep = self._en_cours(self.get_object().pk)
        try:
            point = {
                "minute": int(request.data["minute"]),
                "pression": str(Decimal(str(request.data["pression"]))),
                "temperature": str(Decimal(str(request.data.get("temperature", "0")))),
            }
        except (KeyError, ValueError, InvalidOperation):
            raise DRFValidationError("Relevé attendu : minute, pression, temperature (nombres).")
        if ep.releves and point["minute"] <= ep.releves[-1]["minute"]:
            raise DRFValidationError({"minute": "Les relevés se saisissent par minute croissante."})
        ep.releves = [*ep.releves, point]
        ep.save(update_fields=["releves"])
        return Response(self.get_serializer(ep).data)

    @action(detail=True, methods=["post"], url_path="conclure")
    @transaction.atomic
    def conclure(self, request, pk=None):
        """Conclusion calculée sur la courbe : maintien >= durée, pression d'essai atteinte, chute <= admissible."""
        ep = self._en_cours(self.get_object().pk)
        if len(ep.releves) < 2:
            raise DRFValidationError("Au moins deux relevés P/T sont nécessaires.")
        if ep.releves[-1]["minute"] - ep.releves[0]["minute"] < ep.duree_minutes:
            raise DRFValidationError(f"Maintien insuffisant : {ep.duree_minutes} min requises.")
        pressions = [Decimal(r["pression"]) for r in ep.releves]
        chute = max(pressions) - pressions[-1]
        ok = max(pressions) >= ep.pression_essai and chute <= ep.chute_max
        ep.resultat = "conforme" if ok else "non_conforme"
        ep.statut = EpreuvePression.Statut.CONCLUE
        ep.conclu_par = request.user
        ep.conclu_le = timezone.now()
        ep.save()
        return Response(self.get_serializer(ep).data)
