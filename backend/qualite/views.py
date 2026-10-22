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

from .ecarts import (
    conclure_mesures, criteres_defaut, etiquette_pdf, nc_metrologie,
    PARAMETRES_QUALITE_DEFAUT, archiver_dossier_qualite, dossier_qualite_pdf, get_param_qualite, indicateurs,
    rapport_indicateurs_pdf,
)
from .models import (
    CritereControle,
    MesureControle,
    DiffusionWps,
    ParametreQualite,
    PunchItem,
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
    CritereControleSerializer,
    MesureControleSerializer,
    DiffusionWpsSerializer,
    ParametreQualiteSerializer,
    PunchItemSerializer,
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
from .ecarts_a3 import JointTracabiliteMixin


def _as_bool(value):
    """Booléen tolérant multipart (DRF renvoie des chaînes "True"/"False")."""
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("true", "1", "yes")


def _capa_ouvertes(nc):
    return list(nc.actions_correctives.exclude(statut=ActionCorrective.Statut.CLOTUREE).values_list("code", flat=True))


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
        if type_wps := self.request.query_params.get("type"):
            qs = qs.filter(type=type_wps)
        if ordre := _uuid_or_none(self.request.query_params.get("ordre")):
            qs = qs.filter(diffusions__ordre_id=ordre)
        return qs

    def _assert_brouillon(self):
        wps = self.get_object()
        if wps.statut != WpsWpqr.Statut.BROUILLON:
            raise DRFValidationError(f"{wps.code} {wps.get_statut_display().lower()} : procédure scellée (réviser = nouveau WPS).")
        return wps

    def update(self, request, *args, **kwargs):
        self._assert_brouillon()
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._assert_brouillon()
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], permission_classes=[CanValidatePv])
    def valider(self, request, pk=None):
        """Validation d'un WPS/WPQR : QA/QC + hiérarchie ; date et validateur posés par le serveur.
        Un WPS exige un WPQR validé (PQR) qui le qualifie."""
        wps = self.get_object()
        if wps.statut != WpsWpqr.Statut.BROUILLON:
            return Response(
                {"detail": f"WPS {wps.get_statut_display().lower()} : validation impossible."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if wps.type == WpsWpqr.Type.WPS and (wps.wpqr is None or wps.wpqr.statut != WpsWpqr.Statut.VALIDE):
            return Response({"wpqr": "Un WPS se valide sur un WPQR (PQR) validé : renseignez le WPQR support."},
                            status=status.HTTP_400_BAD_REQUEST)
        wps.statut = WpsWpqr.Statut.VALIDE
        wps.date_validation = timezone.localdate()
        wps.validated_by = request.user
        wps.save(update_fields=["statut", "date_validation", "validated_by", "updated_at"])
        return Response(self.get_serializer(wps).data)

    @action(detail=True, methods=["post"], url_path="obsolete", permission_classes=[CanValidatePv])
    @transaction.atomic
    def obsolete(self, request, pk=None):
        """Retire un WPS / WPQR validé (révision, norme changée) : plus utilisable pour un nouveau joint."""
        wps = WpsWpqr.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if wps.statut != WpsWpqr.Statut.VALIDE:
            raise DRFValidationError("Seule une procédure validée devient obsolète.")
        motif = str(request.data.get("motif", "")).strip()
        if not motif:
            raise DRFValidationError({"motif": "Motif d'obsolescence obligatoire."})
        wps.statut = WpsWpqr.Statut.OBSOLETE
        wps.obsolete_le = timezone.now()
        wps.obsolete_motif = motif[:250]
        wps.save(update_fields=["statut", "obsolete_le", "obsolete_motif", "updated_at"])
        return Response(self.get_serializer(wps).data)

    @action(detail=True, methods=["post"], url_path="diffuser")
    def diffuser(self, request, pk=None):
        """Diffuse un WPS validé vers un OF (atelier / chantier M3)."""
        from operations.models import OrdreFabrication

        wps = self.get_object()
        if wps.statut != WpsWpqr.Statut.VALIDE or wps.type != WpsWpqr.Type.WPS:
            raise DRFValidationError("Seul un WPS validé se diffuse vers un OF.")
        ordre = OrdreFabrication.objects.filter(pk=_uuid_or_none(request.data.get("ordre"))).first()
        if ordre is None:
            raise DRFValidationError({"ordre": "OF introuvable."})
        if ordre.status in (OrdreFabrication.Status.CLOTURE, OrdreFabrication.Status.ANNULE):
            raise DRFValidationError({"ordre": f"OF {ordre.code} clos : diffusion inutile."})
        from .ecarts import controle_wps_profil

        if erreur := controle_wps_profil(wps, ordre.affaire):
            raise DRFValidationError({"wps": erreur})
        diffusion, _ = DiffusionWps.objects.get_or_create(wps=wps, ordre=ordre, defaults={"diffuse_par": request.user})
        return Response(DiffusionWpsSerializer(diffusion).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="fichier")
    def fichier(self, request, pk=None):
        """Joint la fiche WPS / PQR (PDF ou image) tant que la procédure est en brouillon."""
        wps = self._assert_brouillon()
        fichier = request.FILES.get("fichier")
        if fichier is None:
            raise DRFValidationError({"fichier": "Fichier attendu (PDF ou image)."})
        if not fichier.name.lower().endswith((".pdf", ".jpg", ".jpeg", ".png")):
            raise DRFValidationError({"fichier": "Formats acceptés : PDF, JPG, PNG."})
        wps.fichier = fichier
        wps.save(update_fields=["fichier", "updated_at"])
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
        if saisi_le := serializer.validated_data.get("saisi_le"):  # saisie terrain synchronisée (CL-OM-08)
            from operations.terrain_a3 import controler_synchro

            controler_synchro(saisi_le, self.request, None, "Contrôle")
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

    TYPES_MESURES = ("peinture", "genie_civil", "electrique", "essai", "tth")

    @action(detail=True, methods=["post"], url_path="mesure")
    @transaction.atomic
    def mesure(self, request, pk=None):
        """Saisit une mesure contre un critère du type de contrôle ; seuils figés, conformité calculée."""
        controle = ControleQualite.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if controle.type_controle not in self.TYPES_MESURES:
            raise DRFValidationError("Mesures structurées : contrôles peinture, génie civil, électricité, essai ou TTH.")
        if controle.statut in (ControleQualite.Statut.VALIDE, ControleQualite.Statut.ANNULE):
            raise DRFValidationError("Contrôle conclu : mesures scellées.")
        critere = CritereControle.objects.filter(
            pk=_uuid_or_none(request.data.get("critere")), type_controle=controle.type_controle, actif=True
        ).first()
        if critere is None:
            raise DRFValidationError({"critere": "Critère inconnu pour ce type de contrôle."})
        try:
            valeur = Decimal(str(request.data.get("valeur")).replace(",", "."))
        except InvalidOperation:
            raise DRFValidationError({"valeur": "Valeur numérique attendue."})
        mesure = MesureControle.objects.create(
            controle=controle, critere=critere, valeur=valeur, mini=critere.mini, maxi=critere.maxi,
            conforme=critere.accepte(valeur), repere=str(request.data.get("repere", ""))[:80], saisi_par=request.user,
        )
        if controle.statut == ControleQualite.Statut.EN_ATTENTE:
            controle.statut = ControleQualite.Statut.EN_COURS
            controle.save(update_fields=["statut", "updated_at"])
        return Response(MesureControleSerializer(mesure).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="conclure")
    @transaction.atomic
    def conclure(self, request, pk=None):
        """Conclusion calculée sur les mesures (non conforme => NC ouverte automatiquement)."""
        controle = ControleQualite.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if controle.statut in (ControleQualite.Statut.VALIDE, ControleQualite.Statut.ANNULE):
            raise DRFValidationError("Contrôle déjà conclu.")
        if not controle.mesures.exists():
            raise DRFValidationError("Aucune mesure saisie.")
        manquants = list(CritereControle.objects.filter(type_controle=controle.type_controle, actif=True)
                         .exclude(mesures__controle=controle).values_list("libelle", flat=True))
        if manquants and not _as_bool(request.data.get("partiel")):
            raise DRFValidationError({"detail": f"Critères non mesurés : {', '.join(manquants)} (confirmer un contrôle partiel)."})
        conclure_mesures(controle, request.user)
        return Response(self.get_serializer(controle).data)


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
        if traitement == NonConformite.Traitement.REJET and nc.type_ncr != "soudage" and not _capa_ouvertes(nc):
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
        if ouvertes := _capa_ouvertes(nc):
            return Response({"detail": f"CAPA non clôturée(s) : {', '.join(ouvertes)} — clôturez-les avant la NC."},
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
        if not reserve and pv.ordre_id and pv.dossier_document_id is None:
            # Réception prononcée : le dossier qualité de l'OF est constitué, scellé et archivé 10 ans (CDC M6.1-14).
            pv.dossier_document = archiver_dossier_qualite(pv, user=request.user)
            pv.date_archivage = timezone.localdate()
            pv.save(update_fields=["dossier_document", "date_archivage", "updated_at"])
        return Response(self.get_serializer(pv).data)

    @action(detail=True, methods=["get"], url_path="dossier")
    def dossier(self, request, pk=None):
        """Dossier qualité (PDF) : joints, contrôles, ITP, épreuves, NC / CAPA, punch list."""
        from hse.views import _pdf_response

        pv = self.get_object()
        return _pdf_response(dossier_qualite_pdf(pv), f"dossier-qualite-{pv.code}.pdf")


class PointInspectionViewSet(viewsets.ModelViewSet):
    """Points d'un ITP : création/édition tant qu'ils sont en attente ; levée tracée (QA/QC)."""

    queryset = PointInspection.objects.select_related("controle", "leve_par").all()
    serializer_class = PointInspectionSerializer
    permission_classes = [CanManageQualite]

    def get_queryset(self):
        qs = super().get_queryset()
        if controle := self.request.query_params.get("controle"):
            qs = qs.filter(controle_id=controle)
        if self.request.query_params.get("en_retard") == "1":
            qs = qs.filter(statut=PointInspection.Statut.EN_ATTENTE, date_prevue__lt=timezone.localdate())
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
        if type_equipement := self.request.query_params.get("type"):
            qs = qs.filter(type_equipement=type_equipement)
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
            type_operation=inst.operation_attendue, organisme=str(request.data.get("organisme", inst.organisme))[:150],
            certificat=str(request.data.get("certificat", ""))[:80], par=request.user,
        )
        if not conforme:
            # Hors tolérance : NC métrologique avec la liste des usages à réévaluer (contrôles, joints, épreuves).
            nc_metrologie(inst, request.user)
        return Response(self.get_serializer(inst).data)

    @action(detail=True, methods=["get"], url_path="etiquette")
    def etiquette(self, request, pk=None):
        from hse.views import _pdf_response

        inst = self.get_object()
        return _pdf_response(etiquette_pdf(inst), f"etiquette-{inst.code}.pdf")


class JointSoudeViewSet(JointTracabiliteMixin, mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                        viewsets.GenericViewSet):
    """Registre des joints : inscription seule (la traçabilité ne se réécrit pas)."""

    queryset = JointSoude.objects.select_related("ordre", "soudeur", "wps", "lot").prefetch_related("lot__certificats").all()
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


class PunchItemViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                       viewsets.GenericViewSet):
    """Punch list de fin de travaux : réserves A (bloquent la libération de l'OF), B, C ; levée tracée."""

    queryset = PunchItem.objects.select_related("ordre").all()
    serializer_class = PunchItemSerializer
    search_fields = ("code", "description", "repere")
    permission_classes = [CanManageQualite]

    def get_queryset(self):
        qs = super().get_queryset()
        if ordre := _uuid_or_none(self.request.query_params.get("ordre")):
            qs = qs.filter(ordre_id=ordre)
        if self.request.query_params.get("ouvertes") == "1":
            qs = qs.filter(statut=PunchItem.Statut.OUVERTE)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"], url_path="lever")
    @transaction.atomic
    def lever(self, request, pk=None):
        item = PunchItem.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if item.statut != PunchItem.Statut.OUVERTE:
            raise DRFValidationError("Réserve déjà levée.")
        item.statut = PunchItem.Statut.LEVEE
        item.leve_par = request.user
        item.leve_le = timezone.now()
        item.commentaire = str(request.data.get("commentaire", ""))[:250]
        item.save()
        return Response(self.get_serializer(item).data)


class ParametreQualiteViewSet(viewsets.ModelViewSet):
    """Paramètres M6 (délai CAPA, escalade, alerte de péremption) : provisoires jusqu'à confirmation QA/QC."""

    queryset = ParametreQualite.objects.all()
    serializer_class = ParametreQualiteSerializer
    permission_classes = [CanValidatePv]
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_queryset(self):
        for code in PARAMETRES_QUALITE_DEFAUT:
            get_param_qualite(code)
        return super().get_queryset()

    def create(self, request, *args, **kwargs):
        return Response({"detail": "Paramètres prédéfinis : modification seulement."}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def perform_update(self, serializer):
        # Une valeur modifiée redevient provisoire jusqu'à sa confirmation.
        serializer.save(statut_valeur=ParametreQualite.StatutValeur.PROVISOIRE, confirme_par=None, confirme_le=None)

    @action(detail=True, methods=["post"], url_path="confirmer")
    def confirmer(self, request, pk=None):
        p = self.get_object()
        p.statut_valeur = ParametreQualite.StatutValeur.CONFIRME
        p.confirme_par = request.user
        p.confirme_le = timezone.now()
        p.save(update_fields=["statut_valeur", "confirme_par", "confirme_le"])
        return Response(self.get_serializer(p).data)


class IndicateursQualiteViewSet(viewsets.ViewSet):
    """Indicateurs qualité (CDC M6.1-15) sur un mois (`?annee=&mois=`) ou une année ; `?export=pdf` = rapport."""

    permission_classes = [CanManageQualite]

    def list(self, request):
        from rest_framework.fields import IntegerField

        params = request.query_params
        annee = IntegerField(min_value=2000, max_value=2100).run_validation(params.get("annee") or timezone.localdate().year)
        mois = params.get("mois")
        mois = IntegerField(min_value=1, max_value=12).run_validation(mois) if mois not in (None, "") else None
        data = indicateurs(annee, mois)
        if params.get("export") == "pdf":
            from hse.views import _pdf_response

            suffixe = f"{annee}-{mois:02d}" if mois else str(annee)
            return _pdf_response(rapport_indicateurs_pdf(data), f"rapport-qualite-{suffixe}.pdf")
        return Response(data)


class PersonnelQualiteViewSet(viewsets.ViewSet):
    """Salariés actifs (code, nom) pour rattacher un soudeur à sa fiche M9, sans ouvrir le module RH."""

    permission_classes = [CanManageQualite]

    def list(self, request):
        from rh_paie.models import Employe

        rows = [
            {"id": str(e.pk), "code": e.code, "nom_complet": e.nom_complet}
            for e in Employe.objects.exclude(statut=Employe.Statut.SORTI).order_by("code")
        ]
        return Response(rows)


class CritereControleViewSet(viewsets.ModelViewSet):
    """Critères d'acceptation (seuils) par type de contrôle : modifiables par QA/QC, provisoires jusqu'à confirmation."""

    queryset = CritereControle.objects.all()
    serializer_class = CritereControleSerializer
    permission_classes = [CanValidatePv]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        criteres_defaut()
        qs = super().get_queryset()
        if type_controle := self.request.query_params.get("type"):
            qs = qs.filter(type_controle=type_controle)
        return qs

    def perform_update(self, serializer):
        serializer.save(statut_valeur=CritereControle.StatutValeur.PROVISOIRE, confirme_par=None, confirme_le=None)

    @action(detail=True, methods=["post"], url_path="confirmer")
    def confirmer(self, request, pk=None):
        c = self.get_object()
        c.statut_valeur = CritereControle.StatutValeur.CONFIRME
        c.confirme_par = request.user
        c.confirme_le = timezone.now()
        c.save(update_fields=["statut_valeur", "confirme_par", "confirme_le"])
        return Response(self.get_serializer(c).data)
