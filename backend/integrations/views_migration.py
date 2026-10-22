"""API de la reprise de données (CDC §10) : catalogue des gabarits, modèles vides, chargement à blanc / réel,
historique et rapport d'anomalies, rapprochements C1-C10, paramètres provisoires, historique de paie (lecture seule)."""

from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from users.models import User

from .importers_migration import (
    GABARITS,
    FichierErreur,
    _cercle_compta,
    assurer_parametres,
    executer_lot,
    gabarits_autorises,
    modele_vide,
    peut_gabarit,
    rapport_csv,
)
from .models_migration import HistoriquePaie, LigneReprise, LotReprise, ParametreReprise
from .rapprochements import rapprochements, rapprochements_csv, synthese_lots

CONFIRMATION_ROLES = (User.Role.ADMIN, User.Role.PDG, User.Role.DGA, User.Role.DIRECTION, User.Role.FINANCE)


class CanReprise(BasePermission):
    """Au moins un gabarit autorisé : cercle comptable (API d'import), RH (salariés / paie), QA/QC (qualité)."""

    message = "Rôle non autorisé à la reprise de données."

    def has_permission(self, request, view):
        return bool(gabarits_autorises(request.user))


class CanRepriseCompta(BasePermission):
    """Rapprochements (montants) et paramètres : cercle comptable de l'API d'import."""

    message = "Réservé au cercle comptable (administrateur, comptable, finance, direction)."

    def has_permission(self, request, view):
        return _cercle_compta(request.user)


def _fichier(contenu, nom, type_mime):
    reponse = HttpResponse(contenu, content_type=type_mime)
    reponse["Content-Disposition"] = f'attachment; filename="{nom}"'
    return reponse


class CatalogueView(APIView):
    """Gabarits que l'utilisateur peut charger : colonnes, clé d'idempotence, formats."""

    permission_classes = [CanReprise]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return Response([
            {
                "code": g.code, "libelle": g.libelle, "objet": g.objet, "cle": g.cle, "formats": list(g.formats),
                "options": list(g.options), "note": g.note, "sensibles": list(g.sensibles),
                "colonnes": [{"nom": c.nom, "obligatoire": c.obligatoire, "aide": c.aide, "exemple": c.exemple}
                             for c in g.colonnes],
            }
            for g in gabarits_autorises(request.user)
        ])


class ModeleView(APIView):
    """GET `?gabarit=<code>&type=csv|xml` : modèle vide (en-tête + ligne d'exemple)."""

    permission_classes = [CanReprise]

    @extend_schema(responses={200: OpenApiTypes.BINARY})
    def get(self, request):
        gabarit = GABARITS.get(request.query_params.get("gabarit", ""))
        if gabarit is None or not peut_gabarit(request.user, gabarit):
            return Response({"detail": "gabarit inconnu ou non autorisé."}, status=status.HTTP_404_NOT_FOUND)
        fmt = request.query_params.get("type", "csv")
        if fmt not in ("csv", "xml"):
            return Response({"detail": "type attendu : csv ou xml."}, status=status.HTTP_400_BAD_REQUEST)
        nom = f"{'manifeste' if gabarit.code == 'ged' else 'modele_' + gabarit.code}.{fmt}"
        return _fichier(modele_vide(gabarit, fmt), nom, "application/xml" if fmt == "xml" else "text/csv; charset=utf-8")


class LotRepriseSerializer(serializers.ModelSerializer):
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    mode_label = serializers.CharField(source="get_mode_display", read_only=True)
    gabarit_label = serializers.SerializerMethodField()
    cree_par_email = serializers.EmailField(source="cree_par.email", read_only=True, default=None)

    class Meta:
        model = LotReprise
        fields = ["id", "gabarit", "gabarit_label", "mode", "mode_label", "format", "statut", "statut_label", "fichier",
                  "empreinte", "lignes", "creees", "mises_a_jour", "doublons", "erreurs", "taux_erreur", "seuil_erreur",
                  "message", "rejeu_de", "cree_par", "cree_par_email", "cree_le"]
        read_only_fields = fields

    def get_gabarit_label(self, obj):
        g = GABARITS.get(obj.gabarit)
        return g.libelle if g else obj.gabarit


class LigneRepriseSerializer(serializers.ModelSerializer):
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)

    class Meta:
        model = LigneReprise
        fields = ["id", "numero", "statut", "statut_label", "cle", "donnees", "erreur"]
        read_only_fields = fields


class ImportRepriseView(APIView):
    """POST multipart : `gabarit`, `file`, `mode` (blanc | reel), `force`, et pour la balance `date`, `total_controle`."""

    permission_classes = [CanReprise]

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: LotRepriseSerializer, 200: LotRepriseSerializer})
    def post(self, request):
        gabarit = GABARITS.get(str(request.data.get("gabarit", "")))
        if gabarit is None:
            return Response({"detail": "gabarit inconnu."}, status=status.HTTP_400_BAD_REQUEST)
        if not peut_gabarit(request.user, gabarit):
            return Response({"detail": "Gabarit non autorisé pour votre fonction."}, status=status.HTTP_403_FORBIDDEN)
        upload = request.FILES.get("file")
        if upload is None:
            return Response({"detail": "fichier requis (champ « file »)."}, status=status.HTTP_400_BAD_REQUEST)
        mode = str(request.data.get("mode", LotReprise.Mode.BLANC))
        if mode not in LotReprise.Mode.values:
            return Response({"detail": "mode attendu : blanc ou reel."}, status=status.HTTP_400_BAD_REQUEST)
        force = str(request.data.get("force", "")).lower() in ("1", "true", "yes", "oui")
        options = {k: str(request.data.get(k, "")) for k in gabarit.options}
        try:
            lot, rejeu = executer_lot(gabarit.code, upload.name, upload.read(), request.user, mode=mode, force=force,
                                      options=options)
        except FichierErreur as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        donnees = LotRepriseSerializer(lot).data
        donnees["rejeu"] = rejeu
        return Response(donnees, status=status.HTTP_200_OK if rejeu else status.HTTP_201_CREATED)


class LotRepriseViewSet(viewsets.ReadOnlyModelViewSet):
    """Historique des lots de reprise (gabarits autorisés seulement) ; `rapport/` = anomalies ligne par ligne (CSV)."""

    permission_classes = [CanReprise]
    serializer_class = LotRepriseSerializer

    def get_queryset(self):
        codes = [g.code for g in gabarits_autorises(self.request.user)]
        qs = LotReprise.objects.filter(gabarit__in=codes).select_related("cree_par")
        if self.request.query_params.get("gabarit"):
            qs = qs.filter(gabarit=self.request.query_params["gabarit"])
        return qs

    @extend_schema(responses={200: LigneRepriseSerializer(many=True)})
    @action(detail=True, methods=["get"])
    def lignes(self, request, pk=None):
        lot = self.get_object()
        qs = lot.lignes_rapport.all()
        if request.query_params.get("erreurs") in ("1", "true"):
            qs = qs.filter(statut=LigneReprise.Statut.ERREUR)
        return Response(LigneRepriseSerializer(qs[:2000], many=True).data)

    @extend_schema(responses={200: OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def rapport(self, request, pk=None):
        lot = self.get_object()
        return _fichier(rapport_csv(lot), f"rapport_anomalies_{lot.gabarit}_{lot.cree_le:%Y%m%d_%H%M}.csv",
                        "text/csv; charset=utf-8")


class RapprochementView(APIView):
    """C1-C10 (plan ETSL-ERP-MIG §6.3) ; valeurs source en `?source_c1=…` ; `?export=csv` pour le PV de migration."""

    permission_classes = [CanRepriseCompta]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        resultats = rapprochements(request.query_params)
        if request.query_params.get("export") == "csv":
            return _fichier(rapprochements_csv(resultats), f"rapprochements_migration_{timezone.localdate():%Y%m%d}.csv",
                            "text/csv; charset=utf-8")
        return Response({"controles": resultats, "lots": synthese_lots()})


class ParametreRepriseSerializer(serializers.ModelSerializer):
    est_provisoire = serializers.BooleanField(read_only=True)

    class Meta:
        model = ParametreReprise
        fields = ["id", "code", "label", "valeur", "unite", "statut_valeur", "est_provisoire", "confirme_par", "confirme_le"]
        read_only_fields = ["code", "label", "unite", "statut_valeur", "confirme_par", "confirme_le"]

    def validate_valeur(self, value):
        if value < 0:
            raise serializers.ValidationError("La valeur ne peut être négative.")
        if self.instance and self.instance.code == "TAUX_ERREUR_MAX" and value > 100:
            raise serializers.ValidationError("Un taux est compris entre 0 et 100 %.")
        return value

    def update(self, instance, validated_data):
        if "valeur" in validated_data and validated_data["valeur"] != instance.valeur:
            instance.statut_valeur = ParametreReprise.StatutValeur.PROVISOIRE  # modifiée ⇒ à reconfirmer
            instance.confirme_par = None
            instance.confirme_le = None
        return super().update(instance, validated_data)


class ParametreRepriseViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                              viewsets.GenericViewSet):
    """Paramètres provisoires de la reprise : modifiables par le cercle comptable, confirmés par la direction / finance."""

    permission_classes = [CanRepriseCompta]
    serializer_class = ParametreRepriseSerializer
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_queryset(self):
        assurer_parametres()
        return ParametreReprise.objects.all()

    @extend_schema(request=None, responses={200: ParametreRepriseSerializer})
    @action(detail=True, methods=["post"])
    def confirmer(self, request, pk=None):
        u = request.user
        if not (u.is_staff or u.role in CONFIRMATION_ROLES):
            return Response({"detail": "Confirmation réservée à la direction et à la finance."},
                            status=status.HTTP_403_FORBIDDEN)
        p = self.get_object()
        p.statut_valeur = ParametreReprise.StatutValeur.CONFIRME
        p.confirme_par = u
        p.confirme_le = timezone.now()
        p.save(update_fields=["statut_valeur", "confirme_par", "confirme_le"])
        return Response(self.get_serializer(p).data)


class CanPaieHistorique(BasePermission):
    def has_permission(self, request, view):
        from rh_paie.services import can_manage_paie

        return bool(request.user and request.user.is_authenticated and can_manage_paie(request.user))


class HistoriquePaieSerializer(serializers.ModelSerializer):
    matricule = serializers.CharField(source="employe.code", read_only=True)
    salarie = serializers.CharField(source="employe.nom_complet", read_only=True)
    nature_label = serializers.CharField(source="get_nature_display", read_only=True)

    class Meta:
        model = HistoriquePaie
        fields = ["id", "matricule", "salarie", "periode", "rubrique", "libelle", "nature", "nature_label", "base",
                  "montant", "lot", "importe_le"]
        read_only_fields = fields


class HistoriquePaieViewSet(viewsets.ReadOnlyModelViewSet):
    """Historique de paie repris (12 mois) : consultation seule, cercle paie (RF-33)."""

    permission_classes = [CanPaieHistorique]
    serializer_class = HistoriquePaieSerializer

    def get_queryset(self):
        qs = HistoriquePaie.objects.select_related("employe")
        if self.request.query_params.get("matricule"):
            qs = qs.filter(employe__code=self.request.query_params["matricule"])
        periode = self.request.query_params.get("periode", "")
        if len(periode) >= 7 and periode[:4].isdigit() and periode[5:7].isdigit():
            qs = qs.filter(periode__year=int(periode[:4]), periode__month=int(periode[5:7]))
        return qs
