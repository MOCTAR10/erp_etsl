"""Vues API M9 — RH & Paie (RF-ERP-80…83, circuits proc. 7.x)."""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
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
from .services import CanManagePaie, CanManageRh


class EmployeViewSet(viewsets.ModelViewSet):
    queryset = Employe.objects.prefetch_related("contrats", "formations", "bulletins").all()
    serializer_class = EmployeSerializer
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
        e.statut = Employe.Statut.ACTIF
        e.save(update_fields=["statut", "updated_at"])
        return Response(self.get_serializer(e).data)

    @action(detail=True, methods=["post"], url_path="sortir")
    def sortir(self, request, pk=None):
        e = self.get_object()
        e.statut = Employe.Statut.SORTI
        e.date_sortie = request.data.get("date_sortie") or timezone.localdate()
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
        if request.data.get("statut"):
            new_statut = request.data.get("statut")
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
        formation = self.get_object()
        if formation.type != Formation.Type.PLANIFIE:
            return Response(
                {"detail": "Seule une formation prévue peut être marquée réalisée."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        formation.type = Formation.Type.REALISEE
        if request.data.get("evaluation"):
            formation.evaluation = request.data.get("evaluation")
        formation.save()
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

    def _transition(self, request, pk, target, allowed, message, extra=None):
        dc = self.get_object()
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
        )

    @action(detail=True, methods=["post"], url_path="valider")
    def valider(self, request, pk=None):
        return self._transition(
            request, pk, DemandesConge.Statut.VALIDE_RH,
            allowed=[DemandesConge.Statut.APPROUVE, DemandesConge.Statut.DEMANDE],
            message="La demande doit être approuvée (ou au moins demandée) avant validation RH.",
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
        s.statut = Sanction.Statut.DECIDEE
        s.date_decision = request.data.get("date_decision") or timezone.localdate()
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
        gains, retenues = Decimal("0"), Decimal("0")
        for ligne in bulletin.lignes.select_related("rubrique"):
            if ligne.rubrique.nature == RubriquePaie.Nature.GAIN:
                gains += ligne.montant
            else:
                retenues += ligne.montant
        bulletin.brut = gains
        bulletin.net = gains - retenues
        bulletin.save(update_fields=["brut", "net", "updated_at"])
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