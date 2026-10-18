"""API module M11 — Contrôle de gestion (RF-ERP-A0…A4)."""

from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from django.db.models import Prefetch

from .models import AnalyseEcart, Budget, BudgetLigne, BudgetRevision, ClotureGestion, ParametreGestion
from .serializers import (
    AnalyseEcartSerializer,
    BudgetLigneSerializer,
    BudgetRevisionSerializer,
    BudgetSerializer,
    ClotureGestionSerializer,
    ParametreGestionSerializer,
)
from users.models import User
from users.permissions import can_read_module
from .services import (
    CanApproveBudget,
    CanManageGestion,
    PARAMETRES_DEFAUT,
    compute_clotures_stats,
    compute_atterrissage,
    compute_doctrine,
    compute_niveaux_marge,
    compute_sous_activite,
    get_param_gestion,
    compute_marges,
    can_see_amount,
    compute_variance,
    detecter_ecarts,
)


class DjangoValidationMixin:
    """Convertit les `ValidationError` Django en réponses HTTP 400."""

    def handle_exception(self, exc):
        if isinstance(exc, DjangoValidationError):
            exc = DRFValidationError(getattr(exc, "messages", [str(exc)]))
        return super().handle_exception(exc)


def _apposer_visa(obj, request):
    """Pose le visa DAF ou CG demandé ; retourne True quand les DEUX visas sont réunis (CDC M11 §4.4).

    Deux personnes distinctes : celui qui a posé un visa ne pose pas l'autre (séparation des tâches).
    """
    visa = (request.data.get("visa") or "").strip().lower()
    if visa not in ("daf", "cg"):
        raise DRFValidationError({"visa": "Préciser le visa apposé : « daf » ou « cg »."})
    champ, autre = (("visa_daf_par", "visa_cg_par") if visa == "daf" else ("visa_cg_par", "visa_daf_par"))
    if getattr(obj, f"{champ}_id"):
        raise DRFValidationError({"visa": f"Visa {visa.upper()} déjà apposé."})
    if getattr(obj, f"{autre}_id") == request.user.id:
        raise DRFValidationError({"visa": "Double visa : le second visa doit être apposé par une autre personne."})
    setattr(obj, champ, request.user)
    setattr(obj, champ.replace("_par", "_le"), timezone.now())
    obj.save(update_fields=[champ, champ.replace("_par", "_le"), "updated_at"])
    return bool(obj.visa_daf_par_id and obj.visa_cg_par_id)


class BudgetViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    queryset = Budget.objects.select_related(
        "fiscal_year", "axis", "analytic"
    ).prefetch_related(
        Prefetch("lignes", queryset=BudgetLigne.objects.select_related("period__fiscal_year")),
        "revisions",
    )
    serializer_class = BudgetSerializer

    def get_permissions(self):
        if getattr(self, "action", None) in ("approuver", "cloturer"):
            return [CanApproveBudget()]
        return [CanManageGestion()]

    def get_queryset(self):
        qs = super().get_queryset()
        fiscal_year = self.request.query_params.get("fiscal_year")
        type_budget = self.request.query_params.get("type_budget")
        statut = self.request.query_params.get("statut")
        axis = self.request.query_params.get("axis")
        analytic = self.request.query_params.get("analytic")
        if fiscal_year:
            qs = qs.filter(fiscal_year_id=fiscal_year)
        if type_budget:
            qs = qs.filter(type_budget=type_budget)
        if statut:
            qs = qs.filter(statut=statut)
        if axis:
            qs = qs.filter(axis_id=axis)
        if analytic:
            qs = qs.filter(analytic_id=analytic)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["get"])
    def variance(self, request, pk=None):
        budget = self.get_object()
        result = compute_variance(budget)
        return Response(result)

    def perform_update(self, serializer):
        # Version budgétaire scellée : un budget approuvé ou clôturé ne se modifie que par révision (R1-R4).
        if serializer.instance.statut != Budget.Statut.BROUILLON:
            raise DRFValidationError("Budget approuvé (version scellée) : modification par révision R1-R4 uniquement.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.statut != Budget.Statut.BROUILLON:
            raise DRFValidationError("Budget approuvé ou clôturé (version scellée) : suppression interdite.")
        instance.delete()

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def approuver(self, request, pk=None):
        """Visa DAF ou CG sur la version V0 ; le budget entre en vigueur au second visa."""
        budget = Budget.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if budget.statut != Budget.Statut.BROUILLON:
            raise DRFValidationError("Seul un budget brouillon peut être approuvé.")
        if _apposer_visa(budget, request):
            budget.statut = Budget.Statut.APPROUVE
            budget.save(update_fields=["statut", "updated_at"])
        return Response(self.get_serializer(budget).data)

    @action(detail=True, methods=["post"])
    def cloturer(self, request, pk=None):
        budget = self.get_object()
        if budget.statut != Budget.Statut.APPROUVE:
            raise DRFValidationError("Seul un budget approuvé peut être clôturé.")
        budget.statut = Budget.Statut.CLOTURE
        budget.save(update_fields=["statut", "updated_at"])
        return Response(self.get_serializer(budget).data)


class BudgetLigneViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    queryset = BudgetLigne.objects.select_related("budget", "period__fiscal_year").all()
    serializer_class = BudgetLigneSerializer
    permission_classes = [CanManageGestion]

    def get_queryset(self):
        qs = super().get_queryset()
        budget = self.request.query_params.get("budget")
        if budget:
            qs = qs.filter(budget_id=budget)
        return qs

    @staticmethod
    def _verifier_brouillon(budget):
        # Les lignes mensuelles font partie de la version budgétaire : scellées avec elle (révision R1-R4 sur le total).
        if budget is not None and budget.statut != Budget.Statut.BROUILLON:
            raise DRFValidationError("Budget approuvé (version scellée) : lignes mensuelles non modifiables.")

    def perform_create(self, serializer):
        self._verifier_brouillon(serializer.validated_data.get("budget"))
        serializer.save()

    def perform_update(self, serializer):
        self._verifier_brouillon(serializer.instance.budget)
        self._verifier_brouillon(serializer.validated_data.get("budget"))
        serializer.save()

    def perform_destroy(self, instance):
        self._verifier_brouillon(instance.budget)
        instance.delete()


class BudgetRevisionViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    """Révisions budgétaires R1-R4 (RF-ERP-A1)."""

    queryset = BudgetRevision.objects.select_related("budget", "created_by").all()
    serializer_class = BudgetRevisionSerializer

    def get_permissions(self):
        if getattr(self, "action", None) == "appliquer":
            return [CanApproveBudget()]
        return [CanManageGestion()]

    def get_queryset(self):
        qs = super().get_queryset()
        budget = self.request.query_params.get("budget")
        if budget:
            qs = qs.filter(budget_id=budget)
        return qs

    def perform_create(self, serializer):
        budget = serializer.validated_data.get("budget")
        if budget.statut == Budget.Statut.CLOTURE:
            raise DRFValidationError("Budget clôturé : aucune révision possible.")
        numero = budget.revisions.count() + 1
        if numero > 4:
            raise DRFValidationError(
                "Au plus 4 révisions budgétaires annuelles par budget (R1-R4, RF-ERP-A1)."
            )
        nouveau = serializer.validated_data.get("nouveau_montant") or budget.montant
        serializer.save(
            code=None,
            numero=numero,
            ancien_montant=budget.montant,
            nouveau_montant=nouveau,
            statut=BudgetRevision.Statut.BROUILLON,
            created_by=self.request.user,
        )

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def appliquer(self, request, pk=None):
        """Visa DAF ou CG sur la révision ; elle s'applique au budget au second visa (R1-R4)."""
        revision = BudgetRevision.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if revision.statut != BudgetRevision.Statut.BROUILLON:
            raise DRFValidationError("Révision déjà appliquée ou annulée.")
        budget = revision.budget
        if budget.statut == Budget.Statut.CLOTURE:
            raise DRFValidationError("Budget clôturé : révision non applicable.")
        # Révision préparée sur un montant périmé (une autre révision a été appliquée entre-temps) : l'appliquer
        # écraserait silencieusement la précédente. Il faut la refaire sur le montant en vigueur.
        if revision.ancien_montant is not None and revision.ancien_montant != budget.montant:
            raise DRFValidationError(
                f"Le budget a changé depuis la préparation de {revision.code} "
                f"({revision.ancien_montant} → {budget.montant}) : préparez une nouvelle révision."
            )
        if not _apposer_visa(revision, request):
            return Response(self.get_serializer(revision).data)
        budget.montant = revision.nouveau_montant
        budget.save(update_fields=["montant", "updated_at"])
        revision.statut = BudgetRevision.Statut.APPLIQUEE
        revision.save(update_fields=["statut", "updated_at"])
        return Response(
            BudgetSerializer(budget, context=self.get_serializer_context()).data
        )


class ClotureGestionViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    queryset = ClotureGestion.objects.select_related("period", "created_by").all()
    serializer_class = ClotureGestionSerializer

    def get_permissions(self):
        if getattr(self, "action", None) in ("realiser", "publier"):
            return [CanApproveBudget()]
        return [CanManageGestion()]

    def get_queryset(self):
        qs = super().get_queryset()
        fiscal_year = self.request.query_params.get("fiscal_year")
        statut = self.request.query_params.get("statut")
        if fiscal_year:
            if not fiscal_year.isdigit():
                raise DRFValidationError("Paramètre `fiscal_year` doit être un entier.")
            qs = qs.filter(period__fiscal_year_id=fiscal_year)
        if statut:
            qs = qs.filter(statut=statut)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def realiser(self, request, pk=None):
        cloture = self.get_object()
        if cloture.statut == ClotureGestion.Statut.REALISEE:
            raise DRFValidationError("Clôture déjà réalisée.")
        valeur = request.data.get("date_cloture")
        if isinstance(valeur, str):
            try:
                valeur = date.fromisoformat(valeur)
            except (TypeError, ValueError):
                raise DRFValidationError("`date_cloture` doit être une date ISO.")
        cloture.date_cloture = valeur or (cloture.period.end_date + timedelta(days=2))
        cloture.statut = ClotureGestion.Statut.REALISEE
        cloture.save(update_fields=["date_cloture", "statut", "updated_at"])
        return Response(self.get_serializer(cloture).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def publier(self, request, pk=None):
        """Publie le reporting du mois à la Direction (attestation côté serveur) ; exige la clôture réalisée."""
        from workflow.notifications import notify

        cloture = ClotureGestion.objects.select_for_update(of=("self",)).select_related("period").get(
            pk=self.get_object().pk
        )
        if cloture.statut != ClotureGestion.Statut.REALISEE:
            raise DRFValidationError("La clôture de gestion doit être réalisée avant la publication.")
        if cloture.date_publication:
            raise DRFValidationError("Reporting déjà publié.")
        cloture.date_publication = timezone.localdate()
        cloture.publie_par = request.user
        cloture.save(update_fields=["date_publication", "publie_par", "updated_at"])
        for user in User.objects.filter(
            role__in=(User.Role.PDG, User.Role.DGA, User.Role.DIRECTION), is_active=True
        ):
            notify(
                user, f"Reporting de gestion publié : {cloture.period}",
                f"Le reporting de {cloture.period} est publié (statut : {cloture.reporting_statut}).",
                kind="info",
            )
        return Response(self.get_serializer(cloture).data)

    @action(detail=False, methods=["get"])
    def stats(self, request):
        fiscal_year = request.query_params.get("fiscal_year") or None
        if fiscal_year and not fiscal_year.isdigit():
            raise DRFValidationError("Paramètre `fiscal_year` doit être un entier.")
        result = compute_clotures_stats(fiscal_year)
        return Response(result)


@extend_schema(
    parameters=[
        OpenApiParameter("fiscal_year", type=int, required=True, description="Exercice (année)."),
        OpenApiParameter("axis", type=str, required=False, description="Code axe analytique."),
        OpenApiParameter("analytic", type=str, required=False, description="Code compte analytique."),
    ],
    responses={200: OpenApiTypes.OBJECT},
)
class MargesView(viewsets.ViewSet):
    """Marges par axe analytique (RF-ERP-A2) — coût GR isolé (A4)."""

    permission_classes = [can_read_module("controle_gestion")]

    def list(self, request):
        fiscal_year = request.query_params.get("fiscal_year")
        if not fiscal_year:
            raise DRFValidationError("Paramètre `fiscal_year` requis.")
        if not fiscal_year.isdigit():
            raise DRFValidationError("Paramètre `fiscal_year` doit être un entier.")
        axis = request.query_params.get("axis")
        analytic = request.query_params.get("analytic")
        if axis and not axis.isdigit():
            raise DRFValidationError("Paramètre `axis` doit être un entier (id d'axe).")
        if analytic and not analytic.isdigit():
            raise DRFValidationError("Paramètre `analytic` doit être un entier (id de compte analytique).")
        result = compute_marges(fiscal_year, axis=axis, analytic=analytic)
        return Response(result, status=status.HTTP_200_OK)


class ConsommationsStockView(viewsets.ViewSet):
    """Consommations matières et valeur du stock publiées par M5 (clôture M5, CDC M5 §7.11) : sans ressaisie."""

    permission_classes = [can_read_module("controle_gestion")]

    def list(self, request):
        from stocks.models import ValorisationMensuelle

        periode = request.query_params.get("periode")
        qs = ValorisationMensuelle.objects.select_related("depot").order_by("periode", "depot__code")
        if periode:
            qs = qs.filter(periode=periode)
        voir = can_see_amount(request.user)
        axes, depots = {}, []
        for v in qs:
            depots.append({
                "periode": v.periode, "depot": v.depot.code,
                "valeur_stock": f"{v.valeur_stock:.2f}" if voir else None,
                "consommation": f"{v.consommation:.2f}" if voir else None,
            })
            for ligne in v.ventilation:
                axes[ligne["axe"]] = axes.get(ligne["axe"], Decimal("0")) + Decimal(ligne["valeur"])
        return Response({
            "depots": depots,
            "consommations_par_axe": [
                {"axe": a, "valeur": f"{x:.2f}" if voir else None} for a, x in sorted(axes.items())
            ],
        })


class AnalyseEcartViewSet(viewsets.ReadOnlyModelViewSet):
    """Analyses d'écart > 10 % (lot 15, CDC M11 §4.4) : ouvertes par la détection, rendues par `analyser`."""

    queryset = AnalyseEcart.objects.select_related("budget", "period", "analyse_par").all()
    serializer_class = AnalyseEcartSerializer
    permission_classes = [CanManageGestion]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        if budget := params.get("budget"):
            qs = qs.filter(budget_id=budget)
        if params.get("en_retard") == "1":
            qs = qs.filter(statut=AnalyseEcart.Statut.A_ANALYSER, echeance__lt=timezone.localdate())
        return qs

    @action(detail=False, methods=["post"])
    def detecter(self, request):
        return Response({"analyses": [a.code for a in detecter_ecarts()]})

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def analyser(self, request, pk=None):
        analyse = AnalyseEcart.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if analyse.statut != AnalyseEcart.Statut.A_ANALYSER:
            raise DRFValidationError("Analyse déjà rendue.")
        texte = str(request.data.get("analyse") or "").strip()
        if not texte:
            raise DRFValidationError({"analyse": "Explication de l'écart obligatoire."})
        analyse.analyse = texte
        analyse.actions = str(request.data.get("actions") or "").strip()
        analyse.statut = AnalyseEcart.Statut.ANALYSEE
        analyse.analyse_par = request.user
        analyse.analyse_le = timezone.now()
        analyse.save()
        return Response(self.get_serializer(analyse).data)


def _fiscal_year_requis(request):
    fiscal_year = request.query_params.get("fiscal_year")
    if not fiscal_year:
        raise DRFValidationError("Paramètre `fiscal_year` requis.")
    if not fiscal_year.isdigit():
        raise DRFValidationError("Paramètre `fiscal_year` doit être un entier.")
    return fiscal_year


class SousActiviteView(viewsets.ViewSet):
    """Classement des budgets en centres 90 / 91 / 99 selon le taux de sous-activité (CDC M11 §4.4)."""

    permission_classes = [can_read_module("controle_gestion")]

    @extend_schema(
        parameters=[OpenApiParameter("fiscal_year", type=int, required=True)], responses={200: OpenApiTypes.OBJECT}
    )
    def list(self, request):
        result = compute_sous_activite(_fiscal_year_requis(request))
        if not can_see_amount(request.user):
            for r in result["rows"]:
                r["budget_ecoule"] = r["realise"] = None
        return Response(result)


class DoctrineView(viewsets.ViewSet):
    """Doctrine d'imputation Mix A / B / C : répartition réelle face à la cible paramétrée (valeurs RGM_*)."""

    permission_classes = [can_read_module("controle_gestion")]

    @extend_schema(
        parameters=[OpenApiParameter("fiscal_year", type=int, required=True)], responses={200: OpenApiTypes.OBJECT}
    )
    def list(self, request):
        result = compute_doctrine(_fiscal_year_requis(request))
        if not can_see_amount(request.user):
            for r in result["lignes"]:
                r["montant"] = None
        return Response(result)


class ParametreGestionViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    """Paramètres modifiables par ETSL ; création/suppression interdites (définis par le code)."""

    queryset = ParametreGestion.objects.all()
    serializer_class = ParametreGestionSerializer
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_queryset(self):
        for code in PARAMETRES_DEFAUT:
            get_param_gestion(code)
        return super().get_queryset()

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [can_read_module("controle_gestion")()]
        if getattr(self, "action", None) == "confirmer":
            return [CanApproveBudget()]
        return [CanManageGestion()]

    def create(self, request, *args, **kwargs):
        raise DRFValidationError("Les paramètres sont prédéfinis : modifiez leur valeur.")

    @action(detail=True, methods=["post"], url_path="confirmer")
    def confirmer(self, request, pk=None):
        p = self.get_object()
        p.statut_valeur = ParametreGestion.StatutValeur.CONFIRME
        p.confirme_par = request.user
        p.confirme_le = timezone.now()
        p.save(update_fields=["statut_valeur", "confirme_par", "confirme_le"])
        return Response(self.get_serializer(p).data)


class NiveauxMargeView(viewsets.ViewSet):
    """Marges brute / opérationnelle / nette (coût GR isolé en 618)."""

    permission_classes = [can_read_module("controle_gestion")]

    @extend_schema(
        parameters=[OpenApiParameter("fiscal_year", type=int, required=True)], responses={200: OpenApiTypes.OBJECT}
    )
    def list(self, request):
        result = compute_niveaux_marge(_fiscal_year_requis(request))
        if not can_see_amount(request.user):
            result = {k: (None if k.startswith(("produits", "charges", "marge", "cout")) else v) for k, v in result.items()}
        return Response(result)


class AtterrissageView(viewsets.ViewSet):
    """Atterrissage de fin d'exercice par budget et marge à terminaison."""

    permission_classes = [can_read_module("controle_gestion")]

    @extend_schema(
        parameters=[OpenApiParameter("fiscal_year", type=int, required=True)], responses={200: OpenApiTypes.OBJECT}
    )
    def list(self, request):
        result = compute_atterrissage(_fiscal_year_requis(request))
        if not can_see_amount(request.user):
            return Response({"rows": [], "marge_a_terminaison": None, "totaux": None})
        return Response(result)


class MaintenanceCoutsView(viewsets.ViewSet):
    """Coût de maintenance par machine et par mois publié par M8 (clôture M8 → M11) : sans ressaisie ni écriture.

    Les machines GLOBAL RENTAL restent au compte 618 (isolé), le reste au 624 ; montants masqués hors cercle RF-59.
    """

    permission_classes = [can_read_module("controle_gestion")]

    @extend_schema(
        parameters=[OpenApiParameter("periode", type=str, required=True)], responses={200: OpenApiTypes.OBJECT}
    )
    def list(self, request):
        from maintenance.services import couts_maintenance

        periode = request.query_params.get("periode")
        if not periode:
            raise DRFValidationError("Paramètre `periode` (AAAA-MM) requis.")
        try:
            result = couts_maintenance(periode)
        except ValueError as exc:
            raise DRFValidationError(str(exc))
        voir = can_see_amount(request.user)

        def montant(x):
            return f"{x:.2f}" if voir else None

        rows = [
            {**r, "main_oeuvre": montant(r["main_oeuvre"]), "pieces": montant(r["pieces"]), "total": montant(r["total"])}
            for r in result["rows"]
        ]
        return Response({
            "periode": periode, "rows": rows,
            "totaux": {k: montant(v) for k, v in result["totaux"].items()},
        })


class GrAffairesView(viewsets.ViewSet):
    """Coût GLOBAL RENTAL ventilé par affaire, publié par M4 (clôture M4, CDC M4 §12.11 → M11) : sans ressaisie.

    Le coût reste au compte 618 (isolé des marges) ; avec `fiscal_year`, chaque affaire porte sa marge comptable
    hors GR (compute_marges) puis la marge après coût GR estimé.
    """

    permission_classes = [can_read_module("controle_gestion")]

    @extend_schema(
        parameters=[
            OpenApiParameter("periode", type=str, required=True),
            OpenApiParameter("fiscal_year", type=int, required=False),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def list(self, request):
        from logistique.services import ventilation_gr

        periode = request.query_params.get("periode")
        if not periode:
            raise DRFValidationError("Paramètre `periode` (AAAA-MM) requis.")
        result = ventilation_gr(periode)
        fiscal_year = request.query_params.get("fiscal_year")
        if fiscal_year and not fiscal_year.isdigit():
            raise DRFValidationError("Paramètre `fiscal_year` doit être un entier.")
        marges = {}
        if fiscal_year:
            marges = {r["analytic"]: r for r in compute_marges(fiscal_year)["rows"]}
        voir = can_see_amount(request.user)

        def montant(x):
            return f"{x:.2f}" if voir else None

        rows = []
        for r in result["rows"]:
            m = marges.get(r["analytic"]) if r["analytic"] else None
            hors_gr = (m["marge"] if m else Decimal("0")) if fiscal_year and not r["non_affecte"] else None
            rows.append({
                **r,
                "consommation": f"{r['consommation']:.2f}",
                "cout_gr": montant(r["cout_gr"]), "penalites": montant(r["penalites"]), "total_gr": montant(r["total_gr"]),
                "marge_hors_gr": montant(hors_gr) if hors_gr is not None else None,
                "marge_apres_gr": montant(hors_gr - r["total_gr"]) if hors_gr is not None else None,
            })
        return Response({
            "periode": result["periode"], "compte": result["compte"], "rows": rows,
            "total_gr": montant(result["total_gr"]), "provisoire": result["provisoire"],
        })
