"""API module M12 — Juridique & GED (RF-ERP-B0...B4)."""

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import OpenApiParameter
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from .models import (
    Assurance,
    Caution,
    Contentieux,
    Convention,
    Courrier,
    ActionContentieux,
    DossierGlobalRental,
    JalonContentieux,
    LienDocument,
    ParametreJuridique,
    PieceDossier,
    Reunion,
)
from .serializers import (
    ActionContentieuxSerializer,
    JalonContentieuxSerializer,
    ParametreJuridiqueSerializer,
    PieceDossierSerializer,
    LienDocumentSerializer,
    AssuranceSerializer,
    CautionSerializer,
    ContentieuxSerializer,
    ConventionSerializer,
    CourrierSerializer,
    DossierGlobalRentalSerializer,
    ReunionSerializer,
)
from config.inputs import date_input
from users.permissions import can_read_module
from .services import (
    CanValidateDg,
    CanManageJuridique,
    RECHERCHE_MIN,
    rechercher_documents,
    CanValidateJuridique,
    can_see_amount,
    compute_alertes,
    compute_stats,
)
from . import ecarts


def _verrou(viewset):
    """Objet de l'action relu sous verrou (transition atomique, appeler dans `transaction.atomic`)."""
    obj = viewset.get_object()
    return type(obj).objects.select_for_update(of=("self",)).get(pk=obj.pk)


class DjangoValidationMixin:
    """Convertit les `ValidationError` Django en réponses HTTP 400."""

    def handle_exception(self, exc):
        if isinstance(exc, DjangoValidationError):
            exc = DRFValidationError(getattr(exc, "messages", [str(exc)]))
        return super().handle_exception(exc)


class CourrierViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    """Bureau d'ordre (RF-ERP-B1, proc. 3.3)."""

    queryset = Courrier.objects.select_related("tiers", "document").all()
    serializer_class = CourrierSerializer
    search_fields = ("code", "objet", "reference",)
    permission_classes = [CanManageJuridique]

    def get_queryset(self):
        qs = super().get_queryset()
        sens = self.request.query_params.get("sens")
        statut = self.request.query_params.get("statut")
        if sens:
            qs = qs.filter(sens=sens)
        if statut:
            qs = qs.filter(statut=statut)
        return qs

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)

    @action(detail=True, methods=["post"])
    def enregistrer(self, request, pk=None):
        courrier = self.get_object()
        try:
            courrier.enregistrer()
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        return Response(self.get_serializer(courrier).data)

    @action(detail=True, methods=["post"])
    def classer(self, request, pk=None):
        courrier = self.get_object()
        try:
            courrier.classer()
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        return Response(self.get_serializer(courrier).data)

    @action(detail=True, methods=["post"])
    def archiver(self, request, pk=None):
        courrier = self.get_object()
        try:
            courrier.archiver()
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        return Response(self.get_serializer(courrier).data)


class ConventionViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    """Contrats & conventions (RF-ERP-B2, proc. 3.6 / 8.3)."""

    queryset = Convention.objects.select_related("partenaire", "affaire", "document").all()
    serializer_class = ConventionSerializer
    search_fields = ("code", "titre",)

    def get_permissions(self):
        if self.action in ("signer", "resilier", "cloturer"):
            return [CanValidateJuridique()]
        return [CanManageJuridique()]

    def get_queryset(self):
        qs = super().get_queryset()
        statut = self.request.query_params.get("statut")
        type = self.request.query_params.get("type")
        if statut:
            qs = qs.filter(statut=statut)
        if type:
            qs = qs.filter(type=type)
        return qs

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)

    @action(detail=True, methods=["post"])
    def signer(self, request, pk=None):
        convention = self.get_object()
        try:
            ecarts.controler_signature_convention(convention)
            convention.signer()
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        return Response(self.get_serializer(convention).data)

    @action(detail=True, methods=["post"])
    def cloturer(self, request, pk=None):
        convention = self.get_object()
        try:
            convention.cloturer()
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        return Response(self.get_serializer(convention).data)

    @action(detail=True, methods=["post"])
    def resilier(self, request, pk=None):
        convention = self.get_object()
        try:
            convention.resilier()
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        return Response(self.get_serializer(convention).data)


class ContentieuxViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    """Contentieux (RF-ERP-B3, proc. 8.5)."""

    queryset = Contentieux.objects.select_related("document").all()
    serializer_class = ContentieuxSerializer
    search_fields = ("code", "objet", "partie_adverse",)

    def get_permissions(self):
        if self.action in ("instruire", "cloturer", "avancer_phase"):
            return [CanValidateJuridique()]
        return [CanManageJuridique()]

    def get_queryset(self):
        qs = super().get_queryset()
        statut = self.request.query_params.get("statut")
        nature = self.request.query_params.get("nature")
        if statut:
            qs = qs.filter(statut=statut)
        if nature:
            qs = qs.filter(nature=nature)
        return qs

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)

    @action(detail=True, methods=["post"])
    def instruire(self, request, pk=None):
        contentieux = self.get_object()
        try:
            contentieux.instruire()
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        ecarts.journaliser(contentieux, "statut", "Passage en instruction.", request.user)
        return Response(self.get_serializer(contentieux).data)

    @action(detail=True, methods=["post"])
    def qualifier(self, request, pk=None):
        """Saisie de la juridiction (liste paramétrée) et / ou de la cotation du risque, tracée au journal."""
        serializer = self.get_serializer(self.get_object(), data={
            k: request.data[k] for k in ("juridiction", "probabilite") if k in request.data
        }, partial=True)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            contentieux = _verrou(self)
            champs = []
            for k, v in serializer.validated_data.items():
                setattr(contentieux, k, v)
                champs.append(k)
            if not champs:
                raise DRFValidationError("Juridiction ou probabilité attendue.")
            contentieux.save(update_fields=champs + ["updated_at"])
            ecarts.journaliser(contentieux, "autre", "Qualification : " + ", ".join(
                f"{k} = {getattr(contentieux, k) or '—'}" for k in champs) + ".", request.user)
        return Response(self.get_serializer(contentieux).data)

    @action(detail=True, methods=["post"], url_path="avancer-phase")
    def avancer_phase(self, request, pk=None):
        phase = request.data.get("phase")
        if phase not in Contentieux.Phase.values:
            raise DRFValidationError({"phase": "Phase inconnue."})
        with transaction.atomic():
            contentieux = _verrou(self)
            if contentieux.statut not in (Contentieux.Statut.OUVERT, Contentieux.Statut.EN_INSTRUCTION):
                raise DRFValidationError("Contentieux traité : phase figée.")
            if contentieux.phase == phase:
                raise DRFValidationError("Le contentieux est déjà dans cette phase.")
            ancienne = contentieux.get_phase_display()
            contentieux.phase = phase
            contentieux.save(update_fields=["phase", "updated_at"])
            ecarts.journaliser(
                contentieux, "phase", f"Phase : {ancienne} → {contentieux.get_phase_display()}.", request.user
            )
        return Response(self.get_serializer(contentieux).data)

    @action(detail=True, methods=["post"])
    def cloturer(self, request, pk=None):
        contentieux = self.get_object()
        issue = request.data.get("issue")
        decision = request.data.get("decision", "")
        try:
            contentieux.cloturer(issue, decision)
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        ecarts.journaliser(
            contentieux, "decision", f"Clôture : {contentieux.get_statut_display()}. {decision}".strip(), request.user
        )
        return Response(self.get_serializer(contentieux).data)


class CautionViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    """Cautions & garanties (RF-ERP-B4, proc. 8.6)."""

    queryset = Caution.objects.select_related("emetteur", "convention", "document").all()
    serializer_class = CautionSerializer
    search_fields = ("code", "beneficiaire", "objet",)

    def get_permissions(self):
        if self.action in ("lever", "appeler", "valider_dg"):
            return [CanValidateDg()]
        return [CanManageJuridique()]

    @action(detail=True, methods=["post"], url_path="valider-dg")
    def valider_dg(self, request, pk=None):
        with transaction.atomic():
            obj = _verrou(self)
            if obj.valide_dg_par_id:
                raise DRFValidationError("Déjà validée par la Direction Générale.")
            obj.valide_dg_par = request.user
            obj.valide_dg_le = timezone.now()
            obj.save(update_fields=["valide_dg_par", "valide_dg_le", "updated_at"])
        return Response(self.get_serializer(obj).data)

    def get_queryset(self):
        qs = super().get_queryset()
        statut = self.request.query_params.get("statut")
        if statut:
            qs = qs.filter(statut=statut)
        return qs

    @action(detail=True, methods=["post"])
    def lever(self, request, pk=None):
        caution = self.get_object()
        try:
            ecarts.exiger_validation_dg(caution, "Mainlevée")
            caution.lever()
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        return Response(self.get_serializer(caution).data)

    @action(detail=True, methods=["post"])
    def appeler(self, request, pk=None):
        caution = self.get_object()
        try:
            ecarts.exiger_validation_dg(caution, "Appel de la caution")
            caution.appeler()
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        return Response(self.get_serializer(caution).data)


class AssuranceViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    """Assurances & sinistres (RF-ERP-B4, proc. 8.6)."""

    queryset = Assurance.objects.select_related("assureur", "document").all()
    serializer_class = AssuranceSerializer
    search_fields = ("code", "numero_police",)

    def get_permissions(self):
        # NB : self.action = nom de la MÉTHODE (declarer_sinistre), pas l'url_path (bug corrigé : la permission
        # de déclaration de sinistre ne s'appliquait jamais).
        if self.action in ("renouveler", "resilier", "valider_dg"):
            return [CanValidateDg()]
        if self.action == "declarer_sinistre":
            return [CanValidateJuridique()]
        return [CanManageJuridique()]

    @action(detail=True, methods=["post"], url_path="valider-dg")
    def valider_dg(self, request, pk=None):
        with transaction.atomic():
            obj = _verrou(self)
            if obj.valide_dg_par_id:
                raise DRFValidationError("Déjà validée par la Direction Générale.")
            obj.valide_dg_par = request.user
            obj.valide_dg_le = timezone.now()
            obj.save(update_fields=["valide_dg_par", "valide_dg_le", "updated_at"])
        return Response(self.get_serializer(obj).data)

    def get_queryset(self):
        qs = super().get_queryset()
        statut = self.request.query_params.get("statut")
        if statut:
            qs = qs.filter(statut=statut)
        return qs

    @action(detail=True, methods=["post"])
    def renouveler(self, request, pk=None):
        assurance = self.get_object()
        nouvelle_echeance = date_input(request.data.get("date_echeance"), "date_echeance")
        try:
            if nouvelle_echeance and assurance.date_echeance and nouvelle_echeance <= assurance.date_echeance:
                raise ValueError("La nouvelle échéance doit être postérieure à l'échéance en cours.")
            ecarts.exiger_validation_dg(assurance, "Renouvellement")
            assurance.renouveler(nouvelle_echeance)
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        return Response(self.get_serializer(assurance).data)

    @action(detail=True, methods=["post"])
    def resilier(self, request, pk=None):
        assurance = self.get_object()
        try:
            assurance.resilier()
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        return Response(self.get_serializer(assurance).data)

    @action(detail=True, methods=["post"], url_path="declarer-sinistre")
    def declarer_sinistre(self, request, pk=None):
        assurance = self.get_object()
        detail = request.data.get("detail", "")
        assurance.declarer_sinistre(detail)
        return Response(self.get_serializer(assurance).data)


class ReunionViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    """Réunions & comptes rendus (RF-ERP-B1, proc. 3.7)."""

    queryset = Reunion.objects.prefetch_related("participants").select_related(
        "animateur", "compte_rendu"
    ).all()
    serializer_class = ReunionSerializer
    search_fields = ("code", "objet",)
    permission_classes = [CanManageJuridique]

    def get_queryset(self):
        qs = super().get_queryset()
        statut = self.request.query_params.get("statut")
        if statut:
            qs = qs.filter(statut=statut)
        return qs

    def perform_create(self, serializer):
        reunion = serializer.save()
        if self.request.data.get("animateur"):
            reunion.animateur_id = self.request.data["animateur"]
            reunion.save(update_fields=["animateur"])
        participants = self.request.data.get("participants")
        if isinstance(participants, list):
            reunion.participants.set(participants)

    def perform_update(self, serializer):
        reunion = serializer.save()
        participants = self.request.data.get("participants")
        if isinstance(participants, list):
            reunion.participants.set(participants)

    @action(detail=True, methods=["post"])
    def tenir(self, request, pk=None):
        reunion = self.get_object()
        compte_rendu = request.data.get("compte_rendu")
        try:
            reunion.tenir(compte_rendu)
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        return Response(self.get_serializer(reunion).data)

    @action(detail=True, methods=["post"])
    def cloturer(self, request, pk=None):
        reunion = self.get_object()
        try:
            reunion.cloturer()
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        return Response(self.get_serializer(reunion).data)

    @action(detail=False, methods=["get"])
    def stats(self, request):
        return Response(compute_stats())


class DossierGlobalRentalViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    """Dossier intra-groupe GLOBAL RENTAL (RF-ERP-B4, fil rouge compte 618)."""

    queryset = DossierGlobalRental.objects.select_related("partenaire_gr", "affaire").all()
    serializer_class = DossierGlobalRentalSerializer
    search_fields = ("code", "reference_contrat", "objet",)
    permission_classes = [CanManageJuridique]

    def get_queryset(self):
        qs = super().get_queryset()
        statut = self.request.query_params.get("statut")
        if statut:
            qs = qs.filter(statut=statut)
        return qs

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)

    @action(detail=True, methods=["post"])
    def ouvrir(self, request, pk=None):
        dossier = self.get_object()
        try:
            if ecarts.parametre("bloquer_dossier_incomplet"):
                manquantes = ecarts.completude("gr", dossier)["manquantes"]
                if manquantes:
                    raise ValueError("Dossier GR incomplet : pièces manquantes " + ", ".join(manquantes) + ".")
            dossier.ouvrir()
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        return Response(self.get_serializer(dossier).data)

    @action(detail=True, methods=["post"])
    def mandat(self, request, pk=None):
        fin = date_input(request.data.get("mandat_date_fin"), "mandat_date_fin")
        if fin is None:
            raise DRFValidationError({"mandat_date_fin": "Date de fin du mandat obligatoire."})
        with transaction.atomic():
            dossier = _verrou(self)
            if dossier.statut == DossierGlobalRental.Statut.CLOTURE:
                raise DRFValidationError("Dossier clôturé.")
            dossier.mandat_date_fin = fin
            reference = (request.data.get("mandat_reference") or "").strip()
            if reference:
                dossier.mandat_reference = reference[:120]
            dossier.save(update_fields=["mandat_date_fin", "mandat_reference", "updated_at"])
        return Response(self.get_serializer(dossier).data)

    @action(detail=True, methods=["post"])
    def revoir(self, request, pk=None):
        with transaction.atomic():
            dossier = _verrou(self)
            if dossier.statut == DossierGlobalRental.Statut.CLOTURE:
                raise DRFValidationError("Dossier clôturé.")
            dossier.date_revue = timezone.localdate()
            dossier.revu_par = request.user
            dossier.save(update_fields=["date_revue", "revu_par", "updated_at"])
        return Response(self.get_serializer(dossier).data)

    @action(detail=True, methods=["post"])
    def cloturer(self, request, pk=None):
        dossier = self.get_object()
        try:
            dossier.cloturer()
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        return Response(self.get_serializer(dossier).data)


@extend_schema(
    responses={200: OpenApiTypes.OBJECT},
    description="Alertes J-90 / J-60 / J-30 / expirées (RF-ERP-B0).",
)
class AlertesViewSet(viewsets.ViewSet):
    """Alertes J-90 / J-60 / J-30 / expirées (RF-ERP-B0)."""

    def get_permissions(self):
        if self.action == "notifier":
            return [CanValidateJuridique()]
        return [can_read_module("juridique")()]

    def list(self, request):
        return Response(compute_alertes())

    @action(detail=False, methods=["post"])
    def notifier(self, request):
        """Envoie maintenant les notifications des paliers paramétrés (J-60 compris) ; dédupliqué par jour."""
        return Response({"envoyees": ecarts.notifier_echeances_juridiques()})


class LienDocumentViewSet(viewsets.ModelViewSet):
    """Liens document GED ↔ objet métier M1-M11 (recherche juridique interconnectée, clôture M12)."""

    serializer_class = LienDocumentSerializer
    permission_classes = [CanManageJuridique]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        from documents.services import visible_documents

        qs = LienDocument.objects.select_related("document").filter(
            document__in=visible_documents(self.request.user)
        )
        params = self.request.query_params
        if document := params.get("document"):
            qs = qs.filter(document_id=document)
        if objet_type := params.get("objet_type"):
            qs = qs.filter(objet_type=objet_type)
        if objet_id := params.get("objet_id"):
            qs = qs.filter(objet_id=objet_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class RechercheJuridiqueView(viewsets.ViewSet):
    """Recherche transverse : documents GED (ACL respectées) retrouvés par leur texte ou par un objet métier lié."""

    permission_classes = [can_read_module("juridique")]

    @extend_schema(
        parameters=[
            OpenApiParameter("q", type=str, required=True),
            OpenApiParameter("module", type=str, required=False),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def list(self, request):
        q = (request.query_params.get("q") or "").strip()
        if len(q) < RECHERCHE_MIN:
            raise DRFValidationError(f"Saisissez au moins {RECHERCHE_MIN} caractères.")
        module = request.query_params.get("module") or None
        docs = rechercher_documents(request.user, q, module)
        return Response({
            "q": q,
            "documents": [
                {
                    "id": str(d.pk), "title": d.title, "status": d.status, "reference": d.reference,
                    "counterparty": d.counterparty,
                    "liens": [
                        {"objet_type": l.objet_type, "objet_id": l.objet_id, "objet_label": l.objet_label, "module": l.module}
                        for l in d.liens_metier.all()
                    ],
                }
                for d in docs
            ],
        })


# --------------------------------------------------------------------------------------------------
# Écarts M12
# --------------------------------------------------------------------------------------------------
class ParametreJuridiqueViewSet(viewsets.ReadOnlyModelViewSet):
    """Paramètres provisoires M12 : lecture module ; modification / confirmation par la Direction Générale."""

    serializer_class = ParametreJuridiqueSerializer

    def get_permissions(self):
        if self.action in ("modifier", "confirmer"):
            return [CanValidateDg()]
        return [CanManageJuridique()]

    def get_queryset(self):
        ecarts.assurer_parametres()
        return ParametreJuridique.objects.filter(cle__in=list(ecarts.PARAMETRES_DEFAUT))

    @action(detail=True, methods=["post"])
    def modifier(self, request, pk=None):
        import json

        valeur = request.data.get("valeur")
        if isinstance(valeur, str):
            try:
                valeur = json.loads(valeur)
            except ValueError:
                raise DRFValidationError({"valeur": "JSON invalide."})
        with transaction.atomic():
            param = _verrou(self)
            try:
                param.valeur = ecarts.valider_valeur(param.cle, valeur)
            except ValueError as exc:
                raise DRFValidationError({"valeur": str(exc)})
            param.provisoire = True
            param.modifie_par = request.user
            param.modifie_le = timezone.now()
            param.confirme_par = None
            param.confirme_le = None
            param.save()
        return Response(self.get_serializer(param).data)

    @action(detail=True, methods=["post"])
    def confirmer(self, request, pk=None):
        with transaction.atomic():
            param = _verrou(self)
            if not param.provisoire:
                raise DRFValidationError("Paramètre déjà confirmé.")
            param.provisoire = False
            param.confirme_par = request.user
            param.confirme_le = timezone.now()
            param.save(update_fields=["provisoire", "confirme_par", "confirme_le"])
        return Response(self.get_serializer(param).data)


class JalonContentieuxViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    """Échéancier des contentieux (jalons)."""

    serializer_class = JalonContentieuxSerializer
    permission_classes = [CanManageJuridique]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = JalonContentieux.objects.select_related("contentieux")
        if c := self.request.query_params.get("contentieux"):
            qs = qs.filter(contentieux_id=c)
        if st := self.request.query_params.get("statut"):
            qs = qs.filter(statut=st)
        return qs

    def perform_create(self, serializer):
        jalon = serializer.save(cree_par=self.request.user)
        ecarts.journaliser(
            jalon.contentieux, "autre", f"Jalon planifié : {jalon.libelle} ({jalon.date_prevue:%d/%m/%Y}).",
            self.request.user,
        )

    def _cloturer(self, request, statut, verbe):
        with transaction.atomic():
            jalon = _verrou(self)
            if jalon.statut != JalonContentieux.Statut.A_VENIR:
                raise DRFValidationError("Jalon déjà réalisé ou annulé.")
            jalon.statut = statut
            if statut == JalonContentieux.Statut.REALISE:
                jalon.date_realisee = timezone.localdate()
            jalon.save(update_fields=["statut", "date_realisee"])
            ecarts.journaliser(jalon.contentieux, "autre", f"Jalon {verbe} : {jalon.libelle}.", request.user)
        return Response(self.get_serializer(jalon).data)

    @action(detail=True, methods=["post"])
    def realiser(self, request, pk=None):
        return self._cloturer(request, JalonContentieux.Statut.REALISE, "réalisé")

    @action(detail=True, methods=["post"])
    def annuler(self, request, pk=None):
        return self._cloturer(request, JalonContentieux.Statut.ANNULE, "annulé")


class ActionContentieuxViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    """Journal chronologique des actions d'un contentieux (ajout seulement, inaltérable)."""

    serializer_class = ActionContentieuxSerializer
    permission_classes = [CanManageJuridique]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = ActionContentieux.objects.select_related("contentieux", "auteur")
        if c := self.request.query_params.get("contentieux"):
            qs = qs.filter(contentieux_id=c)
        return qs

    def perform_create(self, serializer):
        serializer.save(auteur=self.request.user)


class PieceDossierViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    """Pièces versées aux dossiers (complétude contentieux / conventions / dossiers GR)."""

    serializer_class = PieceDossierSerializer
    permission_classes = [CanManageJuridique]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        from documents.services import visible_documents

        qs = PieceDossier.objects.select_related("document").filter(
            document__in=visible_documents(self.request.user)
        )
        if t := self.request.query_params.get("dossier_type"):
            qs = qs.filter(dossier_type=t)
        if d := self.request.query_params.get("dossier_id"):
            qs = qs.filter(dossier_id=d)
        return qs

    def perform_create(self, serializer):
        serializer.save(ajoute_par=self.request.user)


@extend_schema(responses={200: OpenApiTypes.OBJECT}, description="Vue Risk : cotation probabilité × montant.")
class RisquesViewSet(viewsets.ViewSet):
    """Vue Risk : contentieux cotés (probabilité × montant en jeu) et engagements par caution."""

    permission_classes = [can_read_module("juridique")]

    def list(self, request):
        return Response(ecarts.vue_risques(can_see_amount(request.user)))
