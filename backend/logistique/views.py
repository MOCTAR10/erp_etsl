"""API module M4 — Logistique ETSL & GLOBAL RENTAL (RF-ERP-30…33)."""

from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from .models import (
    AffectationParc,
    DemandeMobilisation,
    EquipementParc,
    LectureCompteur,
    LocationGR,
    ParametreLogistique,
    TarifGR,
)
from .serializers import (
    AffectationParcSerializer,
    DemandeMobilisationSerializer,
    EquipementParcSerializer,
    LectureCompteurSerializer,
    LocationGRSerializer,
    ParametreLogistiqueSerializer,
    TarifGRSerializer,
)
from config.inputs import date_input
from users.permissions import can_read_module
from outbox.models import publish
from .services import (
    LOGISTIQUE_CONFIRM_ROLES,
    PARAMETRES_DEFAUT,
    CanManageLogistique,
    appliquer_tarif,
    calculer_penalite,
    can_see_amount,
    compteur_glissant,
    emettre_bc_gr,
    get_param_logistique,
    reporter_compteur,
    stats_parc,
)


class IsConfirmateurLogistique(BasePermission):
    """Confirmer une valeur provisoire : direction des opérations et au-dessus."""

    def has_permission(self, request, view):
        u = getattr(request, "user", None)
        return bool(u and u.is_authenticated and (u.is_staff or u.role in LOGISTIQUE_CONFIRM_ROLES))


class _CommonViewSet(viewsets.ModelViewSet):
    """Lecture authentifiée ; écriture réservée aux rôles Logistique."""

    http_method_names = ["get", "post", "patch", "delete"]

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [can_read_module("logistique")()]
        return [CanManageLogistique()]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["can_view_amount"] = can_see_amount(self.request.user)
        return context


class EquipementParcViewSet(_CommonViewSet):
    serializer_class = EquipementParcSerializer

    def get_queryset(self):
        qs = EquipementParc.objects.select_related("proprietaire")
        statut_ = self.request.query_params.get("statut")
        if statut_:
            qs = qs.filter(statut=statut_)
        gr = self.request.query_params.get("global_rental")
        if gr in ("true", "1"):
            qs = qs.filter(is_global_rental=True)
        elif gr in ("false", "0"):
            qs = qs.filter(is_global_rental=False)
        categorie = self.request.query_params.get("categorie")
        if categorie:
            qs = qs.filter(categorie=categorie)
        return qs

    @action(detail=False, methods=["post"], url_path="disponibilite")
    def set_disponible(self, request):
        """Remet un équipement du parc disponible (RF-ERP-30)."""
        equipement = EquipementParc.objects.filter(pk=request.data.get("id")).first()
        if not equipement:
            raise ValidationError({"id": "Équipement introuvable."})
        # Un équipement affecté ou en location GR se libère par la fin de l'affectation / la clôture de la location
        # (compteurs, refacturation 618) : pas par un simple bouton, sinon il serait réaffecté en double.
        if equipement.affectations.filter(statut=AffectationParc.Statut.ACTIVE).exists():
            raise ValidationError({"detail": "Affectation en cours : terminez-la pour libérer l'équipement."})
        if equipement.locations.filter(statut=LocationGR.Statut.ACTIVE).exists():
            raise ValidationError({"detail": "Location GLOBAL RENTAL active : clôturez-la pour libérer l'équipement."})
        equipement.statut = EquipementParc.Statut.DISPONIBLE
        equipement.save(update_fields=["statut", "updated_at"])
        return Response(self.get_serializer(equipement).data)


class DemandeMobilisationViewSet(_CommonViewSet):
    serializer_class = DemandeMobilisationSerializer

    def get_queryset(self):
        qs = DemandeMobilisation.objects.select_related("affaire", "ordre", "created_by")
        statut_ = self.request.query_params.get("statut")
        if statut_:
            qs = qs.filter(statut=statut_)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"], url_path="soumettre")
    def soumettre(self, request, pk=None):
        """Soumission d'un besoin opérationnel (RF-ERP-31)."""
        demande = self.get_object()
        if demande.statut != DemandeMobilisation.Statut.BROUILLON:
            raise ValidationError({"detail": f"Demande {demande.get_statut_display().lower()} : soumission impossible."})
        demande.statut = DemandeMobilisation.Statut.SOUMISE
        demande.save(update_fields=["statut", "updated_at"])
        return Response(self.get_serializer(demande).data)

    @action(detail=True, methods=["post"], url_path="traiter")
    def traiter(self, request, pk=None):
        """Marque le besoin traité (affectation réalisée)."""
        demande = self.get_object()
        if demande.statut != DemandeMobilisation.Statut.SOUMISE:
            raise ValidationError({"detail": f"Demande {demande.get_statut_display().lower()} : seule une demande soumise se traite."})
        demande.statut = DemandeMobilisation.Statut.TRAITEE
        demande.save(update_fields=["statut", "updated_at"])
        return Response(self.get_serializer(demande).data)


class AffectationParcViewSet(_CommonViewSet):
    serializer_class = AffectationParcSerializer

    def get_queryset(self):
        qs = AffectationParc.objects.select_related(
            "equipement", "demande", "affaire", "ordre", "responsable", "created_by"
        )
        statut_ = self.request.query_params.get("statut")
        if statut_:
            qs = qs.filter(statut=statut_)
        equipement = self.request.query_params.get("equipement")
        if equipement:
            qs = qs.filter(equipement_id=equipement)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        instance = self.get_object()
        if instance.statut == AffectationParc.Statut.TERMINEE:
            raise ValidationError("Affectation déjà terminée : modifiable via retour.")
        serializer.save()

    @action(detail=True, methods=["post"], url_path="terminer")
    def terminer(self, request, pk=None):
        """Fin d'affectation ; l'équipement redevient disponible (RF-ERP-31)."""
        affectation = self.get_object()
        affectation.statut = AffectationParc.Statut.TERMINEE
        affectation.date_fin = timezone.now().date()
        affectation.save(update_fields=["statut", "date_fin", "updated_at"])
        equipement = affectation.equipement
        if equipement.statut == EquipementParc.Statut.AFFECTE:
            equipement.statut = EquipementParc.Statut.DISPONIBLE
            equipement.save(update_fields=["statut", "updated_at"])
        return Response(self.get_serializer(affectation).data)


class LocationGRViewSet(_CommonViewSet):
    serializer_class = LocationGRSerializer

    def get_queryset(self):
        qs = LocationGR.objects.select_related(
            "partenaire", "equipement", "affaire", "devise", "created_by"
        )
        statut_ = self.request.query_params.get("statut")
        if statut_:
            qs = qs.filter(statut=statut_)
        gr = self.request.query_params.get("global_rental")
        if gr in ("true", "1"):
            qs = qs.filter(partenaire__is_global_rental=True)
        affaire = self.request.query_params.get("affaire")
        if affaire:
            qs = qs.filter(affaire_id=affaire)
        return qs

    def perform_create(self, serializer):
        appliquer_tarif(serializer.save(created_by=self.request.user))

    def perform_update(self, serializer):
        appliquer_tarif(serializer.save())

    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        """Parc, locations actives, compteurs (RF-ERP-30/32/33)."""
        return Response(stats_parc())

    @action(detail=True, methods=["post"], url_path="emettre")
    @transaction.atomic
    def emettre(self, request, pk=None):
        """Émission du BC / GR après validation automatique (équipement, tarif, 618, dates) — M4 clôture."""
        location = LocationGR.objects.select_for_update(of=("self",)).select_related("partenaire", "equipement").get(
            pk=self.get_object().pk
        )
        emettre_bc_gr(location, request.user)
        return Response(self.get_serializer(location).data)

    @action(detail=True, methods=["get"], url_path="glissant")
    def glissant(self, request, pk=None):
        """Formule glissante des compteurs : taux par jour sur la fenêtre paramétrée et projection."""
        jour = date_input(request.query_params.get("date"), "date", default=timezone.localdate())
        return Response(compteur_glissant(self.get_object(), aujourdhui=jour))

    @action(detail=True, methods=["post"], url_path="demarrer")
    @transaction.atomic
    def demarrer(self, request, pk=None):
        """Démarrage location GR : compteur initial + statut actif (RF-ERP-32)."""
        # Verrou : deux démarrages simultanés publieraient deux événements GR (webhook partenaire).
        location = LocationGR.objects.select_for_update().get(pk=self.get_object().pk)
        if location.statut != LocationGR.Statut.BROUILLON:
            raise ValidationError(
                "Seule une prestation en brouillon peut démarrer (déjà active, terminée ou annulée)."
            )
        lecture = request.data.get("lecture_initiale")
        if lecture in (None, ""):
            raise ValidationError({"lecture_initiale": "Compteur de départ requis."})
        try:
            lecture = Decimal(str(lecture))
        except InvalidOperation:
            raise ValidationError({"lecture_initiale": "Compteur numérique attendu."})
        if lecture < 0:
            raise ValidationError({"lecture_initiale": "Le compteur ne peut pas être négatif."})
        if location.date_debut is None:  # le démarrage fixe le début de la prestation
            location.date_debut = timezone.localdate()
            location.save(update_fields=["date_debut", "updated_at"])
        if not location.emis_le:
            emettre_bc_gr(location, request.user)  # validation automatique + BC / GR numérotés
        location.lecture_initiale = lecture
        location.statut = LocationGR.Statut.ACTIVE
        location.save(update_fields=["lecture_initiale", "statut", "updated_at"])
        publish(
            "gr.location.demarree",
            {
                "code": location.code, "equipement": location.equipement.code,
                "reference_bc": location.reference_bc, "reference_bl": location.reference_bl,
                "date_debut": str(location.date_debut) if location.date_debut else None,
                "lecture_initiale": str(lecture),
            },
        )
        equipement = location.equipement
        if equipement.statut != EquipementParc.Statut.EN_LOCATION:
            equipement.statut = EquipementParc.Statut.EN_LOCATION
            equipement.save(update_fields=["statut", "updated_at"])
        return Response(self.get_serializer(location).data)

    @action(detail=True, methods=["post"], url_path="cloturer")
    @transaction.atomic
    def cloturer(self, request, pk=None):
        """Clôture location GR : compteur final + consommation + statut (RF-ERP-32/33)."""
        location = LocationGR.objects.select_for_update().get(pk=self.get_object().pk)
        if location.statut != LocationGR.Statut.ACTIVE:
            raise ValidationError("Seule une location active peut être clôturée.")
        lecture = request.data.get("lecture_finale")
        if lecture in (None, ""):
            raise ValidationError({"lecture_finale": "Compteur de retour requis."})
        try:
            lecture = Decimal(str(lecture))
        except InvalidOperation:
            raise ValidationError({"lecture_finale": "Compteur numérique attendu."})
        location.lecture_finale = lecture
        if location.consommation is not None and location.consommation < 0:
            raise ValidationError("Compteur de retour inférieur au compteur de départ.")
        date_retour = date_input(request.data.get("date_retour"), "date_retour", default=timezone.localdate())
        if location.date_debut and date_retour < location.date_debut:
            raise ValidationError({"date_retour": "Le retour ne peut précéder le début de la location."})
        calculer_penalite(location, date_retour)
        location.statut = LocationGR.Statut.TERMINEE
        location.save(update_fields=["lecture_finale", "date_retour", "jours_retard", "penalite", "statut", "updated_at"])
        reporter_compteur(location.equipement, lecture)
        publish(
            "gr.location.cloturee",
            {
                "code": location.code, "equipement": location.equipement.code,
                "reference_retour": location.reference_retour,
                "lecture_finale": str(location.lecture_finale),
                "consommation": str(location.consommation) if location.consommation is not None else None,
                "date_retour": str(location.date_retour), "jours_retard": location.jours_retard,
                "penalite": str(location.penalite),
            },
        )
        equipement = location.equipement
        if equipement.statut == EquipementParc.Statut.EN_LOCATION:
            equipement.statut = EquipementParc.Statut.DISPONIBLE
            equipement.save(update_fields=["statut", "updated_at"])
        return Response(self.get_serializer(location).data)


class LectureCompteurViewSet(_CommonViewSet):
    serializer_class = LectureCompteurSerializer

    def get_queryset(self):
        qs = LectureCompteur.objects.select_related(
            "location", "location__equipement", "releve_par"
        )
        location = self.request.query_params.get("location")
        if location:
            qs = qs.filter(location_id=location)
        equipement = self.request.query_params.get("equipement")
        if equipement:
            qs = qs.filter(location__equipement_id=equipement)
        if self.request.query_params.get("from"):
            qs = qs.filter(date__gte=self.request.query_params["from"])
        if self.request.query_params.get("to"):
            qs = qs.filter(date__lte=self.request.query_params["to"])
        return qs

    @transaction.atomic
    def perform_create(self, serializer):
        lecture = serializer.save(releve_par=self.request.user)
        reporter_compteur(lecture.location.equipement, lecture.valeur)


class TarifGRViewSet(_CommonViewSet):
    """Grille GR versionnée : création et suppression (si inutilisée) — jamais de modification (lot 14)."""

    serializer_class = TarifGRSerializer
    http_method_names = ["get", "post", "delete"]

    def get_queryset(self):
        qs = TarifGR.objects.select_related("partenaire", "equipement", "created_by")
        params = self.request.query_params
        if partenaire := params.get("partenaire"):
            qs = qs.filter(partenaire_id=partenaire)
        if categorie := params.get("categorie"):
            qs = qs.filter(categorie=categorie)
        if equipement := params.get("equipement"):
            qs = qs.filter(equipement_id=equipement)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

class ParametreLogistiqueViewSet(viewsets.ModelViewSet):
    """Paramètres M4 modifiables par ETSL ; création/suppression interdites (définis par le code)."""

    queryset = ParametreLogistique.objects.all()
    serializer_class = ParametreLogistiqueSerializer
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_queryset(self):
        for code in PARAMETRES_DEFAUT:
            get_param_logistique(code)
        return super().get_queryset()

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [can_read_module("logistique")()]
        if getattr(self, "action", None) == "confirmer":
            return [IsConfirmateurLogistique()]
        return [CanManageLogistique()]

    def create(self, request, *args, **kwargs):
        return Response({"detail": "Les paramètres sont prédéfinis : modifiez leur valeur."}, status=405)

    @action(detail=True, methods=["post"], url_path="confirmer")
    def confirmer(self, request, pk=None):
        p = self.get_object()
        p.statut_valeur = ParametreLogistique.StatutValeur.CONFIRME
        p.confirme_par = request.user
        p.confirme_le = timezone.now()
        p.save(update_fields=["statut_valeur", "confirme_par", "confirme_le"])
        return Response(self.get_serializer(p).data)
