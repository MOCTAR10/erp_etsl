"""API des écarts a2 : cours de change, opérations en devise (EX-G-04), reconnaissance du revenu à l'avancement."""

from django.utils import timezone
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from config.inputs import date_input
from referentiels.models import TauxChange
from users.permissions import can_read_module

from . import avancement, devises
from .models import OperationDevise, ProvisionChange, ReconnaissanceRevenu
from .serializers import _MasqueMontantsMixin
from .services import CanValidateCompta, can_see_amount, parametres_provisoires
from .views import DjangoValidationMixin

PARAMS_DEVISES = ["DEVISE_ANCIENNETE_MAX_JOURS"]
PARAMS_REVENU = ["REVENU_METHODE"]


def _lecture_ou(valider):
    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [can_read_module("comptabilite")()]
        return [valider()]

    return get_permissions


# ------------------------------------------------------------------------------------------------ cours de change
class TauxChangeSerializer(serializers.ModelSerializer):
    devise_code = serializers.CharField(source="devise.code", read_only=True)
    est_provisoire = serializers.BooleanField(read_only=True)
    source_label = serializers.CharField(source="get_source_display", read_only=True)

    class Meta:
        model = TauxChange
        fields = ["id", "devise", "devise_code", "date", "taux", "source", "source_label", "statut_valeur",
                  "est_provisoire", "saisi_par", "confirme_par", "confirme_le", "created_at"]
        read_only_fields = fields


class TauxChangeViewSet(DjangoValidationMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Table des cours (XAF pour 1 unité) : saisie manuelle, import CSV, confirmation par ETSL."""

    serializer_class = TauxChangeSerializer
    get_permissions = _lecture_ou(CanValidateCompta)

    def get_queryset(self):
        qs = TauxChange.objects.select_related("devise").all()
        if self.request.query_params.get("devise"):
            qs = qs.filter(devise__code=self.request.query_params["devise"].upper())
        return qs

    def create(self, request):
        jour = date_input(request.data.get("date"), "date", default=timezone.localdate())
        taux, _ = devises.enregistrer_taux(request.data.get("devise"), jour, request.data.get("taux"), request.user)
        return Response(self.get_serializer(taux).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def importer(self, request):
        return Response(devises.importer_taux(request.data.get("contenu"), request.user))

    @action(detail=True, methods=["post"])
    def confirmer(self, request, pk=None):
        taux = self.get_object()
        taux.statut_valeur, taux.confirme_par, taux.confirme_le = TauxChange.StatutValeur.CONFIRME, request.user, timezone.now()
        taux.save(update_fields=["statut_valeur", "confirme_par", "confirme_le"])
        return Response(self.get_serializer(taux).data)

    @action(detail=False, methods=["get"])
    def situation(self, request):
        """Dernier cours par devise, âge, statut ; paramètre d'ancienneté provisoire ?"""
        return Response({"devises": devises.anciennete_cours(), "provisoire": parametres_provisoires(PARAMS_DEVISES)})

    @action(detail=False, methods=["get"])
    def convertir(self, request):
        jour = date_input(request.query_params.get("date"), "date", default=timezone.localdate())
        montant = devises._decimal(request.query_params.get("montant") or "0", "montant")
        cv, taux, prov = devises.contre_valeur(montant, request.query_params.get("devise") or "", jour)
        return Response({"contre_valeur": str(cv), "taux": str(taux), "provisoire": prov})


# ------------------------------------------------------------------------------------------------ opérations
class OperationDeviseSerializer(_MasqueMontantsMixin, serializers.ModelSerializer):
    champs_montants = ("montant_devise", "contre_valeur", "contre_valeur_reglement", "ecart_change", "ecart_latent")
    partner_name = serializers.CharField(source="partner.name", read_only=True)
    devise_code = serializers.CharField(source="devise.code", read_only=True)
    compte_code = serializers.CharField(source="compte_contrepartie.code", read_only=True)
    sens_label = serializers.CharField(source="get_sens_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    move_number = serializers.CharField(source="move.number", read_only=True, default=None)
    move_reglement_number = serializers.CharField(source="move_reglement.number", read_only=True, default=None)
    move_reevaluation_number = serializers.CharField(source="move_reevaluation.number", read_only=True, default=None)
    has_amount_access = serializers.SerializerMethodField()

    class Meta:
        model = OperationDevise
        fields = [
            "id", "code", "sens", "sens_label", "partner", "partner_name", "devise", "devise_code", "date", "libelle",
            "reference", "montant_devise", "compte_contrepartie", "compte_code", "affaire", "taux_origine",
            "taux_provisoire", "contre_valeur", "statut", "statut_label", "move", "move_number", "date_reglement",
            "taux_reglement", "contre_valeur_reglement", "ecart_change", "move_reglement", "move_reglement_number",
            "date_reevaluation", "taux_reevaluation", "ecart_latent", "move_reevaluation", "move_reevaluation_number",
            "has_amount_access", "cree_par", "created_at",
        ]
        read_only_fields = [
            "code", "taux_origine", "taux_provisoire", "contre_valeur", "statut", "move", "date_reglement",
            "taux_reglement", "contre_valeur_reglement", "ecart_change", "move_reglement", "date_reevaluation",
            "taux_reevaluation", "ecart_latent", "move_reevaluation", "cree_par", "created_at",
        ]

    def validate_montant_devise(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError("Le montant en devise doit être strictement positif.")
        return value

    def validate(self, attrs):
        compte = attrs.get("compte_contrepartie")
        sens = attrs.get("sens")
        if compte and sens:
            attendu = "7" if sens == OperationDevise.Sens.CREANCE else "62"
            if str(compte.code)[:1] not in attendu:
                raise serializers.ValidationError(
                    {"compte_contrepartie": "Créance : compte de produit (classe 7) ; dette : compte de charge ou "
                                            "d'immobilisation (classe 6 ou 2)."})
        return attrs


class OperationDeviseViewSet(DjangoValidationMixin, viewsets.ModelViewSet):
    serializer_class = OperationDeviseSerializer
    http_method_names = ["get", "post", "delete", "head", "options"]
    get_permissions = _lecture_ou(CanValidateCompta)
    search_fields = ("code", "libelle", "reference")

    def get_queryset(self):
        return OperationDevise.objects.select_related(
            "partner", "devise", "compte_contrepartie", "move", "move_reglement", "move_reevaluation"
        ).all()

    def perform_create(self, serializer):
        op = OperationDevise(**serializer.validated_data)
        devises.preparer(op)
        serializer.save(cree_par=self.request.user, contre_valeur=op.contre_valeur, taux_origine=op.taux_origine,
                        taux_provisoire=op.taux_provisoire)

    def destroy(self, request, *args, **kwargs):
        if self.get_object().statut != OperationDevise.Statut.BROUILLON:
            raise DRFValidationError("Opération comptabilisée : non supprimable (corrigez par extourne).")
        return super().destroy(request, *args, **kwargs)

    def _jour(self, request):
        return date_input(request.data.get("date"), "date", default=timezone.localdate())

    @action(detail=True, methods=["post"])
    def comptabiliser(self, request, pk=None):
        return Response(self.get_serializer(devises.comptabiliser(self.get_object(), request.user)).data)

    @action(detail=True, methods=["post"])
    def regler(self, request, pk=None):
        op = devises.regler(self.get_object(), self._jour(request), request.user)
        return Response(self.get_serializer(op).data)

    @action(detail=True, methods=["post"])
    def reevaluer(self, request, pk=None):
        op = devises.reevaluer(self.get_object(), self._jour(request), request.user)
        return Response(self.get_serializer(op).data)

    @action(detail=False, methods=["post"], url_path="reevaluer-tout")
    def reevaluer_tout(self, request):
        return Response(devises.reevaluer_tout(self._jour(request), request.user))


# ------------------------------------------------------------------------------------------------ avancement
def _montants(row, voit, champs=("ca_reference", "revenu_cumule", "facture_cumule", "ecart")):
    sortie = dict(row)
    for k in champs:
        if k in sortie:
            sortie[k] = str(sortie[k]) if voit else None
    if "pct_avancement" in sortie:
        sortie["pct_avancement"] = str(sortie["pct_avancement"])
    return sortie


class ReconnaissanceRevenuSerializer(_MasqueMontantsMixin, serializers.ModelSerializer):
    champs_montants = ("ca_reference", "revenu_cumule", "facture_cumule", "ecart")
    affaire_code = serializers.CharField(source="affaire.code", read_only=True)
    affaire_label = serializers.CharField(source="affaire.title", read_only=True)
    move_number = serializers.CharField(source="move.number", read_only=True, default=None)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    has_amount_access = serializers.SerializerMethodField()

    class Meta:
        model = ReconnaissanceRevenu
        fields = [
            "id", "code", "affaire", "affaire_code", "affaire_label", "date_arrete", "methode", "pct_avancement",
            "ca_reference", "revenu_cumule", "facture_cumule", "ecart", "detail", "methode_provisoire", "statut",
            "statut_label", "move", "move_number", "has_amount_access", "cree_par", "created_at",
        ]
        read_only_fields = fields


class ReconnaissanceRevenuViewSet(DjangoValidationMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                                  viewsets.GenericViewSet):
    """Reconnaissance du revenu à l'avancement : aperçu par affaire, comptabilisation (PAR / PCA), historique."""

    serializer_class = ReconnaissanceRevenuSerializer
    get_permissions = _lecture_ou(CanValidateCompta)

    def get_queryset(self):
        qs = ReconnaissanceRevenu.objects.select_related("affaire", "move").all()
        if self.request.query_params.get("affaire"):
            qs = qs.filter(affaire_id=self.request.query_params["affaire"])
        return qs

    @action(detail=False, methods=["get"])
    def apercu(self, request):
        jour = date_input(request.query_params.get("date"), "date", default=timezone.localdate())
        voit = can_see_amount(request.user)
        return Response({
            "date": jour.isoformat(), "methode": avancement.methode_courante(),
            "provisoire": parametres_provisoires(PARAMS_REVENU), "has_amount_access": voit,
            "rows": [_montants(r, voit) for r in avancement.apercu(jour)],
        })

    def create(self, request):
        from commercial.models import Affaire

        from .views import _est_uuid

        affaire_id = request.data.get("affaire")
        affaire = Affaire.objects.filter(pk=affaire_id).first() if _est_uuid(affaire_id) else None
        if affaire is None:
            raise DRFValidationError({"affaire": "Affaire inconnue."})
        jour = date_input(request.data.get("date_arrete"), "date_arrete", default=timezone.localdate())
        rec = avancement.comptabiliser(affaire, jour, request.user)
        return Response(self.get_serializer(rec).data, status=status.HTTP_201_CREATED)


# ------------------------------------------------------------------------------------------------ lot a7 : provision
class ProvisionChangeSerializer(_MasqueMontantsMixin, serializers.ModelSerializer):
    champs_montants = ("perte_latente", "gain_latent", "montant")
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    move_number = serializers.CharField(source="move.number", read_only=True, default=None)
    move_contre_passation_number = serializers.CharField(source="move_contre_passation.number", read_only=True, default=None)
    has_amount_access = serializers.SerializerMethodField()

    class Meta:
        model = ProvisionChange
        fields = [
            "id", "date_cloture", "perte_latente", "gain_latent", "montant", "operations", "statut", "statut_label",
            "move_number", "move_contre_passation_number", "date_contre_passation", "has_amount_access", "created_at",
        ]
        read_only_fields = fields


class ProvisionChangeViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Provisions pour perte de change latente (lecture) : dotées / contre-passées par « Réévaluer tout »."""

    serializer_class = ProvisionChangeSerializer
    get_permissions = _lecture_ou(CanValidateCompta)

    def get_queryset(self):
        return ProvisionChange.objects.select_related("move", "move_contre_passation").all()

    def list(self, request, *args, **kwargs):
        reponse = super().list(request, *args, **kwargs)
        if isinstance(reponse.data, dict):
            reponse.data["provisoire"] = parametres_provisoires(["DEVISE_PROVISION_PERTE"])
        return reponse
