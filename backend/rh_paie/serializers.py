"""Sérialiseurs M9 — RH & Paie."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import (
    BulletinLigne,
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
from .services import can_see_amount


def _apply_and_validate(serializer, attrs, exclude=("code",)):
    # Les champs M2M (ex. Formation.participants) ne se passent pas au constructeur
    # ni par setattr direct : un input formulaire/multipart le fournit comme [] même
    # absent (DRF ManyRelatedField.get_value sur QueryDict) -> TypeError 500 sinon.
    m2m = {f.name for f in serializer.Meta.model._meta.many_to_many}
    init = {key: value for key, value in attrs.items() if key not in m2m}
    instance = serializer.instance or serializer.Meta.model(**init)
    if serializer.instance:
        for key, value in init.items():
            setattr(instance, key, value)
    try:
        instance.full_clean(exclude=list(exclude))
    except DjangoValidationError as exc:
        if hasattr(exc, "error_dict"):
            raise serializers.ValidationError(exc.message_dict)
        raise serializers.ValidationError({"detail": exc.messages})
    return attrs


class ContratActifSerializer(serializers.Serializer):
    code = serializers.CharField(read_only=True)
    type = serializers.CharField(read_only=True)
    type_label = serializers.CharField(read_only=True)
    date_debut = serializers.DateField(read_only=True)
    date_fin = serializers.DateField(read_only=True, allow_null=True)
    a_renouveler = serializers.BooleanField(read_only=True)


class EmployeSerializer(serializers.ModelSerializer):
    nom_complet = serializers.CharField(read_only=True)
    contrat_actif = ContratActifSerializer(read_only=True)
    solde_conges = serializers.DecimalField(max_digits=8, decimal_places=1, read_only=True)

    class Meta:
        model = Employe
        fields = [
            "id", "code", "civilite", "nom", "prenom", "nom_complet",
            "date_naissance", "lieu_naissance", "nationalite", "numero_securite_sociale",
            "telephone", "email", "adresse", "categorie", "fonction", "departement",
            "site", "statut", "matricule_cnps", "date_embauche", "date_sortie",
            "contrat_actif", "solde_conges", "created_at", "updated_at",
        ]
        read_only_fields = ["code", "nom_complet"]

    def validate(self, attrs):
        return _apply_and_validate(self, attrs)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if not can_see_amount(getattr(request, "user", None)):
            data["contrat_actif"] = None
        return data


class ContratSerializer(serializers.ModelSerializer):
    employe_nom = serializers.CharField(source="employe.nom_complet", read_only=True)
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    expire_dans = serializers.IntegerField(read_only=True)
    a_renouveler = serializers.BooleanField(read_only=True)

    class Meta:
        model = ContratTravail
        fields = [
            "id", "code", "employe", "employe_nom", "type", "type_label",
            "date_debut", "date_fin", "salaire_base", "regime_horaire",
            "lieu_affectation", "statut", "statut_label", "expire_dans",
            "a_renouveler", "notes", "created_at", "updated_at",
        ]
        read_only_fields = ["code", "expire_dans", "a_renouveler"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if not can_see_amount(getattr(request, "user", None)):
            data["salaire_base"] = None
        return data

    def validate(self, attrs):
        return _apply_and_validate(self, attrs)


class QualificationSerializer(serializers.ModelSerializer):
    employe_nom = serializers.CharField(source="employe.nom_complet", read_only=True)
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    expiree = serializers.BooleanField(read_only=True)
    a_renouveler = serializers.BooleanField(read_only=True)

    class Meta:
        model = Qualification
        fields = [
            "id", "code", "employe", "employe_nom", "type", "type_label",
            "intitule", "organisme", "date_obtention", "date_validite",
            "expiree", "a_renouveler", "notes",
        ]
        read_only_fields = ["code", "expiree", "a_renouveler"]

    def validate(self, attrs):
        return _apply_and_validate(self, attrs)


class RecrutementSerializer(serializers.ModelSerializer):
    responsable_name = serializers.CharField(
        source="responsable.get_full_name", read_only=True, default=None
    )
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)

    class Meta:
        model = DemandeRecrutement
        fields = [
            "id", "code", "poste", "type", "type_label", "justification",
            "responsable", "responsable_name", "date_souhaitee", "statut",
            "statut_label", "created_at", "updated_at",
        ]
        read_only_fields = ["code"]

    def validate(self, attrs):
        return _apply_and_validate(self, attrs)


class FormationSerializer(serializers.ModelSerializer):
    participants_detail = EmployeSerializer(many=True, read_only=True)
    participants = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Employe.objects.all(), required=False
    )
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    nb_participants = serializers.SerializerMethodField()

    class Meta:
        model = Formation
        fields = [
            "id", "code", "theme", "organisme", "formateur", "date_session",
            "duree_heures", "participants", "participants_detail", "nb_participants",
            "type", "type_label", "evaluation", "created_at", "updated_at",
        ]
        read_only_fields = ["code"]

    def get_nb_participants(self, obj):
        return obj.participants.count()

    def validate(self, attrs):
        return _apply_and_validate(self, attrs)


class DemandeCongeSerializer(serializers.ModelSerializer):
    employe_nom = serializers.CharField(source="employe.nom_complet", read_only=True)
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)

    class Meta:
        model = DemandesConge
        fields = [
            "id", "code", "employe", "employe_nom", "type", "type_label",
            "date_debut", "date_fin", "nb_jours", "motif", "statut",
            "statut_label", "created_at", "updated_at",
        ]
        read_only_fields = ["code"]

    def validate(self, attrs):
        return _apply_and_validate(self, attrs)


class SanctionSerializer(serializers.ModelSerializer):
    employe_nom = serializers.CharField(source="employe.nom_complet", read_only=True)
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)

    class Meta:
        model = Sanction
        fields = [
            "id", "code", "employe", "employe_nom", "type", "type_label",
            "faits", "rapport", "date_constat", "date_decision", "statut",
            "statut_label", "created_at", "updated_at",
        ]
        read_only_fields = ["code"]

    def validate(self, attrs):
        return _apply_and_validate(self, attrs)


class SaisieTempsSerializer(serializers.ModelSerializer):
    employe_nom = serializers.CharField(source="employe.nom_complet", read_only=True)
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)

    class Meta:
        model = SaisieTemps
        fields = [
            "id", "code", "employe", "employe_nom", "date", "heures", "type",
            "type_label", "source", "statut", "statut_label", "created_at", "updated_at",
        ]
        read_only_fields = ["code", "statut", "source"]

    def validate(self, attrs):
        return _apply_and_validate(self, attrs)


class RubriqueSerializer(serializers.ModelSerializer):
    nature_label = serializers.CharField(source="get_nature_display", read_only=True)

    class Meta:
        model = RubriquePaie
        fields = [
            "id", "code", "label", "nature", "nature_label", "base", "taux", "ordre",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        return _apply_and_validate(self, attrs)


class BulletinLigneSerializer(serializers.ModelSerializer):
    rubrique_code = serializers.CharField(source="rubrique.code", read_only=True)
    rubrique_label = serializers.CharField(source="rubrique.label", read_only=True)
    nature = serializers.CharField(source="rubrique.nature", read_only=True)

    class Meta:
        model = BulletinLigne
        fields = ["id", "bulletin", "rubrique", "rubrique_code", "rubrique_label", "nature", "libelle", "montant"]
        read_only_fields = ["bulletin"]


class BulletinSerializer(serializers.ModelSerializer):
    employe_nom = serializers.CharField(source="employe.nom_complet", read_only=True)
    matricule = serializers.CharField(source="employe.code", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    total_gains = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    total_retenues = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    lignes = BulletinLigneSerializer(many=True, read_only=True)
    has_amount_access = serializers.SerializerMethodField()

    class Meta:
        model = BulletinPaie
        fields = [
            "id", "code", "employe", "employe_nom", "matricule", "periode",
            "salaire_base", "brut", "net", "total_gains", "total_retenues",
            "lignes", "statut", "statut_label", "has_amount_access",
            "created_at", "updated_at",
        ]
        read_only_fields = ["code", "brut", "net", "total_gains", "total_retenues", "lignes"]

    def get_has_amount_access(self, obj):
        return can_see_amount(self.context["request"].user)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if not can_see_amount(getattr(request, "user", None)):
            for key in ("salaire_base", "brut", "net", "total_gains", "total_retenues", "lignes"):
                data[key] = None
            data["has_amount_access"] = False
        return data

    def validate(self, attrs):
        return _apply_and_validate(self, attrs)


class BulletinAvecLignesSerializer(BulletinSerializer):
    lignes = BulletinLigneSerializer(many=True, required=False)

    def validate(self, attrs):
        lignes = attrs.pop("lignes", [])
        _apply_and_validate(self, attrs)
        attrs["lignes"] = lignes
        return attrs

    def create(self, validated_data):
        ligne_data = validated_data.pop("lignes", [])
        bulletin = BulletinPaie.objects.create(**validated_data)
        for item in ligne_data:
            BulletinLigne.objects.create(bulletin=bulletin, **item)
        self.recalculer(bulletin)
        return bulletin

    @staticmethod
    def recalculer(bulletin):
        brut = bulletin.total_gains or 0
        net = bulletin.total_gains - (bulletin.total_retenues or 0)
        bulletin.brut = brut
        bulletin.net = net
        bulletin.save(update_fields=["brut", "net", "updated_at"])