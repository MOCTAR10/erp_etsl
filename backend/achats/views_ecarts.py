"""API des écarts M2 : paramètres provisoires, agréments fournisseurs, règles d'inspection, avoirs, pièces archivées."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from comptabilite.services import CanValidateCompta
from users.permissions import can_read_module

from .ecarts import PARAMETRES_ACHATS_DEFAUT, ajouter_mois, appliquer_agrement, assurer_parametres, catalogue_fournisseurs, comptabiliser_avoir, get_param
from .models import AgrementFournisseur, AvoirFournisseur, GoodsReceipt, LitigeFournisseur, ParametreAchats, PurchaseOrder, RegleInspectionReception
from .serializers_ecarts import (
    AgrementFournisseurSerializer,
    AvoirFournisseurSerializer,
    ParametreAchatsSerializer,
    RegleInspectionReceptionSerializer,
)
from .services import (
    ACHAT_PARAM_CONFIRM_ROLES,
    AGREMENT_HSE_VALIDATION_ROLES,
    AGREMENT_QUALITE_VALIDATION_ROLES,
    AGREMENT_WRITE_ROLES,
    CanManageAchats,
    can_see_amount,
    is_admin_or_staff,
)
from config.i18n import tr


def _drf(exc):
    return ValidationError(exc.message_dict if hasattr(exc, "error_dict") else {"detail": exc.messages})


class CanManageAgrement(BasePermission):
    """Demande d'agrément / règle d'inspection : Achats, QA/QC (M6) et HSE (M7)."""

    def has_permission(self, request, view):
        u = getattr(request, "user", None)
        return bool(u and u.is_authenticated and (is_admin_or_staff(u) or u.role in AGREMENT_WRITE_ROLES))


def _peut_confirmer(user):
    return is_admin_or_staff(user) or user.role in ACHAT_PARAM_CONFIRM_ROLES


class _LectureAchats:
    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [can_read_module("achats")()]
        return [p() for p in self.ecriture]


class ParametreAchatsViewSet(_LectureAchats, viewsets.ModelViewSet):
    """Paramètres M2 attendus d'ETSL : modifiables par les rôles Achats, confirmés par la direction / finance."""

    serializer_class = ParametreAchatsSerializer
    ecriture = [CanManageAchats]
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_queryset(self):
        assurer_parametres()
        return ParametreAchats.objects.filter(code__in=PARAMETRES_ACHATS_DEFAUT)

    def create(self, request, *args, **kwargs):
        return Response({"detail": "Paramètres prédéfinis : modification seulement."}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def confirmer(self, request, pk=None):
        if not _peut_confirmer(request.user):
            return Response({"detail": "Confirmation réservée à la direction et à la finance."}, status=status.HTTP_403_FORBIDDEN)
        p = ParametreAchats.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        p.statut_valeur, p.confirme_par, p.confirme_le = ParametreAchats.StatutValeur.CONFIRME, request.user, timezone.now()
        p.save(update_fields=["statut_valeur", "confirme_par", "confirme_le"])
        return Response(self.get_serializer(p).data)


class RegleInspectionReceptionViewSet(_LectureAchats, viewsets.ModelViewSet):
    """Règles ITP / CND à réception par catégorie d'article (provisoires, à confirmer par ETSL)."""

    serializer_class = RegleInspectionReceptionSerializer
    ecriture = [CanManageAgrement]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return RegleInspectionReception.objects.select_related("article")

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def confirmer(self, request, pk=None):
        if not _peut_confirmer(request.user):
            return Response({"detail": "Confirmation réservée à la direction et à la finance."}, status=status.HTTP_403_FORBIDDEN)
        r = RegleInspectionReception.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        r.statut_valeur, r.confirme_par, r.confirme_le = RegleInspectionReception.StatutValeur.CONFIRME, request.user, timezone.now()
        r.save(update_fields=["statut_valeur", "confirme_par", "confirme_le", "updated_at"])
        return Response(self.get_serializer(r).data)


class AgrementFournisseurViewSet(_LectureAchats, viewsets.ModelViewSet):
    """Agréments fournisseurs : demande (Achats / QA-QC / HSE), décision du service du domaine, report sur la fiche tiers."""

    serializer_class = AgrementFournisseurSerializer
    ecriture = [CanManageAgrement]
    http_method_names = ["get", "post", "patch", "head", "options"]
    search_fields = ("code", "fournisseur__name", "reference")

    def get_queryset(self):
        qs = AgrementFournisseur.objects.select_related("fournisseur")
        params = self.request.query_params
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        if fournisseur := params.get("fournisseur"):
            qs = qs.filter(fournisseur_id=fournisseur)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def _decision(self, request):
        agrement = AgrementFournisseur.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        roles = AGREMENT_QUALITE_VALIDATION_ROLES if agrement.domaine == AgrementFournisseur.Domaine.QUALITE else AGREMENT_HSE_VALIDATION_ROLES
        if not (is_admin_or_staff(request.user) or request.user.role in roles):
            service = "QA/QC (M6)" if agrement.domaine == AgrementFournisseur.Domaine.QUALITE else "HSE (M7)"
            raise PermissionDenied(tr("Décision réservée au service %(service)s et à la Direction.") % {"service": service})
        if agrement.statut != AgrementFournisseur.Statut.DEMANDE:
            raise ValidationError({"detail": "Agrément déjà décidé."})
        return agrement

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def valider(self, request, pk=None):
        """Valide l'agrément (date de fin saisie, sinon durée paramétrée) et met à jour la fiche fournisseur."""
        from rest_framework.fields import DateField

        agrement = self._decision(request)
        fin = request.data.get("date_fin")
        if fin:
            fin = DateField().run_validation(fin)
            if fin < agrement.date_evaluation:
                raise ValidationError({"date_fin": "La fin d'agrément doit suivre la date d'évaluation."})
            agrement.date_fin = fin
        elif agrement.date_fin is None:
            agrement.date_fin = ajouter_mois(agrement.date_evaluation, int(get_param("AGREMENT_DUREE_MOIS")))
        agrement.statut, agrement.valide_par, agrement.valide_le = AgrementFournisseur.Statut.VALIDE, request.user, timezone.now()
        agrement.save()
        appliquer_agrement(agrement)
        return Response(self.get_serializer(agrement).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def refuser(self, request, pk=None):
        """Refus motivé : l'agrément du domaine est retiré de la fiche fournisseur (aucun BC ne peut plus être émis)."""
        agrement = self._decision(request)
        motif = str(request.data.get("motif") or "").strip()
        if not motif:
            raise ValidationError({"motif": "Motif du refus obligatoire."})
        agrement.statut, agrement.motif_refus = AgrementFournisseur.Statut.REFUSE, motif
        agrement.valide_par, agrement.valide_le = request.user, timezone.now()
        agrement.save()
        appliquer_agrement(agrement)
        return Response(self.get_serializer(agrement).data)

    @action(detail=False, methods=["get"])
    def catalogue(self, request):
        """Catalogue fournisseurs : agréments qualité / HSE, alertes de renouvellement, note /100."""
        return Response(catalogue_fournisseurs())


class AvoirFournisseurViewSet(_LectureAchats, viewsets.ModelViewSet):
    """Avoirs fournisseurs : saisie (Achats), comptabilisation (cercle comptable) = contre-passation au prorata."""

    serializer_class = AvoirFournisseurSerializer
    ecriture = [CanManageAchats]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    search_fields = ("code", "reference_fournisseur", "facture__code")

    def get_permissions(self):
        if self.action == "comptabiliser":
            return [CanValidateCompta()]
        return super().get_permissions()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["can_view_amount"] = can_see_amount(self.request.user)
        return context

    def get_queryset(self):
        qs = AvoirFournisseur.objects.select_related("facture__supplier", "move", "document_ged")
        if facture := self.request.query_params.get("facture"):
            qs = qs.filter(facture_id=facture)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_destroy(self, instance):
        if instance.statut != AvoirFournisseur.Statut.BROUILLON:
            raise ValidationError({"detail": "Avoir comptabilisé : suppression impossible (contre-passer)."})
        instance.delete()

    @action(detail=True, methods=["post"])
    def comptabiliser(self, request, pk=None):
        try:
            avoir = comptabiliser_avoir(self.get_object(), request.user)
        except DjangoValidationError as exc:
            raise _drf(exc)
        return Response(self.get_serializer(avoir).data)


def pieces_archivees():
    """Pièces d'achat scellées en GED (BC, réceptions, litiges, avoirs) avec leur durée de conservation."""
    rows = []
    sources = (
        ("BC", PurchaseOrder.objects.filter(document_ged__isnull=False)),
        ("Réception", GoodsReceipt.objects.filter(document_ged__isnull=False)),
        ("Litige", LitigeFournisseur.objects.filter(document_ged__isnull=False)),
        ("Avoir", AvoirFournisseur.objects.filter(document_ged__isnull=False)),
    )
    for nature, qs in sources:
        for obj in qs.select_related("document_ged__type").order_by("-document_ged__archived_at")[:100]:
            doc = obj.document_ged
            rows.append({
                "nature": nature, "piece": obj.code, "document": str(doc.pk), "titre": doc.title,
                "archive_le": doc.archived_at, "conservation_ans": doc.type.retention_years if doc.type_id else None,
                "sha256": doc.sha256,
            })
    rows.sort(key=lambda r: r["archive_le"] or timezone.now(), reverse=True)
    return {"rows": rows, "conservation_ans": int(get_param("RETENTION_PIECES_ACHAT_ANS"))}

