"""API des écarts M7 (lot ecarts-m6m7) : listes paramétrables, check-lists d'audit, plans de prévention,
prestataires déchets agréés, fiches sécurité terrain."""

from django.db import transaction
from django.utils import timezone
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from config.inputs import fk_input

from .models import (
    AuditHse,
    ConstatAudit,
    EvaluationRisque,
    FicheSecurite,
    ListeHse,
    ModeleChecklistHse,
    PlanPrevention,
    PrestataireDechet,
    ReponseChecklistHse,
)
from .serializers import _apply_and_validate
from .services import CanManageHse, CanValidateHse, can_validate_hse


# --------------------------------------------------------------------------------------------------------------
# Sérialiseurs
# --------------------------------------------------------------------------------------------------------------
class ListeHseSerializer(serializers.ModelSerializer):
    categorie_label = serializers.CharField(source="get_categorie_display", read_only=True)
    est_provisoire = serializers.BooleanField(read_only=True)

    class Meta:
        model = ListeHse
        fields = [
            "id", "categorie", "categorie_label", "code", "libelle", "actif", "gaz_obligatoire", "dangereux", "ordre",
            "statut_valeur", "est_provisoire", "confirme_par", "confirme_le",
        ]
        read_only_fields = ["statut_valeur", "confirme_par", "confirme_le"]

    def validate(self, attrs):
        if self.instance and ("code" in attrs and attrs["code"] != self.instance.code
                              or "categorie" in attrs and attrs["categorie"] != self.instance.categorie):
            raise serializers.ValidationError({"code": "Code et catégorie figés : désactiver puis créer une nouvelle valeur."})
        categorie = attrs.get("categorie") or (self.instance.categorie if self.instance else None)
        code = attrs.get("code") or (self.instance.code if self.instance else None)
        if not self.instance and ListeHse.objects.filter(categorie=categorie, code=code).exists():
            raise serializers.ValidationError({"code": "Ce code existe déjà dans la catégorie."})
        return _apply_and_validate(self, attrs, exclude=())


class ModeleChecklistHseSerializer(serializers.ModelSerializer):
    est_provisoire = serializers.BooleanField(read_only=True)
    questions_texte = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = ModeleChecklistHse
        fields = [
            "id", "code", "intitule", "type_audit", "referentiel", "questions", "questions_texte", "actif",
            "statut_valeur", "est_provisoire", "confirme_par", "confirme_le", "created_at",
        ]
        read_only_fields = ["code", "statut_valeur", "confirme_par", "confirme_le"]

    def validate_questions(self, value):
        if not isinstance(value, list) or not all(isinstance(q, str) and q.strip() for q in value):
            raise serializers.ValidationError("Liste de questions (textes) attendue.")
        return [q.strip() for q in value]

    def validate(self, attrs):
        texte = attrs.pop("questions_texte", None)
        if texte is not None:
            attrs["questions"] = [q.strip() for q in texte.splitlines() if q.strip()]
        questions = attrs.get("questions", self.instance.questions if self.instance else [])
        if not questions:
            raise serializers.ValidationError({"questions": "Au moins une question (une par ligne)."})
        return attrs

    def update(self, instance, validated_data):
        # Une trame modifiée redevient provisoire jusqu'à sa confirmation.
        validated_data.update(statut_valeur=ModeleChecklistHse.StatutValeur.PROVISOIRE, confirme_par=None, confirme_le=None)
        return super().update(instance, validated_data)


class ReponseChecklistHseSerializer(serializers.ModelSerializer):
    reponse_label = serializers.CharField(source="get_reponse_display", read_only=True)
    constat_gravite = serializers.CharField(source="constat.gravite", read_only=True, default=None)

    class Meta:
        model = ReponseChecklistHse
        fields = [
            "id", "audit", "ordre", "question", "reponse", "reponse_label", "commentaire", "constat",
            "constat_gravite", "repondu_par", "repondu_le",
        ]
        read_only_fields = fields


class PlanPreventionSerializer(serializers.ModelSerializer):
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    affaire_code = serializers.CharField(source="affaire.code", read_only=True, default=None)
    risques_detail = serializers.SerializerMethodField()
    en_vigueur = serializers.SerializerMethodField()
    valide_par_nom = serializers.CharField(source="valide_par.get_full_name", read_only=True, default=None)

    class Meta:
        model = PlanPrevention
        fields = [
            "id", "code", "affaire", "affaire_code", "entreprise_exterieure", "site", "site_gr",
            "date_inspection_commune", "date_debut", "date_fin", "risques_detail", "mesures", "consignes_urgence",
            "statut", "statut_label", "en_vigueur", "valide_par", "valide_par_nom", "valide_le", "created_by",
            "created_at",
        ]
        read_only_fields = ["code", "statut", "valide_par", "valide_le", "created_by"]

    def get_risques_detail(self, obj):
        return [
            {"id": str(r.pk), "code": r.code, "description": r.description, "score": r.score, "criticite": r.criticite,
             "mesure": r.mesure}
            for r in obj.risques.all()
        ]

    def get_en_vigueur(self, obj):
        return obj.en_vigueur()

    def validate(self, attrs):
        if self.instance and self.instance.statut != PlanPrevention.Statut.BROUILLON:
            raise serializers.ValidationError({"detail": "Plan de prévention validé : scellé (créer un nouveau plan)."})
        return _apply_and_validate(self, attrs)


class PrestataireDechetSerializer(serializers.ModelSerializer):
    valide = serializers.SerializerMethodField()
    partenaire_nom = serializers.CharField(source="partenaire.name", read_only=True, default=None)

    class Meta:
        model = PrestataireDechet
        fields = [
            "id", "nom", "partenaire", "partenaire_nom", "numero_agrement", "autorite", "types_dechets",
            "date_fin_validite", "actif", "valide", "notes", "created_at",
        ]

    def get_valide(self, obj):
        return obj.est_valide()

    def validate_types_dechets(self, value):
        from .ecarts_m6m7 import codes_actifs

        codes = [c.strip() for c in (value or "").split(",") if c.strip()]
        inconnus = sorted(set(codes) - codes_actifs("type_dechet"))
        if inconnus:
            raise serializers.ValidationError(f"Type(s) de déchet inconnu(s) : {', '.join(inconnus)}.")
        return ",".join(codes)


class FicheSecuriteSerializer(serializers.ModelSerializer):
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)

    class Meta:
        model = FicheSecurite
        fields = [
            "id", "code", "titre", "categorie", "risques", "consignes", "epi", "urgence", "version", "provisoire",
            "statut", "statut_label", "publiee_par", "publiee_le", "updated_at",
        ]
        read_only_fields = ["code", "version", "provisoire", "statut", "publiee_par", "publiee_le"]

    def update(self, instance, validated_data):
        # Toute modification d'une fiche crée une nouvelle version, à republier ; le contenu n'est plus provisoire.
        validated_data.update(version=instance.version + 1, statut=FicheSecurite.Statut.BROUILLON, provisoire=False)
        return super().update(instance, validated_data)


# --------------------------------------------------------------------------------------------------------------
# Vues
# --------------------------------------------------------------------------------------------------------------
def _confirmer(request, obj):
    if not can_validate_hse(request.user):
        return None
    obj.statut_valeur = "confirme"
    obj.confirme_par = request.user
    obj.confirme_le = timezone.now()
    obj.save(update_fields=["statut_valeur", "confirme_par", "confirme_le"])
    return obj


class _SansSuppression(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                       mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Référentiels : désactivation plutôt que suppression (traçabilité)."""

    http_method_names = ["get", "post", "patch", "head", "options"]


class ListeHseViewSet(_SansSuppression):
    """Types de permis / d'incidents / de déchets et rôles du partage GR (provisoires, confirmables)."""

    queryset = ListeHse.objects.all()
    serializer_class = ListeHseSerializer
    permission_classes = [CanValidateHse]

    def get_queryset(self):
        from .ecarts_m6m7 import assurer_listes

        assurer_listes()
        qs = super().get_queryset()
        params = self.request.query_params
        if categorie := params.get("categorie"):
            qs = qs.filter(categorie=categorie)
        if params.get("actifs") == "1":
            qs = qs.filter(actif=True)
        return qs

    def get_permissions(self):
        # Lecture des listes : tout lecteur HSE (formulaires de saisie) ; écriture : HSE + hiérarchie.
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [CanManageHse()]
        return super().get_permissions()

    @action(detail=True, methods=["post"], url_path="confirmer")
    def confirmer(self, request, pk=None):
        obj = _confirmer(request, self.get_object())
        if obj is None:
            return Response({"detail": "Confirmation réservée au HSE et à la hiérarchie."}, status=status.HTTP_403_FORBIDDEN)
        return Response(self.get_serializer(obj).data)


class ModeleChecklistHseViewSet(_SansSuppression):
    queryset = ModeleChecklistHse.objects.all()
    serializer_class = ModeleChecklistHseSerializer
    permission_classes = [CanManageHse]

    def get_queryset(self):
        from .ecarts_m6m7 import assurer_modele_defaut

        assurer_modele_defaut()
        qs = super().get_queryset()
        if self.request.query_params.get("actifs") == "1":
            qs = qs.filter(actif=True)
        return qs

    @action(detail=True, methods=["post"], url_path="confirmer")
    def confirmer(self, request, pk=None):
        obj = _confirmer(request, self.get_object())
        if obj is None:
            return Response({"detail": "Confirmation réservée au HSE et à la hiérarchie."}, status=status.HTTP_403_FORBIDDEN)
        return Response(self.get_serializer(obj).data)


class ReponseChecklistHseViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = ReponseChecklistHse.objects.select_related("audit", "constat").all()
    serializer_class = ReponseChecklistHseSerializer
    permission_classes = [CanManageHse]

    def get_queryset(self):
        qs = super().get_queryset()
        if audit := self.request.query_params.get("audit"):
            import uuid

            try:
                qs = qs.filter(audit_id=uuid.UUID(str(audit)))
            except ValueError:
                qs = qs.none()
        return qs

    @action(detail=True, methods=["post"], url_path="repondre")
    @transaction.atomic
    def repondre(self, request, pk=None):
        """Répond à un point de la check-list ; « non conforme » ouvre (ou met à jour) un constat d'audit."""
        rep = ReponseChecklistHse.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        audit = rep.audit
        if audit.statut == AuditHse.Statut.CLOTURE:
            return Response({"detail": "Audit clôturé : check-list scellée."}, status=status.HTTP_400_BAD_REQUEST)
        reponse = request.data.get("reponse")
        if reponse not in ReponseChecklistHse.Reponse.values or reponse == ReponseChecklistHse.Reponse.EN_ATTENTE:
            return Response({"reponse": "Réponse attendue : conforme, non_conforme ou sans_objet."}, status=status.HTTP_400_BAD_REQUEST)
        gravite = request.data.get("gravite") or ConstatAudit.Gravite.MINEUR
        if reponse == ReponseChecklistHse.Reponse.NON_CONFORME and gravite not in (
            ConstatAudit.Gravite.MINEUR, ConstatAudit.Gravite.MAJEUR, ConstatAudit.Gravite.CRITIQUE,
        ):
            return Response({"gravite": "Gravité attendue : mineur, majeur ou critique."}, status=status.HTTP_400_BAD_REQUEST)
        rep.reponse = reponse
        rep.commentaire = str(request.data.get("commentaire", rep.commentaire) or "")[:2000]
        rep.repondu_par, rep.repondu_le = request.user, timezone.now()
        description = f"{rep.question}" + (f" — {rep.commentaire}" if rep.commentaire else "")
        if reponse == ReponseChecklistHse.Reponse.NON_CONFORME:
            if rep.constat_id:
                ConstatAudit.objects.filter(pk=rep.constat_id).update(description=description, gravite=gravite)
            else:
                rep.constat = ConstatAudit.objects.create(audit=audit, description=description, gravite=gravite)
        elif rep.constat_id and rep.constat.action_id is None:
            # Point réévalué conforme : le constat sans action est retiré.
            ConstatAudit.objects.filter(pk=rep.constat_id).delete()
            rep.constat = None
        rep.save()
        return Response(self.get_serializer(rep).data)


class PlanPreventionViewSet(viewsets.ModelViewSet):
    queryset = PlanPrevention.objects.select_related("affaire", "valide_par").prefetch_related("risques").all()
    serializer_class = PlanPreventionSerializer
    search_fields = ("code", "entreprise_exterieure", "site")
    permission_classes = [CanManageHse]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        if params.get("site_gr") == "1":
            qs = qs.filter(site_gr=True)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def _verrou(self):
        return PlanPrevention.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)

    @action(detail=True, methods=["post"], url_path="ajouter-risque")
    @transaction.atomic
    def ajouter_risque(self, request, pk=None):
        pdp = self._verrou()
        if pdp.statut != PlanPrevention.Statut.BROUILLON:
            return Response({"detail": "Plan validé : scellé."}, status=status.HTTP_400_BAD_REQUEST)
        risque = fk_input(request.data.get("risque"), EvaluationRisque.objects.all(), "risque")
        if risque is None:
            return Response({"risque": "Risque requis."}, status=status.HTTP_400_BAD_REQUEST)
        pdp.risques.add(risque)
        return Response(self.get_serializer(pdp).data)

    @action(detail=True, methods=["post"], url_path="valider")
    @transaction.atomic
    def valider(self, request, pk=None):
        """Validation HSE : inspection commune faite, au moins un risque, mesures pour les risques élevés."""
        if not can_validate_hse(request.user):
            return Response({"detail": "Validation réservée au HSE et à la hiérarchie."}, status=status.HTTP_403_FORBIDDEN)
        pdp = self._verrou()
        if pdp.statut != PlanPrevention.Statut.BROUILLON:
            return Response({"detail": "Plan déjà validé ou clos."}, status=status.HTTP_400_BAD_REQUEST)
        if not pdp.date_inspection_commune:
            return Response({"detail": "Inspection commune préalable non renseignée."}, status=status.HTTP_400_BAD_REQUEST)
        risques = list(pdp.risques.all())
        if not risques:
            return Response({"detail": "Aucun risque d'interférence analysé : validation impossible."}, status=status.HTTP_400_BAD_REQUEST)
        sans_mesure = [
            r.code for r in risques
            if r.criticite in (EvaluationRisque.Criticite.ELEVEE, EvaluationRisque.Criticite.CRITIQUE) and not r.mesure.strip()
        ]
        if sans_mesure or not pdp.mesures.strip():
            detail = (f"Risque(s) élevé(s) sans mesure : {', '.join(sans_mesure)}." if sans_mesure
                      else "Mesures de prévention du plan requises.")
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)
        pdp.statut = PlanPrevention.Statut.VALIDE
        pdp.valide_par, pdp.valide_le = request.user, timezone.now()
        pdp.save()
        if pdp.site_gr:
            from .ecarts_m6m7 import partager_site_gr

            partager_site_gr(
                f"Site GLOBAL RENTAL : plan de prévention {pdp.code} validé",
                f"Plan de prévention {pdp.code} ({pdp.entreprise_exterieure}, {pdp.site}) validé le "
                f"{timezone.localdate():%d/%m/%Y}.",
                exclure=request.user,
            )
        return Response(self.get_serializer(pdp).data)

    @action(detail=True, methods=["post"], url_path="cloturer")
    @transaction.atomic
    def cloturer(self, request, pk=None):
        pdp = self._verrou()
        if pdp.statut != PlanPrevention.Statut.VALIDE:
            return Response({"detail": "Seul un plan validé se clôt."}, status=status.HTTP_400_BAD_REQUEST)
        pdp.statut = PlanPrevention.Statut.CLOS
        pdp.save(update_fields=["statut", "updated_at"])
        return Response(self.get_serializer(pdp).data)


class PrestataireDechetViewSet(_SansSuppression):
    queryset = PrestataireDechet.objects.select_related("partenaire").all()
    serializer_class = PrestataireDechetSerializer
    search_fields = ("nom", "numero_agrement")
    permission_classes = [CanManageHse]

    def get_permissions(self):
        # L'agrément d'un prestataire est une décision HSE : écriture réservée au HSE et à la hiérarchie.
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return super().get_permissions()
        return [CanValidateHse()]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("valides") == "1":
            qs = qs.filter(actif=True, date_fin_validite__gte=timezone.localdate())
        return qs


class FicheSecuriteViewSet(_SansSuppression):
    """Fiches sécurité (CDC M7-08) : publiées = consultables sur /terrain, y compris hors ligne."""

    queryset = FicheSecurite.objects.all()
    serializer_class = FicheSecuriteSerializer
    search_fields = ("code", "titre", "categorie")
    permission_classes = [CanManageHse]

    def get_queryset(self):
        from .ecarts_m6m7 import assurer_fiches_defaut

        assurer_fiches_defaut()
        qs = super().get_queryset()
        if self.request.query_params.get("publiees") == "1":
            qs = qs.filter(statut=FicheSecurite.Statut.PUBLIEE)
        return qs

    def _transition(self, statut):
        fiche = FicheSecurite.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if fiche.statut == statut:
            return Response({"detail": "Fiche déjà dans cet état."}, status=status.HTTP_400_BAD_REQUEST)
        fiche.statut = statut
        if statut == FicheSecurite.Statut.PUBLIEE:
            fiche.publiee_par, fiche.publiee_le = self.request.user, timezone.now()
        fiche.save()
        return Response(self.get_serializer(fiche).data)

    @action(detail=True, methods=["post"], url_path="publier")
    @transaction.atomic
    def publier(self, request, pk=None):
        return self._transition(FicheSecurite.Statut.PUBLIEE)

    @action(detail=True, methods=["post"], url_path="retirer")
    @transaction.atomic
    def retirer(self, request, pk=None):
        return self._transition(FicheSecurite.Statut.RETIREE)
