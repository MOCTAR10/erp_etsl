"""API module M3 — Opérations (Atelier + Chantier) (RF-ERP-20…23)."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from integrations.idempotency import idempotent
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from .models import (
    AffectationEquipe,
    CapaciteAtelier,
    Equipe,
    PresenceChantier,
    DossierOperationnel,
    GammeOperatoire,
    GammeOperation,
    OrdreFabrication,
    PointageChantier,
    SituationTravaux,
)
from .serializers import (
    AffectationEquipeSerializer,
    CapaciteAtelierSerializer,
    EquipeSerializer,
    PresenceChantierSerializer,
    DossierOperationnelSerializer,
    GammeOperatoireSerializer,
    GammeOperationSerializer,
    OrdreFabricationSerializer,
    PointageChantierSerializer,
    SituationTravauxSerializer,
)
from users.permissions import can_read_module
from .cloture import figer_dossier, transferer_paie, valider_pointage
from .services import CanManageOperations, can_see_amount, charge_stats


class _CommonViewSet(viewsets.ModelViewSet):
    """Lecture authentifiée ; écriture réservée aux rôles Opérations."""

    http_method_names = ["get", "post", "patch", "delete"]

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [can_read_module("operations")()]
        return [CanManageOperations()]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["can_view_amount"] = can_see_amount(self.request.user)
        return context


class GammeViewSet(_CommonViewSet):
    serializer_class = GammeOperatoireSerializer
    search_fields = ("code", "label",)

    def get_queryset(self):
        qs = GammeOperatoire.objects.all()
        status_ = self.request.query_params.get("status")
        if status_:
            qs = qs.filter(status=status_)
        return qs


class GammeOperationViewSet(_CommonViewSet):
    serializer_class = GammeOperationSerializer

    def get_queryset(self):
        qs = GammeOperation.objects.select_related("gamme").all()
        gamme = self.request.query_params.get("gamme")
        if gamme:
            qs = qs.filter(gamme_id=gamme)
        return qs


class OrdreFabricationViewSet(_CommonViewSet):
    serializer_class = OrdreFabricationSerializer
    search_fields = ("code", "label",)

    def get_queryset(self):
        qs = OrdreFabrication.objects.select_related(
            "affaire", "gamme", "article", "responsible"
        )
        status_ = self.request.query_params.get("status")
        if status_:
            qs = qs.filter(status=status_)
        scope = self.request.query_params.get("scope")
        if scope:
            qs = qs.filter(scope=scope)
        affaire = self.request.query_params.get("affaire")
        if affaire:
            qs = qs.filter(affaire_id=affaire)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def _transition(self, depuis, vers, controle=None):
        of = OrdreFabrication.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if of.status not in depuis:
            return Response({"detail": f"OF {of.get_status_display().lower()} : action impossible."},
                            status=status.HTTP_400_BAD_REQUEST)
        if controle:
            blocage = controle(of)
            if blocage:
                return Response({"detail": blocage}, status=status.HTTP_400_BAD_REQUEST)
        of.status = vers
        of.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(of).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def lancer(self, request, pk=None):
        return self._transition([OrdreFabrication.Status.PREVU], OrdreFabrication.Status.LANCE)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def demarrer(self, request, pk=None):
        return self._transition([OrdreFabrication.Status.LANCE], OrdreFabrication.Status.EN_COURS, controle_demarrage)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def terminer(self, request, pk=None):
        return self._transition([OrdreFabrication.Status.EN_COURS], OrdreFabrication.Status.TERMINE)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def liberer(self, request, pk=None):
        """Libération (clôture) : conformité qualité obligatoire (CDC M3 §6.8, M6 §8.10)."""
        reponse = self._transition([OrdreFabrication.Status.TERMINE], OrdreFabrication.Status.CLOTURE, controle_liberation)
        if reponse.status_code == status.HTTP_200_OK:
            figer_dossier(OrdreFabrication.objects.get(pk=pk))  # dossier opérationnel scellé, archivage 10 ans
        return reponse

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def annuler(self, request, pk=None):
        return self._transition(
            [OrdreFabrication.Status.PREVU, OrdreFabrication.Status.LANCE, OrdreFabrication.Status.EN_COURS],
            OrdreFabrication.Status.ANNULE,
        )

    @action(detail=False, methods=["get"], url_path="charge")
    def charge(self, request):
        """Plan de charge & capacité atelier (RF-ERP-23)."""
        return Response(charge_stats())


class CapaciteAtelierViewSet(_CommonViewSet):
    serializer_class = CapaciteAtelierSerializer
    queryset = CapaciteAtelier.objects.all()


class EquipeViewSet(_CommonViewSet):
    serializer_class = EquipeSerializer

    def get_queryset(self):
        qs = Equipe.objects.prefetch_related("membres")
        metier = self.request.query_params.get("metier")
        return qs.filter(metier=metier) if metier else qs


class AffectationEquipeViewSet(_CommonViewSet):
    serializer_class = AffectationEquipeSerializer

    def get_queryset(self):
        qs = AffectationEquipe.objects.select_related("equipe", "ordre")
        for param, champ in (("ordre", "ordre_id"), ("equipe", "equipe_id"), ("statut", "statut")):
            valeur = self.request.query_params.get(param)
            if valeur:
                qs = qs.filter(**{champ: valeur})
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def _assert_planifiee(self):
        if self.get_object().statut != AffectationEquipe.Statut.PLANIFIEE:
            raise DRFValidationError("Affectation mobilisée ou terminée : non modifiable ni supprimable.")

    def update(self, request, *args, **kwargs):
        self._assert_planifiee()
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._assert_planifiee()
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def mobiliser(self, request, pk=None):
        """Fiche de mobilisation : atteste la mobilisation de l'équipe (serveur) ; l'OF ne doit pas être clos."""
        aff = AffectationEquipe.objects.select_for_update(of=("self",)).select_related("ordre").get(pk=self.get_object().pk)
        if aff.statut != AffectationEquipe.Statut.PLANIFIEE:
            raise DRFValidationError("Seule une affectation planifiée peut être mobilisée.")
        if aff.ordre.status in (OrdreFabrication.Status.CLOTURE, OrdreFabrication.Status.ANNULE):
            raise DRFValidationError(f"OF {aff.ordre.code} clos ou annulé : mobilisation impossible.")
        aff.statut = AffectationEquipe.Statut.MOBILISEE
        aff.mobilise_par = request.user
        aff.mobilise_le = timezone.now()
        aff.save(update_fields=["statut", "mobilise_par", "mobilise_le"])
        return Response(self.get_serializer(aff).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def terminer(self, request, pk=None):
        aff = AffectationEquipe.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if aff.statut != AffectationEquipe.Statut.MOBILISEE:
            raise DRFValidationError("Seule une affectation mobilisée peut être terminée.")
        aff.statut = AffectationEquipe.Statut.TERMINEE
        aff.save(update_fields=["statut"])
        return Response(self.get_serializer(aff).data)


class PresenceChantierViewSet(_CommonViewSet):
    serializer_class = PresenceChantierSerializer

    def get_queryset(self):
        qs = PresenceChantier.objects.select_related("ordre", "employe")
        for param, champ in (("ordre", "ordre_id"), ("employe", "employe_id"), ("statut", "statut")):
            valeur = self.request.query_params.get(param)
            if valeur:
                qs = qs.filter(**{champ: valeur})
        if self.request.query_params.get("from"):
            qs = qs.filter(date__gte=self.request.query_params["from"])
        if self.request.query_params.get("to"):
            qs = qs.filter(date__lte=self.request.query_params["to"])
        return qs

    def perform_create(self, serializer):
        serializer.save(releve_par=self.request.user)


class DossierOperationnelViewSet(viewsets.ReadOnlyModelViewSet):
    """Dossiers opérationnels scellés à la libération des OF (lecture seule)."""

    serializer_class = DossierOperationnelSerializer
    queryset = DossierOperationnel.objects.select_related("ordre")

    def get_permissions(self):
        return [can_read_module("operations")()]


class PointageChantierViewSet(_CommonViewSet):
    serializer_class = PointageChantierSerializer
    search_fields = ("code", "worker_name",)

    def get_queryset(self):
        qs = PointageChantier.objects.select_related("ordre", "worker").all()
        ordre = self.request.query_params.get("ordre")
        if ordre:
            qs = qs.filter(ordre_id=ordre)
        status_ = self.request.query_params.get("status")
        if status_:
            qs = qs.filter(status=status_)
        if self.request.query_params.get("from"):
            qs = qs.filter(date__gte=self.request.query_params["from"])
        if self.request.query_params.get("to"):
            qs = qs.filter(date__lte=self.request.query_params["to"])
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @idempotent
    def create(self, request, *args, **kwargs):  # saisie terrain rejouable (hors-ligne)
        return super().create(request, *args, **kwargs)


    def _assert_saisi(self):
        if self.get_object().status != PointageChantier.Status.SAISI:
            raise DRFValidationError("Pointage validé ou transféré en paie : non modifiable ni supprimable.")

    def update(self, request, *args, **kwargs):
        self._assert_saisi()
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._assert_saisi()
        return super().destroy(request, *args, **kwargs)

    def _pointage_action(self, fonction, *args):
        pointage = self.get_object()
        try:
            fonction(pointage, *args)
        except DjangoValidationError as exc:
            raise DRFValidationError(exc.messages)
        return Response(self.get_serializer(pointage).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def valider(self, request, pk=None):
        """Validation par un tiers du saisisseur (séparation des tâches)."""
        return self._pointage_action(valider_pointage, request.user)

    @action(detail=True, methods=["post"], url_path="transferer-paie")
    @transaction.atomic
    def transferer_paie(self, request, pk=None):
        """Sortie vers M9 : crée la saisie temps de paie (idempotent)."""
        return self._pointage_action(transferer_paie)


class SituationTravauxViewSet(_CommonViewSet):
    serializer_class = SituationTravauxSerializer
    search_fields = ("code", "label",)

    def get_queryset(self):
        qs = SituationTravaux.objects.select_related("affaire", "created_by", "validated_by").all()
        status_ = self.request.query_params.get("status")
        if status_:
            qs = qs.filter(status=status_)
        affaire = self.request.query_params.get("affaire")
        if affaire:
            qs = qs.filter(affaire_id=affaire)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    LOCKED = (SituationTravaux.Status.VALIDEE, SituationTravaux.Status.FACTUREE)

    def _assert_unlocked(self):
        if self.get_object().status in self.LOCKED:
            raise DRFValidationError("Situation validée ou facturée : non modifiable ni supprimable.")

    def update(self, request, *args, **kwargs):
        self._assert_unlocked()
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._assert_unlocked()
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def soumettre(self, request, pk=None):
        """Brouillon → soumise à validation (circuit : le créateur soumet, un tiers valide)."""
        situation = SituationTravaux.objects.select_for_update().get(pk=self.get_object().pk)
        if situation.status != SituationTravaux.Status.BROUILLON:
            raise DRFValidationError("Seule une situation en brouillon peut être soumise.")
        situation.status = SituationTravaux.Status.SOUMISE
        situation.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(situation).data)

    @action(detail=True, methods=["post"], url_path="validate")
    @transaction.atomic
    def validate(self, request, pk=None):
        """Validation d'une situation de travaux (RF-ERP-22) — une seule fois, par un tiers du créateur."""
        situation = SituationTravaux.objects.select_for_update().get(pk=self.get_object().pk)
        if situation.created_by_id and situation.created_by_id == request.user.id:
            raise DRFValidationError("Séparation des tâches : le créateur d'une situation ne peut pas la valider.")
        if situation.status not in (
            SituationTravaux.Status.BROUILLON,
            SituationTravaux.Status.SOUMISE,
        ):
            raise DRFValidationError("Situation déjà validée ou facturée.")
        situation.status = SituationTravaux.Status.VALIDEE
        situation.validated_by = request.user
        situation.validated_at = timezone.now()
        situation.save(update_fields=["status", "validated_by", "validated_at", "updated_at"])
        return Response(self.get_serializer(situation).data)


    @action(detail=False, methods=["get"], url_path="a-facturer")
    def a_facturer(self, request):
        """Sortie vers M10 : situations validées, valorisées et non encore facturées."""
        qs = self.get_queryset().filter(status=SituationTravaux.Status.VALIDEE, amount__gt=0)
        return Response(self.get_serializer(qs, many=True).data)

    @action(detail=True, methods=["post"], url_path="marquer-facturee")
    @transaction.atomic
    def marquer_facturee(self, request, pk=None):
        """Retour de M10 : référence de la facture émise ; la situation est ensuite scellée."""
        situation = SituationTravaux.objects.select_for_update().get(pk=self.get_object().pk)
        ref = str(request.data.get("facture_ref", "")).strip()
        if situation.status != SituationTravaux.Status.VALIDEE:
            raise DRFValidationError("Seule une situation validée peut être facturée.")
        if not ref:
            raise DRFValidationError({"facture_ref": "La référence de la facture est obligatoire."})
        situation.status = SituationTravaux.Status.FACTUREE
        situation.facture_ref = ref
        situation.facture_le = timezone.localdate()
        situation.save(update_fields=["status", "facture_ref", "facture_le", "updated_at"])
        return Response(self.get_serializer(situation).data)


def controle_demarrage(of):
    """Démarrage d'un OF : permis HSE en vigueur pour un chantier (CDC M3 §6.8, M7 §9.10) et soudeurs affectés
    qualifiés à la date du jour (CDC M6 §8.11). Retourne le motif de blocage, ou None."""
    from hse.models import PermisTravail
    from qualite.models import QualificationSoudeur

    jour = timezone.localdate()
    if of.scope == OrdreFabrication.Scope.CHANTIER:
        permis_ok = PermisTravail.objects.filter(
            ordre=of, statut__in=[PermisTravail.Statut.VALIDE, PermisTravail.Statut.ACTIF], date_debut__lte=jour,
        ).filter(Q(date_fin__isnull=True) | Q(date_fin__gte=jour)).exists()
        if not permis_ok:
            return f"OF chantier {of.code} : aucun permis de travail HSE en vigueur — démarrage interdit (CDC M3 §6.8)."
    non_qualifies = [
        str(s) for s in of.soudeurs.all()
        if not QualificationSoudeur.objects.filter(
            soudeur=s, statut=QualificationSoudeur.Statut.VALIDE, date_validite__gte=jour
        ).exists()
    ]
    if non_qualifies:
        return f"Soudeur(s) sans qualification valide : {', '.join(non_qualifies)} — démarrage interdit (CDC M6 §8.11)."
    return None


def controle_liberation(of):
    """Libération : au moins un contrôle qualité validé conforme, aucun contrôle en attente ou non conforme, aucune NC
    ouverte sur l'OF (CDC M3 §6.11 « aucun OF libéré sans conformité qualité »)."""
    from qualite.models import ControleQualite, NonConformite

    controles = ControleQualite.objects.filter(ordre=of).exclude(statut=ControleQualite.Statut.ANNULE)
    if not controles.filter(statut=ControleQualite.Statut.VALIDE, resultat=ControleQualite.Resultat.CONFORME).exists():
        return f"OF {of.code} : aucun contrôle qualité validé conforme (CND / ITP) — libération interdite."
    en_attente = controles.exclude(statut=ControleQualite.Statut.VALIDE).count()
    if en_attente:
        return f"OF {of.code} : {en_attente} contrôle(s) qualité non validé(s) (ITP / CND en cours) — libération interdite."
    if controles.filter(resultat=ControleQualite.Resultat.NON_CONFORME).exists():
        return f"OF {of.code} : contrôle non conforme — reprise et re-contrôle requis avant libération."
    if NonConformite.objects.filter(controle__ordre=of).exclude(statut=NonConformite.Statut.CLOTUREE).exists():
        return f"OF {of.code} : NC ouverte(s) sur l'OF — traitement et clôture requis avant libération."
    from qualite.models import PunchItem

    bloquantes = PunchItem.objects.filter(ordre=of, categorie=PunchItem.Categorie.A, statut=PunchItem.Statut.OUVERTE).count()
    if bloquantes:
        return f"OF {of.code} : {bloquantes} réserve(s) A de la punch list ouverte(s) — levée requise avant libération."
    return None
