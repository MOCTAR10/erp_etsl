"""API module M1 — Commercial / CRM / CLM (RF-ERP-01…05)."""

from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from .models import (
    Avenant,
    Affaire,
    ClientProfile,
    Contract,
    ContractService,
    Estimate,
    EstimateLine,
    EstimateOption,
    Milestone,
    Opportunity,
    SoumissionEvent,
    RevueCommande,
    TenderReview,
)
from .serializers import (
    AvenantSerializer,
    AffaireSerializer,
    ClientProfileSerializer,
    ContractSerializer,
    ContractServiceSerializer,
    EstimateLineSerializer,
    EstimateOptionSerializer,
    EstimateSerializer,
    MilestoneSerializer,
    OpportunitySerializer,
    SoumissionEventSerializer,
    RevueCommandeSerializer,
    TenderReviewSerializer,
)
from users.models import User
from users.permissions import can_read_module
from config.inputs import fk_input
from documents.models import Document

from .services import (
    MARGE_AXES,
    CanManageCommercial,
    can_see_amount,
    controle_crrl,
    controle_document_contractuel,
    marges_affaires,
    pipeline_stats,
)


class _CommonViewSet(viewsets.ModelViewSet):
    """Lecture authentifiée ; écriture réservée aux rôles commerciaux."""

    http_method_names = ["get", "post", "patch", "delete"]

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [can_read_module("commercial")()]
        return [CanManageCommercial()]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["can_view_amount"] = can_see_amount(self.request.user)
        return context


class ClientProfileViewSet(_CommonViewSet):
    serializer_class = ClientProfileSerializer

    def get_queryset(self):
        qs = ClientProfile.objects.select_related("partner").all()
        segment = self.request.query_params.get("segment")
        if segment:
            qs = qs.filter(segment=segment)
        if self.request.query_params.get("active") is not None:
            active = self.request.query_params["active"].lower() in ("1", "true", "yes")
            qs = qs.filter(is_active=active)
        return qs


class OpportunityViewSet(_CommonViewSet):
    serializer_class = OpportunitySerializer
    search_fields = ("code", "subject", "client__partner__name",)

    def get_queryset(self):
        qs = Opportunity.objects.select_related("client__partner", "owner").all()
        stage = self.request.query_params.get("stage")
        client = self.request.query_params.get("client")
        if stage:
            qs = qs.filter(stage=stage)
        if client:
            qs = qs.filter(client_id=client)
        if self.request.query_params.get("active") is not None:
            active = self.request.query_params["active"].lower() in ("1", "true", "yes")
            qs = qs.filter(is_active=active)
        return qs

    @action(detail=False, methods=["get"], url_path="pipeline")
    def pipeline(self, request):
        """Pilotage M1.4 — pipeline par étape, taux de conversion, marge par segment."""
        return Response(pipeline_stats())


class EstimateViewSet(_CommonViewSet):
    serializer_class = EstimateSerializer
    search_fields = ("code", "title", "client__partner__name",)

    def get_queryset(self):
        qs = Estimate.objects.select_related("opportunity", "client__partner", "currency")
        status_ = self.request.query_params.get("status")
        if status_:
            qs = qs.filter(status=status_)
        if self.request.query_params.get("global_rental") is not None:
            gr = self.request.query_params["global_rental"].lower() in ("1", "true", "yes")
            qs = qs.filter(is_global_rental=gr)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_destroy(self, instance):
        if instance.status != Estimate.Status.BROUILLON:
            raise DRFValidationError({"detail": "Offre émise : non supprimable (traçabilité des versions)."})
        instance.delete()

    def _offre(self):
        return Estimate.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)

    def _decider(self, offre, depuis, vers, **champs):
        if offre.status not in depuis:
            raise DRFValidationError({"detail": f"Offre {offre.get_status_display().lower()} : action impossible."})
        offre.status = vers
        for nom, valeur in champs.items():
            setattr(offre, nom, valeur)
        offre.save()
        return Response(self.get_serializer(offre).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def soumettre(self, request, pk=None):
        """Émission au client : l'offre doit être chiffrée (option ou ligne) ; elle devient une version scellée."""
        offre = self._offre()
        if not offre.montant_offre:
            raise DRFValidationError({"detail": "Offre non chiffrée : ajoutez au moins une option ou une ligne."})
        return self._decider(offre, (Estimate.Status.BROUILLON,), Estimate.Status.SOUMISE, soumise_le=timezone.now())

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def reviser(self, request, pk=None):
        """Révision d'une offre émise : nouvelle version brouillon (CDC M1 §3.5), l'ancienne est remplacée."""
        offre = self._offre()
        if offre.status != Estimate.Status.SOUMISE:
            raise DRFValidationError({"detail": "Seule une offre soumise se révise (un brouillon se modifie directement)."})
        nouvelle = offre.reviser(request.user)
        return Response(self.get_serializer(nouvelle).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def gagner(self, request, pk=None):
        return self._decider(self._offre(), (Estimate.Status.SOUMISE,), Estimate.Status.GAGNEE, decision_le=timezone.now())

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def perdre(self, request, pk=None):
        motif = str(request.data.get("motif") or "").strip()
        if not motif:
            raise DRFValidationError({"motif": "Motif de perte obligatoire (retour d'expérience commercial)."})
        return self._decider(self._offre(), (Estimate.Status.SOUMISE,), Estimate.Status.PERDUE,
                             decision_le=timezone.now(), motif_perte=motif[:250])

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def annuler(self, request, pk=None):
        return self._decider(self._offre(), (Estimate.Status.BROUILLON, Estimate.Status.SOUMISE), Estimate.Status.ANNULEE,
                             decision_le=timezone.now())


class EstimateOptionViewSet(_CommonViewSet):
    serializer_class = EstimateOptionSerializer

    def get_queryset(self):
        qs = EstimateOption.objects.all()
        estimate = self.request.query_params.get("estimate")
        if estimate:
            qs = qs.filter(estimate_id=estimate)
        return qs

    def perform_destroy(self, instance):
        if instance.estimate.status != Estimate.Status.BROUILLON:
            raise DRFValidationError({"detail": "Offre émise : version scellée."})
        instance.delete()


class EstimateLineViewSet(_CommonViewSet):
    serializer_class = EstimateLineSerializer

    def get_queryset(self):
        qs = EstimateLine.objects.select_related("article", "unit").all()
        estimate = self.request.query_params.get("estimate")
        if estimate:
            qs = qs.filter(estimate_id=estimate)
        return qs

    def perform_destroy(self, instance):
        if instance.estimate.status != Estimate.Status.BROUILLON:
            raise DRFValidationError({"detail": "Offre émise : version scellée."})
        instance.delete()


class TenderReviewViewSet(_CommonViewSet):
    serializer_class = TenderReviewSerializer

    def get_queryset(self):
        qs = TenderReview.objects.select_related("client", "estimate").all()
        for param, field in (("estimate", "estimate_id"), ("client", "client_id")):
            value = self.request.query_params.get(param)
            if value:
                qs = qs.filter(**{field: value})
        return qs

    def perform_create(self, serializer):
        serializer.save(reviewed_by=self.request.user, reviewed_at=timezone.now())

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def soumettre(self, request, pk=None):
        """Soumission de l'offre : interdite en No-Go ; un Go sous réserve exige une justification (CDC M1 §3.8)."""
        rao = TenderReview.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if rao.review_status in (TenderReview.Status.SOUMIS, TenderReview.Status.ARCHIVE):
            return Response({"detail": "Revue déjà soumise ou archivée."}, status=status.HTTP_400_BAD_REQUEST)
        if not rao.decision_rao:
            return Response({"detail": "Notez les critères de la revue avant de soumettre."}, status=status.HTTP_400_BAD_REQUEST)
        if rao.decision_rao == "no_go":
            return Response({"detail": f"No-Go (note {rao.score} % < 50 %) : offre non soumise."}, status=status.HTTP_400_BAD_REQUEST)
        justification = (request.data.get("decision") or rao.decision or "").strip()
        if rao.decision_rao == "go_reserve" and not justification:
            return Response({"decision": f"Go sous réserve (note {rao.score} %) : justification obligatoire."},
                            status=status.HTTP_400_BAD_REQUEST)
        rao.decision = justification
        rao.review_status = TenderReview.Status.SOUMIS
        rao.save()
        return Response(self.get_serializer(rao).data)


class AffaireViewSet(_CommonViewSet):
    serializer_class = AffaireSerializer
    search_fields = ("code", "title", "client__partner__name",)

    def get_queryset(self):
        qs = Affaire.objects.select_related("opportunity", "client__partner", "currency")
        status_ = self.request.query_params.get("status")
        if status_:
            qs = qs.filter(status=status_)
        if self.request.query_params.get("global_rental") is not None:
            gr = self.request.query_params["global_rental"].lower() in ("1", "true", "yes")
            qs = qs.filter(is_global_rental=gr)
        return qs

    def _transition(self, depuis, vers, controle=None):
        affaire = Affaire.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if affaire.status != depuis:
            return None, Response({"detail": f"Affaire {affaire.get_status_display().lower()} : action impossible."},
                                  status=status.HTTP_400_BAD_REQUEST)
        if controle:
            blocage = controle(affaire)
            if blocage:
                return None, Response({"detail": blocage}, status=status.HTTP_400_BAD_REQUEST)
        affaire.status = vers
        affaire.save(update_fields=["status", "updated_at"])
        return affaire, None

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def confirmer(self, request, pk=None):
        """Confirmation : revue de commande validée obligatoire, puis génération automatique de l'OF (CDC M1 §3.10)."""
        affaire, erreur = self._transition(Affaire.Status.BROUILLON, Affaire.Status.CONFIRMEE, controle_revue_commande)
        if erreur:
            return erreur
        affaire.assurer_compte_analytique()
        generer_of(affaire, request.user)
        return Response(self.get_serializer(affaire).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def demarrer(self, request, pk=None):
        """Démarrage : CRRL (réunion de lancement tenue, compte-rendu en GED) exigé — CDC M1 §3.6."""
        affaire, erreur = self._transition(Affaire.Status.CONFIRMEE, Affaire.Status.EN_COURS, controle_crrl)
        return erreur or Response(self.get_serializer(affaire).data)

    @action(detail=False, methods=["get"])
    def marges(self, request):
        """Marges prévues / réelles par client, profil, affaire ou responsable (CDC M1 §3.4 / §3.7)."""
        par = request.query_params.get("par", "client")
        if par not in MARGE_AXES:
            raise DRFValidationError({"par": f"Valeurs possibles : {', '.join(MARGE_AXES)}."})
        return Response(marges_affaires(par, can_see_amount(request.user)))

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def cloturer(self, request, pk=None):
        affaire, erreur = self._transition(Affaire.Status.EN_COURS, Affaire.Status.CLOTUREE)
        return erreur or Response(self.get_serializer(affaire).data)


class MilestoneViewSet(_CommonViewSet):
    serializer_class = MilestoneSerializer

    def get_queryset(self):
        qs = Milestone.objects.select_related("affaire").all()
        affaire = self.request.query_params.get("affaire")
        if affaire:
            qs = qs.filter(affaire_id=affaire)
        return qs

    @action(detail=False, methods=["get"], url_path="a-facturer")
    def a_facturer(self, request):
        """Sortie vers M10 : jalons réalisés, valorisés et non encore facturés (échéancier contractuel)."""
        qs = self.get_queryset().filter(status=Milestone.Status.FAIT, montant__gt=0, facture_le__isnull=True)
        return Response(self.get_serializer(qs, many=True).data)


class ContractViewSet(_CommonViewSet):
    serializer_class = ContractSerializer
    search_fields = ("code", "client__partner__name",)

    def get_queryset(self):
        qs = Contract.objects.select_related("client__partner", "currency", "affaire").all()
        profile = self.request.query_params.get("profile")
        if profile:
            qs = qs.filter(profile=profile)
        expiring = self.request.query_params.get("expiring")
        if expiring:
            days = int(expiring)
            qs = qs.filter(end_date__isnull=False)
            qs = qs.filter(
                end_date__lte=timezone.localdate() + timezone.timedelta(days=days),
                end_date__gte=timezone.localdate(),
            ).exclude(status=Contract.Status.CLOTURE)
            return qs
        if self.request.query_params.get("active") is not None:
            active = self.request.query_params["active"].lower() in ("1", "true", "yes")
            qs = qs.filter(status=Contract.Status.ACTIF if active else Contract.Status.BROUILLON)
        return qs

    def _contrat(self):
        return Contract.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)

    def _passer(self, contrat, depuis, vers):
        if contrat.status not in depuis:
            raise DRFValidationError({"detail": f"Contrat {contrat.get_status_display().lower()} : action impossible."})
        contrat.status = vers
        contrat.save()
        return Response(self.get_serializer(contrat).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def activer(self, request, pk=None):
        """Activation = contrat signé électroniquement et archivé 10 ans (CDC M1 §3.5 / §3.11) ; il est ensuite scellé."""
        contrat = self._contrat()
        if contrat.status != Contract.Status.BROUILLON:
            raise DRFValidationError({"detail": "Seul un contrat en brouillon s'active."})
        document = fk_input(request.data.get("document"), Document.objects.select_related("type", "current_version"), "document")
        motif = controle_document_contractuel(document)
        if motif:
            raise DRFValidationError({"document": motif})
        contrat.document, contrat.signe_le = document, timezone.now()
        return self._passer(contrat, (Contract.Status.BROUILLON,), Contract.Status.ACTIF)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def suspendre(self, request, pk=None):
        return self._passer(self._contrat(), (Contract.Status.ACTIF,), Contract.Status.SUSPENDU)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def reprendre(self, request, pk=None):
        return self._passer(self._contrat(), (Contract.Status.SUSPENDU,), Contract.Status.ACTIF)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def cloturer(self, request, pk=None):
        return self._passer(self._contrat(), (Contract.Status.ACTIF, Contract.Status.SUSPENDU), Contract.Status.CLOTURE)


class AvenantViewSet(_CommonViewSet):
    """Avenants (versioning contractuel) : brouillon modifiable, signature = application au contrat puis scellement."""

    serializer_class = AvenantSerializer

    def get_queryset(self):
        qs = Avenant.objects.select_related("contract")
        if contract := self.request.query_params.get("contract"):
            qs = qs.filter(contract_id=contract)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_destroy(self, instance):
        if instance.statut == Avenant.Statut.SIGNE:
            raise DRFValidationError({"detail": "Avenant signé : pièce scellée."})
        instance.delete()

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def signer(self, request, pk=None):
        avenant = Avenant.objects.select_for_update(of=("self",)).select_related("contract").get(pk=self.get_object().pk)
        if avenant.statut != Avenant.Statut.BROUILLON:
            raise DRFValidationError({"detail": "Avenant déjà signé."})
        document = fk_input(request.data.get("document"), Document.objects.select_related("type", "current_version"), "document")
        motif = controle_document_contractuel(document)
        if motif:
            raise DRFValidationError({"document": motif})
        contrat = Contract.objects.select_for_update().get(pk=avenant.contract_id)
        if contrat.status not in (Contract.Status.ACTIF, Contract.Status.SUSPENDU):
            raise DRFValidationError({"detail": "Le contrat n'est plus en vigueur."})
        if avenant.nouvelle_date_fin:
            contrat.end_date = avenant.nouvelle_date_fin
            contrat.save(update_fields=["end_date", "updated_at"])
        avenant.statut, avenant.document, avenant.signe_le = Avenant.Statut.SIGNE, document, timezone.now()
        avenant.save()
        return Response(self.get_serializer(avenant).data)


class ContractServiceViewSet(_CommonViewSet):
    serializer_class = ContractServiceSerializer

    def get_queryset(self):
        qs = ContractService.objects.select_related("contract").all()
        contract = self.request.query_params.get("contract")
        if contract:
            qs = qs.filter(contract_id=contract)
        return qs


class SoumissionEventViewSet(_CommonViewSet):
    serializer_class = SoumissionEventSerializer

    def get_queryset(self):
        qs = SoumissionEvent.objects.select_related("client__partner", "opportunity")
        for param, field in (("client", "client_id"), ("opportunity", "opportunity_id"), ("estimate", "estimate_id")):
            value = self.request.query_params.get(param)
            if value:
                qs = qs.filter(**{field: value})
        return qs

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


REVUE_COMPLETE_ROLES = (User.Role.ADMIN, User.Role.PDG, User.Role.DGA, User.Role.DIRECTION)


def controle_revue_commande(affaire):
    revue = RevueCommande.objects.filter(affaire=affaire).first()
    if revue is None or revue.statut != RevueCommande.Statut.VALIDEE:
        return f"Affaire {affaire.code} : revue de commande non validée — confirmation bloquée (CDC M1 §3.8)."
    return None


def generer_of(affaire, user):
    """Affaire confirmée → OF prévu (atelier / chantier selon le type d'affaire), sans doublon (CDC M1 §3.10, M3 §6.5)."""
    from operations.models import OrdreFabrication

    if OrdreFabrication.objects.filter(affaire=affaire).exists():
        return None
    scope = OrdreFabrication.Scope.CHANTIER if affaire.affaire_type == Affaire.AffaireType.CHANTIER else OrdreFabrication.Scope.ATELIER
    return OrdreFabrication.objects.create(
        label=affaire.title, affaire=affaire, scope=scope, status=OrdreFabrication.Status.PREVU,
        planned_start=affaire.start_date, planned_end=affaire.end_date, created_by=user,
    )


class RevueCommandeViewSet(_CommonViewSet):
    serializer_class = RevueCommandeSerializer

    def get_queryset(self):
        qs = RevueCommande.objects.select_related("affaire").all()
        if affaire := self.request.query_params.get("affaire"):
            qs = qs.filter(affaire_id=affaire)
        return qs

    def perform_update(self, serializer):
        if serializer.instance.statut != RevueCommande.Statut.EN_ATTENTE:
            raise DRFValidationError("Revue de commande déjà tranchée : non modifiable.")
        serializer.save()

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def valider(self, request, pk=None):
        """Revue légère : rôle commercial ; revue complète : Direction + commentaire obligatoire."""
        revue = RevueCommande.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if revue.statut != RevueCommande.Statut.EN_ATTENTE:
            return Response({"detail": "Revue déjà tranchée."}, status=status.HTTP_400_BAD_REQUEST)
        commentaire = (request.data.get("commentaire") or revue.commentaire or "").strip()
        if revue.type_revue == RevueCommande.Type.COMPLETE:
            if not (request.user.is_staff or request.user.role in REVUE_COMPLETE_ROLES):
                return Response(
                    {"detail": f"Revue complète (Δ prix {revue.delta_prix_pct} %, Δ délai {revue.delta_delai_jours} j) : "
                               "validation réservée à la Direction."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if not commentaire:
                return Response({"commentaire": "Revue complète : commentaire de revue obligatoire."},
                                status=status.HTTP_400_BAD_REQUEST)
        revue.statut = RevueCommande.Statut.VALIDEE
        revue.commentaire = commentaire
        revue.valide_par = request.user
        revue.valide_le = timezone.now()
        revue.save()
        return Response(self.get_serializer(revue).data)
