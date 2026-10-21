"""API module M1 — Commercial / CRM / CLM (RF-ERP-01…05)."""

from django.core.exceptions import ValidationError as DjangoValidationError
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
    HabilitationRequise,
    Milestone,
    Opportunity,
    ParametreCommercial,
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
    HabilitationRequiseSerializer,
    MilestoneSerializer,
    ParametreCommercialSerializer,
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
from . import ecarts_m1


def _svc(fonction, *args, **kwargs):
    """Appelle un service M1 ; une `ValidationError` Django devient une 400 DRF."""
    try:
        return fonction(*args, **kwargs)
    except DjangoValidationError as e:
        raise DRFValidationError(e.message_dict if hasattr(e, "error_dict") else {"detail": e.messages[0]})


def _entier(valeur, nom, defaut=None):
    if valeur in (None, ""):
        return defaut
    try:
        return int(valeur)
    except (TypeError, ValueError):
        raise DRFValidationError({nom: "Nombre entier attendu."})


def _decimal(valeur, nom):
    from decimal import Decimal, InvalidOperation

    if valeur in (None, ""):
        return None
    try:
        return Decimal(str(valeur))
    except InvalidOperation:
        raise DRFValidationError({nom: "Nombre attendu."})


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

    @action(detail=True, methods=["get"], url_path="vue-360")
    def vue_360(self, request, pk=None):
        """Vue 360° : contacts, historique, score détaillé, signaux faibles, opportunités, offres, affaires, contrats."""
        return Response(ecarts_m1.vue_360(self.get_object(), can_see_amount(request.user)))

    @action(detail=False, methods=["get"])
    def signaux(self, request):
        """Clients actifs : score calculé vs enregistré et signaux faibles (inactivité, relance, pertes, échéance)."""
        return Response({"lignes": ecarts_m1.clients_signaux(),
                         "provisoire": ecarts_m1.provisoires(tuple(c for c in ecarts_m1.PARAMETRES_DEFAUT
                                                                   if c.startswith(("SCORE_", "CLIENT_"))))})

    @action(detail=False, methods=["post"], url_path="recalculer-scores")
    @transaction.atomic
    def recalculer_scores(self, request):
        return Response({"modifies": ecarts_m1.recalculer_scores()})


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

    @action(detail=False, methods=["get"], url_path="pipe-par-profil")
    def pipe_par_profil(self, request):
        """Ventilation du pipe par profil contractuel (marché de travaux, maintenance, GLOBAL RENTAL…)."""
        return Response({"lignes": ecarts_m1.pipe_par_profil(can_see_amount(request.user))})

    @action(detail=False, methods=["get"])
    def alertes(self, request):
        """Opportunités ouvertes sans mouvement depuis N jours ou dont la clôture prévue est dépassée."""
        lignes = [{k: v for k, v in o.items() if k != "owner_id"} for o in ecarts_m1.alertes_opportunites()]
        return Response({"lignes": lignes, "jours": str(ecarts_m1.get_param("OPP_INACTIVITE_JOURS")),
                         "provisoire": ecarts_m1.provisoires(("OPP_INACTIVITE_JOURS",))})

    @action(detail=True, methods=["post"], url_path="changer-etape")
    @transaction.atomic
    def changer_etape(self, request, pk=None):
        """Avance / recule l'étape du funnel (glisser-déposer du pipeline) ; « perdue » enregistre le motif."""
        opp = Opportunity.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        _svc(ecarts_m1.changer_etape, opp, str(request.data.get("stage") or ""), str(request.data.get("motif") or ""))
        return Response(self.get_serializer(opp).data)


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

    @action(detail=True, methods=["get"])
    def structure(self, request, pk=None):
        """Structure de chiffrage : déboursé sec par nature / lot, frais indirects, aléas, prix de revient, marge."""
        return Response(ecarts_m1.structure_chiffrage(self.get_object(), can_see_amount(request.user)))

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

    @action(detail=False, methods=["get"], url_path="criteres-defaut")
    def criteres_defaut(self, request):
        """Critères du formulaire ENG-PR1-01 (provisoires) et seuils Go / Go sous réserve paramétrables."""
        return Response({"criteres": ecarts_m1.CRITERES_RAO_DEFAUT, "seuil_go": str(ecarts_m1.get_param("RAO_SEUIL_GO")),
                         "seuil_reserve": str(ecarts_m1.get_param("RAO_SEUIL_RESERVE")), "provisoire": True})

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def archiver(self, request, pk=None):
        """Formulaire RAO (PDF) archivé en GED pour 10 ans."""
        rao = TenderReview.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        _svc(ecarts_m1.archiver_rao, rao, request.user)
        return Response(self.get_serializer(rao).data)

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
        if not rao.document_id:
            ecarts_m1.archiver_rao(rao, request.user)
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
        affaire, erreur = self._transition(
            Affaire.Status.CONFIRMEE, Affaire.Status.EN_COURS,
            lambda a: controle_crrl(a) or ecarts_m1.controle_habilitations_affaire(a),
        )
        return erreur or Response(self.get_serializer(affaire).data)

    @action(detail=False, methods=["get"])
    def marges(self, request):
        """Marges prévues / réelles par client, profil, affaire ou responsable (CDC M1 §3.4 / §3.7)."""
        par = request.query_params.get("par", "client")
        if par not in MARGE_AXES:
            raise DRFValidationError({"par": f"Valeurs possibles : {', '.join(MARGE_AXES)}."})
        return Response(marges_affaires(par, can_see_amount(request.user)))

    @action(detail=False, methods=["get"])
    def derives(self, request):
        """Dérive des coûts : coût réel (grand livre, axe affaire) vs coût prévu (offre gagnée) à l'avancement."""
        return Response(ecarts_m1.derives_affaires(can_see_amount(request.user)))

    @action(detail=True, methods=["post"], url_path="besoins-achat")
    @transaction.atomic
    def besoins_achat(self, request, pk=None):
        """Génère la DA (M2) des lignes achetables de l'offre gagnée, imputée à l'affaire."""
        affaire = Affaire.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        da = _svc(ecarts_m1.generer_besoins_achat, affaire, request.user)
        return Response({"id": str(da.pk), "code": da.code, "lignes": da.lines.count()}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def achats(self, request, pk=None):
        """DA et BC (M2) imputés au compte analytique de l'affaire, et nombre de bons de sortie (BS) consommés."""
        affaire = self.get_object()
        data = ecarts_m1.achats_affaire(affaire, can_see_amount(request.user))
        data["bons_sortie"] = ecarts_m1.bons_sortie(affaire)
        data["definition_bs"] = ecarts_m1.DEFINITION_BS
        return Response(data)

    @action(detail=True, methods=["get"], url_path="plan-charge")
    def plan_charge(self, request, pk=None):
        """Plan de charge nominatif : personnel des équipes affectées aux OF de l'affaire."""
        return Response({"lignes": ecarts_m1.plan_charge(self.get_object())})

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
    search_fields = ("code", "client__partner__name", "affaire__title",)

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
        if contrat.profile == Contract.Profile.MARCHE_TRAVAUX and contrat.retenue_rate is None:
            contrat.retenue_rate = ecarts_m1.get_param("RETENUE_GARANTIE_PCT")
        manquants = ecarts_m1.controle_profil(contrat)
        if manquants:
            raise DRFValidationError({"detail": " ".join(manquants)})
        contrat.document, contrat.signe_le = document, timezone.now()
        return self._passer(contrat, (Contract.Status.BROUILLON,), Contract.Status.ACTIF)

    @action(detail=True, methods=["get"])
    def calculs(self, request, pk=None):
        """Retenue de garantie, pénalités de retard (?jours_retard=), indexation (?indice=&indice_base=), durée, SLA."""
        q = request.query_params
        jours = _entier(q.get("jours_retard"), "jours_retard", 0)
        if jours < 0:
            raise DRFValidationError({"jours_retard": "Valeur positive attendue."})
        indice, base = _decimal(q.get("indice"), "indice"), _decimal(q.get("indice_base"), "indice_base")
        return Response(ecarts_m1.calculs_contrat(self.get_object(), can_see_amount(request.user), jours, indice, base))

    @action(detail=True, methods=["post"], url_path="generer-echeancier")
    @transaction.atomic
    def generer_echeancier(self, request, pk=None):
        """Échéancier type (jalons facturables mensuels) du contrat en vigueur."""
        contrat = self._contrat()
        if contrat.status not in (Contract.Status.ACTIF, Contract.Status.SUSPENDU):
            raise DRFValidationError({"detail": "Seul un contrat signé (actif) reçoit un échéancier."})
        jalons = _svc(ecarts_m1.generer_echeancier, contrat)
        return Response({"jalons": len(jalons)}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def retenues(self, request, pk=None):
        """Retenue de garantie cumulée sur les factures émises de l'affaire et date de libération."""
        return Response(ecarts_m1.retenues_contrat(self.get_object(), can_see_amount(request.user)))

    @action(detail=True, methods=["get"])
    def habilitations(self, request, pk=None):
        """Conformité du personnel affecté aux habilitations exigées par le contrat (ou son profil)."""
        return Response(ecarts_m1.conformite_habilitations(self.get_object()))

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
        if not revue.document_id:
            ecarts_m1.archiver_rc(revue, request.user)
        return Response(self.get_serializer(revue).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def archiver(self, request, pk=None):
        revue = RevueCommande.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        _svc(ecarts_m1.archiver_rc, revue, request.user)
        return Response(self.get_serializer(revue).data)


CONFIRMATION_PARAM_ROLES = (User.Role.ADMIN, User.Role.PDG, User.Role.DGA, User.Role.DIRECTION)


class ParametreCommercialViewSet(_CommonViewSet):
    """Paramètres M1 provisoires (prédéfinis) : valeur modifiable par le commercial, confirmation par la Direction."""

    serializer_class = ParametreCommercialSerializer
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_queryset(self):
        ecarts_m1.assurer_parametres()
        return ParametreCommercial.objects.all()

    def create(self, request, *args, **kwargs):
        return Response({"detail": "Les paramètres sont prédéfinis : modifiez leur valeur."},
                        status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @action(detail=True, methods=["post"])
    def confirmer(self, request, pk=None):
        if not (request.user.is_staff or request.user.role in CONFIRMATION_PARAM_ROLES):
            return Response({"detail": "Confirmation réservée à la Direction."}, status=status.HTTP_403_FORBIDDEN)
        p = self.get_object()
        p.statut_valeur = ParametreCommercial.StatutValeur.CONFIRME
        p.confirme_par, p.confirme_le = request.user, timezone.now()
        p.save(update_fields=["statut_valeur", "confirme_par", "confirme_le"])
        return Response(self.get_serializer(p).data)


class HabilitationRequiseViewSet(_CommonViewSet):
    serializer_class = HabilitationRequiseSerializer

    def get_queryset(self):
        qs = HabilitationRequise.objects.select_related("contract")
        if contract := self.request.query_params.get("contract"):
            qs = qs.filter(contract_id=contract)
        return qs


class PilotageM1ViewSet(viewsets.ViewSet):
    """Échéances J-90 / J-60 / J-30 (offres, contrats, avenants), relances, indicateurs commerciaux (Couche D)."""

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [can_read_module("commercial")()]
        return [CanManageCommercial()]

    @action(detail=False, methods=["get"])
    def echeances(self, request):
        lignes = [{k: v for k, v in e.items() if k != "destinataire_id"} for e in ecarts_m1.echeances_m1()]
        return Response({"paliers": ecarts_m1.paliers(), "lignes": lignes,
                         "provisoire": ecarts_m1.provisoires(("ECHEANCE_PALIER_1", "ECHEANCE_PALIER_2", "ECHEANCE_PALIER_3"))})

    @action(detail=False, methods=["post"])
    @transaction.atomic
    def relancer(self, request):
        """Envoie maintenant les relances du jour (sinon envoyées après la tâche quotidienne des échéances)."""
        return Response({"notifications": ecarts_m1.relances_commerciales()})

    @action(detail=False, methods=["get"])
    def indicateurs(self, request):
        return Response(ecarts_m1.indicateurs_commerciaux(can_see_amount(request.user)))
