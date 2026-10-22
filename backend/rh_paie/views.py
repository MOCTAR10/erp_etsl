"""Vues API M9 — RH & Paie (RF-ERP-80…83, circuits proc. 7.x)."""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from config.filtres_vues import FiltresMulticriteresMixin
from rest_framework import generics, serializers, status, viewsets
from rest_framework.permissions import BasePermission
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response

from accounting_kernel.permissions import CanPostAccounting
from config.inputs import date_input

from .models import (
    BaremeImpot,
    BaremeCotisation,
    CompteEmetteur,
    DeclarationSociale,
    OrdreVirement,
    HistoriqueBareme,
    ParametrePaie,
    BulletinPaie,
    ContratTravail,
    DemandeRecrutement,
    DemandesConge,
    Employe,
    Formation,
    Qualification,
    RubriquePaie,
    SaisieTemps,
    Sanction,
)
from .serializers import (
    BaremeImpotSerializer,
    CompteEmetteurSerializer,
    DeclarationSocialeSerializer,
    OrdreVirementSerializer,
    HistoriqueBaremeSerializer,
    ParametrePaieSerializer,
    MonBulletinSerializer,
    MonCongeSerializer,
    BaremeCotisationSerializer,
    BulletinAvecLignesSerializer,
    BulletinSerializer,
    ContratSerializer,
    DemandeCongeSerializer,
    EmployeSerializer,
    FormationSerializer,
    QualificationSerializer,
    RecrutementSerializer,
    RubriqueSerializer,
    SaisieTempsSerializer,
    SanctionSerializer,
)
from .services import (
    CanManagePaie,
    CanManageRh,
    archiver_bulletin,
    bareme_fige,
    generer_declaration,
    generer_virement,
    integrer_temps,
    reporting_rh,
    calculer_bulletin,
    comptabiliser_bulletin,
    confirmer_valeur,
    reviser_valeur,
    tracer_changement,
)
from config.i18n import tr


class EmployeViewSet(FiltresMulticriteresMixin, viewsets.ModelViewSet):
    # EX-G-03 : filtre par site (`?site_etsl=<id>`, GET filtres/) et restriction de lecture par site (paramètre).
    champs_filtrables = ("site_etsl",)
    champ_site = "site_etsl"
    queryset = Employe.objects.prefetch_related("contrats", "formations", "bulletins").all()
    serializer_class = EmployeSerializer
    search_fields = ("code", "nom", "prenom", "fonction", "departement",)
    permission_classes = [CanManageRh]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        if departement := params.get("departement"):
            qs = qs.filter(departement=departement)
        if recherche := params.get("recherche"):
            qs = qs.filter(
                Q(nom__icontains=recherche)
                | Q(prenom__icontains=recherche)
                | Q(code__icontains=recherche)
            )
        return qs

    @action(detail=True, methods=["post"], url_path="activer")
    def activer(self, request, pk=None):
        e = self.get_object()
        # Un salarié sorti ne se « réactive » pas (date de sortie, solde de tout compte) : réembauche = nouvelle fiche.
        if e.statut == Employe.Statut.SORTI:
            return Response({"detail": "Salarié sorti : réembauche par une nouvelle fiche et un nouveau contrat."},
                            status=status.HTTP_400_BAD_REQUEST)
        e.statut = Employe.Statut.ACTIF
        e.save(update_fields=["statut", "updated_at"])
        return Response(self.get_serializer(e).data)

    @action(detail=True, methods=["post"], url_path="sortir")
    def sortir(self, request, pk=None):
        e = self.get_object()
        if e.statut == Employe.Statut.SORTI:
            return Response({"detail": tr("Salarié déjà sorti (le %(e_date_sortie)s).") % {"e_date_sortie": e.date_sortie}}, status=status.HTTP_400_BAD_REQUEST)
        e.statut = Employe.Statut.SORTI
        date_sortie = request.data.get("date_sortie")
        if date_sortie:
            # Parse strict via DRF : un valeur invalide (str/nombre/binaire) -> 400, pas 500.
            e.date_sortie = serializers.DateField().run_validation(date_sortie)
        else:
            e.date_sortie = timezone.localdate()
        e.save(update_fields=["statut", "date_sortie", "updated_at"])
        return Response(self.get_serializer(e).data)

    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        t = timezone.localdate()
        actifs = Employe.objects.filter(statut=Employe.Statut.ACTIF)
        contrats = ContratTravail.objects.filter(statut=ContratTravail.Statut.ACTIF)
        qualifs = Qualification.objects.all()
        return Response(
            {
                "effectif": actifs.count(),
                "en_conge": Employe.objects.filter(statut=Employe.Statut.CONGE).count(),
                "contrats_expirants_30": contrats.filter(date_fin__lte=t + timedelta(days=30), date_fin__gte=t).count(),
                "conges_en_attente": DemandesConge.objects.filter(
                    statut__in=[DemandesConge.Statut.DEMANDE, DemandesConge.Statut.APPROUVE]
                ).count(),
                "qualifications_expirees": qualifs.filter(date_validite__lt=t).count(),
                "bulletins_mois": BulletinPaie.objects.filter(
                    periode__gte=f"{t:%Y-%m}-01",
                    statut__in=[BulletinPaie.Statut.VALIDE, BulletinPaie.Statut.CLOTURE],
                ).count(),
            }
        )


class ContratViewSet(viewsets.ModelViewSet):
    queryset = ContratTravail.objects.select_related("employe").all()
    serializer_class = ContratSerializer
    search_fields = ("employe__code", "employe__nom", "employe__prenom",)
    permission_classes = [CanManageRh]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if employe := params.get("employe"):
            qs = qs.filter(employe_id=employe)
        if type_contrat := params.get("type"):
            qs = qs.filter(type=type_contrat)
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        if params.get("a_renouveler") == "1":
            t = timezone.localdate()
            qs = qs.filter(date_fin__lte=t + timedelta(days=90), date_fin__gte=t)
        return qs


class QualificationViewSet(viewsets.ModelViewSet):
    queryset = Qualification.objects.select_related("employe").all()
    serializer_class = QualificationSerializer
    permission_classes = [CanManageRh]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if employe := params.get("employe"):
            qs = qs.filter(employe_id=employe)
        if type_qualif := params.get("type"):
            qs = qs.filter(type=type_qualif)
        if params.get("expirees") == "1":
            qs = qs.filter(date_validite__lt=timezone.localdate())
        return qs


class RecrutementViewSet(viewsets.ModelViewSet):
    queryset = DemandeRecrutement.objects.select_related("responsable").all()
    serializer_class = RecrutementSerializer
    permission_classes = [CanManageRh]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        if params.get("ouvertes") == "1":
            qs = qs.exclude(statut__in=[DemandeRecrutement.Statut.INTEGRE, DemandeRecrutement.Statut.ANNULEE])
        return qs

    def _statut_action(self, request, pk, new_statut, allowed, message):
        dr = self.get_object()
        if dr.statut not in allowed:
            return Response({"detail": message}, status=status.HTTP_400_BAD_REQUEST)
        requested = request.data.get("statut")
        if requested is not None and str(requested) not in DemandeRecrutement.Statut.values:
            return Response({"detail": "Statut inconnu."}, status=status.HTTP_400_BAD_REQUEST)
        if requested:
            new_statut = requested
        dr.avancer(new_statut)
        return Response(self.get_serializer(dr).data)

    @action(detail=True, methods=["post"], url_path="valider")
    def valider(self, request, pk=None):
        return self._statut_action(
            request, pk, DemandeRecrutement.Statut.VALIDEE,
            allowed=[DemandeRecrutement.Statut.DEMANDE],
            message="Seule une demande à l'état 'Demandé' peut être validée.",
        )

    @action(detail=True, methods=["post"], url_path="integrer")
    def integrer(self, request, pk=None):
        return self._statut_action(
            request, pk, DemandeRecrutement.Statut.INTEGRE,
            allowed=[DemandeRecrutement.Statut.VALIDEE, DemandeRecrutement.Statut.CANDIDATS, DemandeRecrutement.Statut.ENTREVUE],
            message="Le besoin doit être validé avant intégration.",
        )

    @action(detail=True, methods=["post"], url_path="annuler")
    def annuler(self, request, pk=None):
        return self._statut_action(
            request, pk, DemandeRecrutement.Statut.ANNULEE,
            allowed=[DemandeRecrutement.Statut.DEMANDE, DemandeRecrutement.Statut.VALIDEE, DemandeRecrutement.Statut.CANDIDATS],
            message="Cette demande ne peut plus être annulée.",
        )


class FormationsViewSet(viewsets.ModelViewSet):
    queryset = Formation.objects.prefetch_related("participants").all()
    serializer_class = FormationSerializer
    permission_classes = [CanManageRh]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if type_formation := params.get("type"):
            qs = qs.filter(type=type_formation)
        if params.get("a_venir") == "1":
            qs = qs.filter(date_session__gte=timezone.localdate())
        return qs

    @action(detail=True, methods=["post"], url_path="realiser")
    def realiser(self, request, pk=None):
        """`{"evaluation", "cout_reel", "gain_estime", "note_evaluation"}` (facultatifs) : la qualification du
        catalogue est délivrée à chaque participant."""
        from .formation_m9c import realiser_formation

        montant = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, allow_null=True)
        data = request.data
        champs = {
            "cout_reel": montant.run_validation(data.get("cout_reel")) if data.get("cout_reel") not in (None, "") else None,
            "gain_estime": montant.run_validation(data.get("gain_estime")) if data.get("gain_estime") not in (None, "") else None,
            "note": serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=20).run_validation(
                data.get("note_evaluation")) if data.get("note_evaluation") not in (None, "") else None,
        }
        try:
            formation = realiser_formation(self.get_object(), evaluation=data.get("evaluation") or "", **champs)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"detail": exc.messages})
        return Response(self.get_serializer(formation).data)

    @action(detail=True, methods=["post"], url_path="inscrire")
    def inscrire(self, request, pk=None):
        """`{"employe": <id>}` : inscrit un salarié à une session prévue."""
        formation = self.get_object()
        if formation.type != Formation.Type.PLANIFIE:
            raise serializers.ValidationError({"detail": "Inscription possible seulement sur une session prévue."})
        employe = serializers.PrimaryKeyRelatedField(queryset=Employe.objects.all()).run_validation(
            request.data.get("employe")
        )
        formation.participants.add(employe)
        return Response(self.get_serializer(formation).data)

    @action(detail=True, methods=["post"], url_path="annuler")
    def annuler(self, request, pk=None):
        formation = self.get_object()
        if formation.type != Formation.Type.PLANIFIE:
            return Response(
                {"detail": "Seule une formation prévue peut être annulée."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        formation.type = Formation.Type.ANNULEE
        formation.save()
        return Response(self.get_serializer(formation).data)


class DemandeCongeViewSet(viewsets.ModelViewSet):
    queryset = DemandesConge.objects.select_related("employe").all()
    serializer_class = DemandeCongeSerializer
    search_fields = ("employe__code", "employe__nom", "employe__prenom",)
    permission_classes = [CanManageRh]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if employe := params.get("employe"):
            qs = qs.filter(employe_id=employe)
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        if params.get("ouvertes") == "1":
            qs = qs.exclude(statut__in=[DemandesConge.Statut.VALIDE_RH, DemandesConge.Statut.REFUSE, DemandesConge.Statut.ANNULE])
        return qs

    LOCKED = (
        DemandesConge.Statut.APPROUVE,
        DemandesConge.Statut.VALIDE_RH,
        DemandesConge.Statut.REFUSE,
        DemandesConge.Statut.ANNULE,
    )

    def update(self, request, *args, **kwargs):
        # Une fois la demande instruite, dates/duree ne bougent plus (annuler et ressaisir).
        if self.get_object().statut in self.LOCKED:
            return Response(
                {"detail": "Demande instruite : non modifiable. Annulez-la et ressaisissez-la."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().update(request, *args, **kwargs)

    @staticmethod
    def _verifier_solde(dc, request):
        """Conge annuel : refus si la duree depasse le solde restant de l'annee."""
        solde = dc.employe.solde_conges
        if dc.type == DemandesConge.Type.ANNUEL and dc.nb_jours > solde:
            raise serializers.ValidationError(
                {"detail": tr("Solde insuffisant : %(solde)s jour(s) restant(s), %(dc_nb_jours)s demande(s).") % {"solde": solde, "dc_nb_jours": dc.nb_jours}}
            )

    @classmethod
    def _verifier_solde_si_directe(cls, dc, request):
        # Depuis APPROUVE le solde a deja ete controle ; depuis DEMANDE (validation directe) non.
        if getattr(dc, "_statut_initial", None) == DemandesConge.Statut.DEMANDE:
            cls._verifier_solde(dc, request)

    def _transition(self, request, pk, target, allowed, message, extra=None):
        dc = self.get_object()
        dc._statut_initial = dc.statut
        if dc.statut not in allowed:
            return Response({"detail": message}, status=status.HTTP_400_BAD_REQUEST)
        dc.statut = target
        if extra:
            extra(dc, request)
        dc.save()
        return Response(self.get_serializer(dc).data)

    @action(detail=True, methods=["post"], url_path="approuver")
    def approuver(self, request, pk=None):
        return self._transition(
            request, pk, DemandesConge.Statut.APPROUVE,
            allowed=[DemandesConge.Statut.DEMANDE],
            message="Seule une demande 'Demandé' peut être approuvée par la hiérarchie.",
            extra=self._verifier_solde,
        )

    @action(detail=True, methods=["post"], url_path="valider")
    def valider(self, request, pk=None):
        return self._transition(
            request, pk, DemandesConge.Statut.VALIDE_RH,
            allowed=[DemandesConge.Statut.APPROUVE, DemandesConge.Statut.DEMANDE],
            message="La demande doit être approuvée (ou au moins demandée) avant validation RH.",
            extra=self._verifier_solde_si_directe,
        )

    @action(detail=True, methods=["post"], url_path="refuser")
    def refuser(self, request, pk=None):
        return self._transition(
            request, pk, DemandesConge.Statut.REFUSE,
            allowed=[DemandesConge.Statut.DEMANDE, DemandesConge.Statut.APPROUVE],
            message="Cette demande ne peut plus être refusée.",
        )

    @action(detail=True, methods=["post"], url_path="annuler")
    def annuler(self, request, pk=None):
        return self._transition(
            request, pk, DemandesConge.Statut.ANNULE,
            allowed=[DemandesConge.Statut.DEMANDE, DemandesConge.Statut.APPROUVE],
            message="Cette demande ne peut plus être annulée.",
        )


class SanctionViewSet(viewsets.ModelViewSet):
    queryset = Sanction.objects.select_related("employe").all()
    serializer_class = SanctionSerializer
    permission_classes = [CanManageRh]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if employe := params.get("employe"):
            qs = qs.filter(employe_id=employe)
        if type_sanction := params.get("type"):
            qs = qs.filter(type=type_sanction)
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        return qs

    @action(detail=True, methods=["post"], url_path="instruire")
    def instruire(self, request, pk=None):
        s = self.get_object()
        if s.statut != Sanction.Statut.CONSTATE:
            return Response(
                {"detail": "Seul un constat peut être mis en instruction."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        s.statut = Sanction.Statut.INSTRUITE
        if request.data.get("rapport"):
            s.rapport = request.data.get("rapport")
        s.save()
        return Response(self.get_serializer(s).data)

    @action(detail=True, methods=["post"], url_path="decider")
    def decider(self, request, pk=None):
        s = self.get_object()
        if s.statut != Sanction.Statut.INSTRUITE:
            return Response(
                {"detail": "Seule une sanction en instruction peut faire l'objet d'une décision."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        date_decision = date_input(request.data.get("date_decision"), "date_decision", default=timezone.localdate())
        s.statut = Sanction.Statut.DECIDEE
        s.date_decision = date_decision
        s.save()
        return Response(self.get_serializer(s).data)

    @action(detail=True, methods=["post"], url_path="archiver")
    def archiver(self, request, pk=None):
        s = self.get_object()
        if s.statut != Sanction.Statut.DECIDEE:
            return Response(
                {"detail": "Seule une sanction décidée peut être archivée."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        s.statut = Sanction.Statut.ARCHIVEE
        s.save()
        return Response(self.get_serializer(s).data)


class SaisieTempsViewSet(viewsets.ModelViewSet):
    queryset = SaisieTemps.objects.select_related("employe").all()
    serializer_class = SaisieTempsSerializer
    permission_classes = [CanManageRh]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if employe := params.get("employe"):
            qs = qs.filter(employe_id=employe)
        if date_debut := params.get("date_debut"):
            qs = qs.filter(date__gte=date_debut)
        if date_fin := params.get("date_fin"):
            qs = qs.filter(date__lte=date_fin)
        if params.get("transferees") == "1":
            qs = qs.filter(statut=SaisieTemps.Statut.TRANSFERE_PAIE)
        return qs

    @action(detail=True, methods=["post"], url_path="transferer-paie")
    def transferer_paie(self, request, pk=None):
        """Marque une saisie temps comme transmise à la paie (RF-ERP-81 → 82)."""
        st = self.get_object()
        if st.statut == SaisieTemps.Statut.TRANSFERE_PAIE:
            return Response(
                {"detail": "Cette saisie a déjà été transférée en paie."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        st.statut = SaisieTemps.Statut.TRANSFERE_PAIE
        st.save()
        return Response(self.get_serializer(st).data)


class RubriqueViewSet(viewsets.ModelViewSet):
    queryset = RubriquePaie.objects.all()
    serializer_class = RubriqueSerializer
    permission_classes = [CanManageRh]


class BulletinViewSet(viewsets.ModelViewSet):
    queryset = BulletinPaie.objects.select_related("employe").prefetch_related("lignes__rubrique").all()
    serializer_class = BulletinSerializer
    search_fields = ("employe__code", "employe__nom", "employe__prenom",)
    permission_classes = [CanManagePaie]
    http_method_names = ["get", "post", "head", "options"]  # pas de PUT/DELETE

    def get_serializer_class(self):
        if self.action in ("create", "calculer"):
            return BulletinAvecLignesSerializer
        return BulletinSerializer

    def create(self, request, *args, **kwargs):
        serializer = BulletinAvecLignesSerializer(
            data=request.data, context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():  # bulletin + lignes : tout ou rien
            bulletin = serializer.save()
        return Response(
            BulletinSerializer(bulletin, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if employe := params.get("employe"):
            qs = qs.filter(employe_id=employe)
        if periode := params.get("periode"):
            qs = qs.filter(periode=periode)
        if mois := params.get("mois"):
            qs = qs.filter(periode__startswith=mois)
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        return qs

    @action(detail=True, methods=["post"], url_path="calculer")
    def calculer(self, request, pk=None):
        """Recalcule brut/net depuis les lignes du bulletin."""
        bulletin = self.get_object()
        if bulletin.statut != BulletinPaie.Statut.BROUILLON:
            return Response(
                {"detail": "Seul un bulletin brouillon peut être recalculé."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        bulletin = calculer_bulletin(bulletin)  # barèmes en vigueur + gains/retenues saisis
        return Response(self.get_serializer(bulletin).data)

    def get_permissions(self):
        if self.action == "comptabiliser":
            # Écriture comptable : cercle de la paie ET cercle comptable (admin/comptable/finance/direction).
            return [CanManagePaie(), CanPostAccounting()]
        return super().get_permissions()

    @action(detail=True, methods=["post"], url_path="comptabiliser")
    def comptabiliser(self, request, pk=None):
        """Génère l'écriture de paie (journal PAI) d'un bulletin validé (RF-ERP-82 → M10)."""
        try:
            comptabiliser_bulletin(self.get_object(), user=request.user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"detail": exc.messages})
        bulletin = self.get_object()
        return Response(self.get_serializer(bulletin).data)

    @action(detail=True, methods=["post"], url_path="valider")
    def valider(self, request, pk=None):
        bulletin = self.get_object()
        if bulletin.statut != BulletinPaie.Statut.BROUILLON:
            return Response(
                {"detail": "Seul un bulletin brouillon peut être validé."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        bulletin.statut = BulletinPaie.Statut.VALIDE
        bulletin.save(update_fields=["statut", "updated_at"])
        return Response(self.get_serializer(bulletin).data)

    @action(detail=True, methods=["post"], url_path="integrer-temps")
    def integrer_temps(self, request, pk=None):
        """Intègre les heures supplémentaires des pointages du mois (durée légale et majorations paramétrées)."""
        try:
            bulletin, _ = integrer_temps(self.get_object())
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"detail": exc.messages})
        return Response(self.get_serializer(bulletin).data)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"], url_path="preparer")
    def preparer(self, request, pk=None):
        """Prépare le bulletin depuis le contrat : salaire (grille), primes récurrentes, prorata, absences, heures sup."""
        from .paie_m9a import preparer_bulletin

        try:
            preparer_bulletin(self.get_object())
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"detail": exc.messages})
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=True, methods=["post"], url_path="archiver")
    def archiver(self, request, pk=None):
        """Scelle le PDF du bulletin en GED (conservation ≥ 10 ans, accès restreint RH)."""
        try:
            archiver_bulletin(self.get_object(), user=request.user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"detail": exc.messages})
        return Response(self.get_serializer(self.get_object()).data)

    @extend_schema(responses=OpenApiTypes.BINARY)
    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request, pk=None):
        return _reponse_pdf(self.get_object())

    @action(detail=True, methods=["post"], url_path="signer")
    def signer(self, request, pk=None):
        """Soumet le bulletin archivé à la signature électronique avancée (`{"signataire": <user id>}`, défaut :
        l'utilisateur courant) ; la signature se fait dans « Signatures » (code à usage unique + sceau)."""
        from django.contrib.auth import get_user_model

        from .formation_m9c import demander_signature_bulletin

        signataire = None
        if request.data.get("signataire"):
            signataire = serializers.PrimaryKeyRelatedField(
                queryset=get_user_model().objects.filter(is_active=True)
            ).run_validation(request.data.get("signataire"))
        try:
            demander_signature_bulletin(self.get_object(), request.user, signataire=signataire)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"detail": exc.messages})
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=True, methods=["post"], url_path="diffuser")
    def diffuser(self, request, pk=None):
        """Met le bulletin à disposition du salarié (accusé de dépôt horodaté, CL-OM-06)."""
        bulletin = self.get_object()
        if bulletin.statut not in (BulletinPaie.Statut.VALIDE, BulletinPaie.Statut.CLOTURE):
            return Response(
                {"detail": "Seul un bulletin validé ou clôturé peut être diffusé."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if bulletin.disponible_le:
            return Response(
                {"detail": tr("Déjà mis à disposition le %(bulletin_disponible_le)s.") % {"bulletin_disponible_le": format(bulletin.disponible_le, '%d/%m/%Y %H:%M')}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not bulletin.document_id:  # la copie du salarié est la copie archivée
            archiver_bulletin(bulletin, user=request.user)
            bulletin.refresh_from_db()
        bulletin.disponible_le = timezone.now()
        bulletin.save(update_fields=["disponible_le", "updated_at"])
        return Response(self.get_serializer(bulletin).data)

    @action(detail=True, methods=["post"], url_path="cloturer")
    def cloturer(self, request, pk=None):
        bulletin = self.get_object()
        if bulletin.statut != BulletinPaie.Statut.VALIDE:
            return Response(
                {"detail": "Seul un bulletin validé peut être clôturé."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        bulletin.statut = BulletinPaie.Statut.CLOTURE
        bulletin.save(update_fields=["statut", "updated_at"])
        return Response(self.get_serializer(bulletin).data)

    @action(detail=True, methods=["post"], url_path="annuler")
    def annuler(self, request, pk=None):
        bulletin = self.get_object()
        if bulletin.statut in (BulletinPaie.Statut.CLOTURE, BulletinPaie.Statut.ANNULE):
            return Response(
                {"detail": "Le bulletin est déjà clôturé ou annulé."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        bulletin.statut = BulletinPaie.Statut.ANNULE
        bulletin.save(update_fields=["statut", "updated_at"])
        return Response(self.get_serializer(bulletin).data)

    @action(detail=False, methods=["get"], url_path="masse")
    def masse(self, request):
        t = timezone.localdate()
        mois = request.query_params.get("mois") or f"{t:%Y-%m}"
        bulletins = BulletinPaie.objects.filter(periode__startswith=mois).exclude(
            statut=BulletinPaie.Statut.ANNULE
        )
        agg = bulletins.aggregate(
            effectif=Count("id", distinct=True),
            brut_total=Sum("brut"),
            net_total=Sum("net"),
        )
        return Response(
            {
                "mois": mois,
                "bulletins": agg["effectif"] or 0,
                "brut_total": f"{agg['brut_total'] or 0:.2f}",
                "net_total": f"{agg['net_total'] or 0:.2f}",
            }
        )


def _reponse_pdf(bulletin):
    """Réponse PDF du bulletin : copie archivée si elle existe, sinon génération à la volée (brouillon)."""
    from django.http import HttpResponse

    from .services import bulletin_pdf

    if bulletin.document_id and bulletin.document.current_version_id:
        version = bulletin.document.current_version
        with version.file.open("rb") as f:
            contenu = f.read()
    else:
        contenu = bulletin_pdf(bulletin)
    rep = HttpResponse(contenu, content_type="application/pdf")
    rep["Content-Disposition"] = f'attachment; filename="{bulletin.code}.pdf"'
    return rep


class BaremeVersionneMixin:
    """Paramétrage sans développeur : cercle `CanManagePaie`, historique inaltérable, versions conservées.

    - création / modification tracées dans `HistoriqueBareme` ;
    - une valeur déjà appliquée à un bulletin validé n'est plus modifiable (→ `reviser`, nouvelle version) ;
    - toute modification repasse la valeur à « provisoire » ; `confirmer` est une action explicite.
    """

    objet = ""
    champs_valeurs = ()
    permission_classes = [CanManagePaie]

    def perform_create(self, serializer):
        obj = serializer.save()
        tracer_changement(obj, self.objet, "creation", self.request.user)

    def update(self, request, *args, **kwargs):
        from .services import _etat

        # Instantané AVANT validation : le sérialiseur applique les valeurs sur l'instance (full_clean).
        self._avant = _etat(self.get_object())
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        avant = self._avant
        if bareme_fige(serializer.instance) and any(c in self.request.data for c in self.champs_valeurs):
            raise serializers.ValidationError(
                {"detail": "Valeur déjà utilisée par un bulletin validé : créer une nouvelle version (action « reviser »)."}
            )
        obj = serializer.save(
            statut_valeur="provisoire", confirme_par=None, confirme_le=None
        ) if any(c in self.request.data for c in self.champs_valeurs) else serializer.save()
        tracer_changement(obj, self.objet, "modification", self.request.user, avant)

    def perform_destroy(self, instance):
        from .services import _etat

        if bareme_fige(instance):
            raise serializers.ValidationError({"detail": "Valeur utilisée par un bulletin validé : suppression interdite."})
        avant = _etat(instance)
        tracer_changement(instance, self.objet, "suppression", self.request.user, avant)
        instance.delete()

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def confirmer(self, request, pk=None):
        obj = confirmer_valeur(self.get_object(), self.objet, request.user)
        return Response(self.get_serializer(obj).data)

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def reviser(self, request, pk=None):
        """Nouvelle version datée : `{"date_effet": "...", <champs modifiés>}`. L'ancienne est close la veille."""
        data = request.data
        champ_date = serializers.DateField().run_validation(data.get("date_effet"))
        champs = {c: data[c] for c in self.champs_valeurs + ("source", "reference_texte") if c in data}
        try:
            nouvelle = reviser_valeur(self.get_object(), self.objet, request.user, champ_date, champs)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"detail": exc.messages})
        return Response(self.get_serializer(nouvelle).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses=HistoriqueBaremeSerializer(many=True))
    @action(detail=True, methods=["get"])
    def historique(self, request, pk=None):
        obj = self.get_object()
        qs = HistoriqueBareme.objects.filter(objet=self.objet, code=obj.code)
        return Response(HistoriqueBaremeSerializer(qs, many=True).data)


class BaremeCotisationViewSet(BaremeVersionneMixin, viewsets.ModelViewSet):
    """Barèmes de cotisation versionnés (taux/plafonds = données, à valider avec ETSL)."""

    objet = "cotisation"
    champs_valeurs = ("taux", "plafond", "base", "nature", "organisme", "label")

    queryset = BaremeCotisation.objects.all()
    serializer_class = BaremeCotisationSerializer
    permission_classes = [CanManagePaie]


# --------------------------------------------------------------------------------------------
# Libre-service salarié (CL-OM-01 : inclus dans M9 ; CL-OM-06 : accusé de dépôt horodaté)
# --------------------------------------------------------------------------------------------
class IsEmployeLie(BasePermission):
    """Compte authentifié lié à une fiche salarié : l'espace ne montre que SES données."""

    message = "Aucune fiche salarié n'est liée à ce compte."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        fiche = Employe.objects.filter(user=user).first()
        request.employe = fiche
        return fiche is not None


class MonProfilView(APIView):
    permission_classes = [IsEmployeLie]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        e = request.employe
        return Response(
            {
                "id": str(e.pk), "code": e.code, "nom_complet": e.nom_complet,
                "categorie": e.categorie, "statut": e.statut,
                "solde_conges": e.solde_conges,
                "acquis_annuel": DemandesConge.DUREE_CONGE_CNSS,
            }
        )


class MesBulletinsView(generics.ListAPIView):
    permission_classes = [IsEmployeLie]
    serializer_class = MonBulletinSerializer

    def get_queryset(self):
        return (
            BulletinPaie.objects.filter(employe=self.request.employe, disponible_le__isnull=False)
            .prefetch_related("lignes__rubrique")
            .order_by("-periode")
        )


class MonBulletinView(generics.RetrieveAPIView):
    permission_classes = [IsEmployeLie]
    serializer_class = MonBulletinSerializer

    def get_queryset(self):
        return BulletinPaie.objects.filter(
            employe=self.request.employe, disponible_le__isnull=False
        ).prefetch_related("lignes__rubrique")

    def retrieve(self, request, *args, **kwargs):
        bulletin = self.get_object()
        if bulletin.consulte_le is None:  # accusé de consultation : première ouverture seulement
            bulletin.consulte_le = timezone.now()
            bulletin.save(update_fields=["consulte_le", "updated_at"])
        return Response(self.get_serializer(bulletin).data)


class MesCongesView(generics.ListCreateAPIView):
    permission_classes = [IsEmployeLie]
    serializer_class = MonCongeSerializer

    def get_queryset(self):
        return DemandesConge.objects.filter(employe=self.request.employe).order_by("-created_at")

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["employe"] = getattr(self.request, "employe", None)
        return ctx


class MonCongeAnnulerView(APIView):
    permission_classes = [IsEmployeLie]

    @extend_schema(request=None, responses=MonCongeSerializer)
    def post(self, request, pk):
        demande = generics.get_object_or_404(DemandesConge, pk=pk, employe=request.employe)
        if demande.statut != DemandesConge.Statut.DEMANDE:
            return Response(
                {"detail": "Seule une demande en attente peut être annulée par le salarié."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        demande.statut = DemandesConge.Statut.ANNULE
        demande.save()
        return Response(MonCongeSerializer(demande).data)


class BaremeImpotViewSet(BaremeVersionneMixin, viewsets.ModelViewSet):
    """Barème progressif de l'impôt sur le revenu (tranches mensuelles par part) — donnée à valider avec ETSL."""

    objet = "impot"
    champs_valeurs = ("tranches", "abattement_pct", "cotisations_deductibles", "label")

    queryset = BaremeImpot.objects.all()
    serializer_class = BaremeImpotSerializer
    permission_classes = [CanManagePaie]


class ParametrePaieViewSet(BaremeVersionneMixin, viewsets.ModelViewSet):
    """Paramètres versionnés (SMIG, durée légale, majorations d'heures supplémentaires, taxes patronales)."""

    objet = "parametre"
    champs_valeurs = ("valeur", "unite", "label")
    queryset = ParametrePaie.objects.all()
    serializer_class = ParametrePaieSerializer


class HistoriqueBaremeViewSet(viewsets.ReadOnlyModelViewSet):
    """Journal inaltérable des changements de barèmes (lecture seule, cercle paie)."""

    queryset = HistoriqueBareme.objects.select_related("par")
    serializer_class = HistoriqueBaremeSerializer
    permission_classes = [CanManagePaie]
    filterset_fields = ["objet", "code"]


class MonBulletinPdfView(APIView):
    permission_classes = [IsEmployeLie]

    @extend_schema(responses=OpenApiTypes.BINARY)
    def get(self, request, pk):
        bulletin = generics.get_object_or_404(
            BulletinPaie, pk=pk, employe=request.employe, disponible_le__isnull=False
        )
        return _reponse_pdf(bulletin)


class CompteEmetteurViewSet(viewsets.ModelViewSet):
    """Comptes bancaires émetteurs des virements de salaires — cercle paie."""

    queryset = CompteEmetteur.objects.all()
    serializer_class = CompteEmetteurSerializer
    permission_classes = [CanManagePaie]


class OrdreVirementViewSet(viewsets.ReadOnlyModelViewSet):
    """Ordres de virement CFONB 160 (scellés à la génération)."""

    queryset = OrdreVirement.objects.select_related("compte", "created_by")
    serializer_class = OrdreVirementSerializer
    permission_classes = [CanManagePaie]

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OrdreVirementSerializer)
    @action(detail=False, methods=["post"], url_path="generer")
    def generer(self, request):
        """`{"periode": "AAAA-MM-01", "compte": <id>, "date_execution": "AAAA-MM-JJ"}`."""
        data = request.data
        periode = serializers.DateField().run_validation(data.get("periode"))
        date_execution = serializers.DateField().run_validation(data.get("date_execution"))
        compte = generics.get_object_or_404(CompteEmetteur, pk=data.get("compte"))
        try:
            ordre = generer_virement(periode, compte, date_execution, user=request.user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"detail": exc.messages})
        return Response(self.get_serializer(ordre).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses=OpenApiTypes.BINARY)
    @action(detail=True, methods=["get"], url_path="fichier")
    def fichier(self, request, pk=None):
        from django.http import HttpResponse

        ordre = self.get_object()
        rep = HttpResponse(ordre.contenu, content_type="text/plain; charset=ascii")
        rep["Content-Disposition"] = f'attachment; filename="{ordre.code}.cfonb"'
        return rep


class DeclarationSocialeViewSet(viewsets.ReadOnlyModelViewSet):
    """Déclarations CNSS / CNAMGS / IRPP (2460) / DADS générées depuis les bulletins, scellées."""

    queryset = DeclarationSociale.objects.select_related("created_by")
    serializer_class = DeclarationSocialeSerializer
    permission_classes = [CanManagePaie]

    @extend_schema(request=OpenApiTypes.OBJECT, responses=DeclarationSocialeSerializer)
    @action(detail=False, methods=["post"], url_path="generer")
    def generer(self, request):
        """`{"type": "cnss|cnamgs|irpp|dads", "periode_debut": "AAAA-MM-01", "periode_fin": "AAAA-MM-01"}`."""
        data = request.data
        debut = serializers.DateField().run_validation(data.get("periode_debut"))
        fin = serializers.DateField().run_validation(data.get("periode_fin"))
        try:
            decl = generer_declaration(data.get("type"), debut, fin, user=request.user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"detail": exc.messages})
        return Response(self.get_serializer(decl).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses=OpenApiTypes.BINARY)
    @action(detail=True, methods=["get"], url_path="fichier")
    def fichier(self, request, pk=None):
        from django.http import HttpResponse

        decl = self.get_object()
        rep = HttpResponse(decl.contenu, content_type="text/csv; charset=utf-8")
        rep["Content-Disposition"] = f'attachment; filename="{decl.code}_{decl.type}.csv"'
        return rep


class ReportingRhView(APIView):
    """Turnover et absentéisme de l'année (`?annee=AAAA`)."""

    permission_classes = [CanManageRh]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        annee = serializers.IntegerField(min_value=2000, max_value=2100).run_validation(
            request.query_params.get("annee", timezone.localdate().year)
        )
        return Response(reporting_rh(annee))
