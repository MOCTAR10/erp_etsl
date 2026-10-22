"""Vues Couche D — BI / décisionnel (RF-ERP-C0...C3).

Lecture seule pour tout utilisateur authentifié ; montants masqués selon le
pattern RF-59 (services). Aucune écriture exposée ici (les datamarts dbt /
Superset vivent sur le réplica lecteur).
"""

from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from controle_gestion.services import can_manage_gestion, can_see_amount

from users.models import User

from . import bi_etat, cubes, pilotage
from .exports import FORMATS, reponse_export, sections_indicateurs
from .models import CubeArchive, ParametreCube, ScelleMart
from .serializers import CubeArchiveSerializer, ParametreCubeSerializer, ScelleMartSerializer

EXPORT_PARAM = OpenApiParameter("export", str, description="xlsx ou pdf : télécharge le tableau (Excel / PDF).")


def _format_export(request):
    """Format demandé (`?export=xlsx|pdf`), None sans export ; ValueError si format inconnu."""
    fmt = request.query_params.get("export")
    if fmt in (None, ""):
        return None
    if fmt not in FORMATS:
        raise ValueError("Export attendu : xlsx ou pdf.")
    return fmt

from .services import (
    alertes_agregees,
    tendances,
    dashboard_direction,
    reporting_petrolier,
)


@extend_schema(
    parameters=[EXPORT_PARAM],
    responses={200: OpenApiTypes.OBJECT},
    description="Tableau de bord Direction — KPIs consolidés des 12 modules (C1) ; `?export=xlsx|pdf`.",
)
class DashboardDirectionView(APIView):
    """Tableau de bord Direction — KPIs consolidés des 12 modules (C1)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            fmt = _format_export(request)
        except ValueError as exc:
            return _erreur(exc)
        data = dashboard_direction(request.user)
        if fmt:
            return reponse_export(fmt, "Tableau de bord Direction", "tableau_direction", sections_indicateurs(data))
        return Response(data)


@extend_schema(
    parameters=[EXPORT_PARAM],
    responses={200: OpenApiTypes.OBJECT},
    description="Reporting client pétrolier — ASMR / HSE / Qualité ITP / CND (C2) ; `?export=xlsx|pdf`.",
)
class ReportingPetrolierView(APIView):
    """Reporting client pétrolier — ASMR / HSE / Qualité ITP / CND (C2)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            fmt = _format_export(request)
        except ValueError as exc:
            return _erreur(exc)
        data = reporting_petrolier(request.user)
        if fmt:
            return reponse_export(fmt, "Reporting client pétrolier — ASMR / HSE / Qualité", "reporting_petrolier",
                                  sections_indicateurs(data))
        return Response(data)


@extend_schema(
    responses={200: OpenApiTypes.OBJECT},
    description="Alertes J-90 / J-60 / J-30 / expirées transverses (C3).",
)
class AlertesAgregeesView(APIView):
    """Alertes J-90 / J-60 / J-30 / expirées transverses (C3)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(alertes_agregees(request.user))


@extend_schema(
    responses={200: OpenApiTypes.OBJECT},
    description="Tendances mensuelles (6 mois) non financières du cockpit Direction, filtrées par droits.",
)
class TendancesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(tendances(request.user))


class CanReadCube(BasePermission):
    """Les cubes portent des montants : lecture = cercle des montants M11 ; alimentation / archivage = gestion."""

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated):
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            # Le contrôleur de gestion consomme la Couche D (CDC : DG, DAF, CG) même hors cercle M11 du module.
            return can_see_amount(user) or user.role == User.Role.CONTROLEUR_GESTION
        return can_manage_gestion(user)


#: Confirmation des paramètres de la Couche D : Direction (admin, PDG, DGA, Direction) ; la modification reste au
#: cercle de gestion (`CanReadCube`).
CUBE_PARAM_CONFIRM_ROLES = ("admin", "pdg", "dga", "direction")


class CanConfirmerParametreCube(BasePermission):
    message = "Confirmation des paramètres de la Couche D réservée à la Direction."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser
                                                        or user.role in CUBE_PARAM_CONFIRM_ROLES))


def _erreur(exc):
    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    parameters=[
        OpenApiParameter("periode", str, description="AAAA-MM (plusieurs, séparées par une virgule)."),
        OpenApiParameter("axes", str, description="Axes de lecture : affaire, chantier, site, activite, centre, periode."),
    ],
    responses={200: OpenApiTypes.OBJECT},
    description="Cube OLAP à 6 axes (affaire, chantier, site, activité, centre, période) : coupe agrégée (Couche D).",
)
class CubeView(APIView):
    permission_classes = [CanReadCube]

    def get(self, request):
        p = request.query_params
        periodes = [x for x in p.get("periode", "").split(",") if x] or None
        axes = tuple(x for x in p.get("axes", "periode").split(",") if x) or ("periode",)
        filtres = {a: p.get(a) for a in cubes.AXES if a != "periode" and p.get(a)}
        try:
            fmt = _format_export(request)
            for per in periodes or ():
                cubes._bornes(per)
            lecture = cubes.lire_cube(periodes, axes, filtres, user=request.user)
        except ValueError as exc:
            return _erreur(exc)
        if fmt:
            colonnes = list(lecture["axes"]) + ["produits", "charges", "cout_gr", "marge"]
            lignes = [[r[c] for c in colonnes] for r in lecture["rows"]]
            lignes.append(["TOTAL"] + [""] * (len(lecture["axes"]) - 1) + [lecture["totaux"][m] for m in colonnes[-4:]])
            return reponse_export(fmt, "Cube BI — coupe " + " × ".join(lecture["axes"]), "cube_bi",
                                  [("cube", colonnes, lignes)])
        return Response(lecture)


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
class CubeAlimenterView(APIView):
    """Alimente (ou ré-alimente) les faits d'un mois depuis le grand livre — idempotent."""

    permission_classes = [CanReadCube]

    def post(self, request):
        periode = request.data.get("periode", "")
        try:
            return Response({"periode": periode, "faits": cubes.alimenter_cube(periode)})
        except ValueError as exc:
            return _erreur(exc)


class CubeArchiveViewSet(viewsets.ReadOnlyModelViewSet):
    """Archives de cubes figées, scellées et conservées 10 ans (lecture seule)."""

    queryset = CubeArchive.objects.all()
    serializer_class = CubeArchiveSerializer
    permission_classes = [CanReadCube]
    lookup_field = "periode"

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: CubeArchiveSerializer})
    @action(detail=False, methods=["post"], url_path="archiver")
    def archiver(self, request):
        try:
            archive = cubes.archiver_cube(request.data.get("periode", ""), request.user)
        except ValueError as exc:
            return _erreur(exc)
        return Response(self.get_serializer(archive).data, status=status.HTTP_201_CREATED)


class ParametreCubeViewSet(viewsets.ModelViewSet):
    """Paramètres du cube modifiables par ETSL ; création/suppression interdites (définis par le code)."""

    queryset = ParametreCube.objects.all()
    serializer_class = ParametreCubeSerializer
    permission_classes = [CanReadCube]
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_permissions(self):
        if getattr(self, "action", None) == "confirmer":
            return [CanReadCube(), CanConfirmerParametreCube()]
        return super().get_permissions()

    def get_queryset(self):
        for code in cubes.PARAMETRES_DEFAUT:
            cubes.get_param_cube(code)
        return super().get_queryset()

    def create(self, request, *args, **kwargs):
        return Response({"detail": "Les paramètres sont prédéfinis : modifiez leur valeur."}, status=405)

    @action(detail=True, methods=["post"], url_path="confirmer")
    def confirmer(self, request, pk=None):
        p = self.get_object()
        p.statut_valeur = ParametreCube.StatutValeur.CONFIRME
        p.confirme_par = request.user
        p.confirme_le = timezone.now()
        p.save(update_fields=["statut_valeur", "confirme_par", "confirme_le"])
        return Response(self.get_serializer(p).data)


def _pilotage(request):
    return {
        "cashflow": pilotage.cashflow_13_semaines(),
        "pipe_budget": pilotage.pipe_vers_budget(),
        "seuils_budget": pilotage.seuils_budgetaires(),
        "retention": pilotage.etat_retention(),
        "blocage_avant_cloture": pilotage.blocage_avant_cloture_actif(),
        "voit_non_cloture": pilotage.voit_non_cloture(request.user),
        "periodes_cloturees": sorted(pilotage.periodes_cloturees()),
        "parametres_provisoires": cubes.parametres_provisoires(),
    }


@extend_schema(
    parameters=[EXPORT_PARAM],
    responses={200: OpenApiTypes.OBJECT},
    description="Pilotage Direction (Couche D) : cash-flow 13 semaines, pipe → budget, seuils budgétaires, "
    "conservation ; `?export=xlsx|pdf`. Cercle des montants M11.",
)
class PilotageDirectionView(APIView):
    permission_classes = [CanReadCube]

    def get(self, request):
        try:
            fmt = _format_export(request)
        except ValueError as exc:
            return _erreur(exc)
        data = _pilotage(request)
        if not fmt:
            return Response(data)
        cf = data["cashflow"]
        cles = ["semaine", "debut", "fin", "encaissements", "decaissements", "flux_net", "solde_fin"]
        pb = data["pipe_budget"]
        sections = [
            ("cash-flow 13 semaines", cles, [["ouverture", "", "", "", "", "", cf["ouverture"]]]
             + [[s[c] for c in cles] for s in cf["semaines"]]),
            ("pipe vers budget", ["Indicateur", "Valeur"], [
                ["Exercice", pb["annee"]], ["Budget de produits", pb["budget_produits"]], ["Réalisé", pb["realise"]],
                *[[f"Pipe pondéré {k}", v] for k, v in pb["pipe_pondere"].items()],
                ["Atterrissage", pb["atterrissage"]], ["Reste à couvrir", pb["reste_a_couvrir"]],
                ["Couverture (%)", pb["couverture_pct"]],
            ]),
            ("seuils budgetaires", ["Budget", "Libellé", "Montant", "Réalisé", "Taux %", "Niveau"],
             [[s["budget"], s["libelle"], s["montant"], s["realise"], s["taux_pct"], s["niveau"]] for s in data["seuils_budget"]]),
        ]
        return reponse_export(fmt, "Pilotage Direction — trésorerie et budget", "pilotage_direction", sections)


@extend_schema(request=None, responses={200: OpenApiTypes.OBJECT})
class ControlerSeuilsView(APIView):
    """Rejoue à la demande le contrôle quotidien des seuils budgétaires (notifications une fois par seuil)."""

    permission_classes = [CanReadCube]

    def post(self, request):
        return Response({"notifications": pilotage.controler_seuils_budgetaires(), "seuils": pilotage.seuils_budgetaires()})


@extend_schema(responses={200: OpenApiTypes.OBJECT},
               description="Alertes calendaires : garantie, agrément fournisseur, audit interne, revue de direction.")
class AlertesCalendairesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            "items": pilotage.alertes_calendaires(request.user),
            "paliers": sorted(pilotage.paliers_notification(), reverse=True),
        })


@extend_schema(responses={200: OpenApiTypes.OBJECT},
               description="État de la Couche D : fraîcheur de l'ETL horaire, CAPA qualité / HSE, modèles dbt.")
class EtatCoucheDView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(bi_etat.etat_couche_d(request.user))


class ScelleMartViewSet(viewsets.ReadOnlyModelViewSet):
    """Scellés des marts dbt (piste d'audit) : lecture, scellement à la demande, purge des scellés échus."""

    queryset = ScelleMart.objects.all()
    serializer_class = ScelleMartSerializer
    permission_classes = [CanReadCube]

    @extend_schema(request=None, responses={201: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["post"], url_path="sceller")
    def sceller(self, request):
        return Response({"resultats": pilotage.sceller_marts(request.user)}, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["post"], url_path="purger")
    def purger(self, request):
        return Response(pilotage.purger_archives_expirees())
