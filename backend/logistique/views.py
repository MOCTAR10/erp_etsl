"""API module M4 — Logistique ETSL & GLOBAL RENTAL (RF-ERP-30…33)."""

from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.utils import timezone
from config.filtres_vues import FiltresMulticriteresMixin
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from .models import (
    AffectationParc,
    ArchiveCompteurGR,
    AuditEquipement,
    HistoriqueEquipement,
    LigneLocationGR,
    ReceptionBLGR,
    ReleveCompteurParc,
    DemandeMobilisation,
    EquipementParc,
    LectureCompteur,
    LocationGR,
    ParametreLogistique,
    TarifGR,
)
from .serializers import (
    AffectationParcSerializer,
    ArchiveCompteurGRSerializer,
    AuditEquipementSerializer,
    HistoriqueEquipementSerializer,
    LigneLocationGRSerializer,
    ReceptionBLGRSerializer,
    ReleveCompteurParcSerializer,
    DemandeMobilisationSerializer,
    EquipementParcSerializer,
    LectureCompteurSerializer,
    LocationGRSerializer,
    ParametreLogistiqueSerializer,
    TarifGRSerializer,
)
from config.inputs import date_input, fk_input, positive_decimal
from users.permissions import can_read_module
from outbox.models import publish
from .services import (
    LOGISTIQUE_CONFIRM_ROLES,
    PARAMETRES_DEFAUT,
    CanManageLogistique,
    appliquer_tarif,
    archiver_compteurs,
    calculer_penalite,
    conservation_jusqu_au,
    donnees_618,
    enregistrer_releve_parc,
    escalader_m12,
    flux_operations,
    historiser_equipement,
    lier_bc_achat,
    proposer_demandes,
    rapprocher_facture,
    receptionner_bl,
    reporting_parc,
    valider_commande,
    can_see_amount,
    compteur_glissant,
    emettre_bc_gr,
    get_param_logistique,
    reporter_compteur,
    stats_parc,
)
from config.i18n import tr


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


class EquipementParcViewSet(FiltresMulticriteresMixin, _CommonViewSet):
    # EX-G-03 : filtre par site (`?site_etsl=<id>`, GET filtres/) et restriction de lecture par site (paramètre).
    champs_filtrables = ("site_etsl",)
    champ_site = "site_etsl"
    serializer_class = EquipementParcSerializer
    search_fields = ("code", "label", "registration", "site",)

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

    @transaction.atomic
    def perform_update(self, serializer):
        avant = EquipementParc.objects.select_for_update().get(pk=serializer.instance.pk)
        historiser_equipement(avant, serializer.save(), self.request.user)

    @action(detail=True, methods=["post"], url_path="plafond")
    @transaction.atomic
    def plafond(self, request, pk=None):
        """Fixe le plafond du compteur (km / heures maximal) ; modification historisée."""
        equipement = EquipementParc.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        avant = EquipementParc.objects.get(pk=equipement.pk)
        valeur = positive_decimal(request.data.get("plafond_compteur"), "plafond_compteur")
        if valeur <= 0:
            raise ValidationError({"plafond_compteur": "Le plafond doit être strictement positif."})
        equipement.plafond_compteur = valeur
        equipement.save(update_fields=["plafond_compteur", "updated_at"])
        historiser_equipement(avant, equipement, request.user)
        return Response(self.get_serializer(equipement).data)

    @action(detail=False, methods=["get"], url_path="reporting")
    def reporting(self, request):
        """Rentabilité, utilisation et économies du parc sur un mois (formules provisoires)."""
        periode = request.query_params.get("periode") or timezone.localdate().strftime("%Y-%m")
        data = reporting_parc(periode)
        if not can_see_amount(request.user):
            data["economies"] = data["cout_gr"] = None
            for row in data["rows"]:
                row["economie"] = None
        return Response(data)

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
        avant = EquipementParc.objects.get(pk=equipement.pk)
        equipement.statut = EquipementParc.Statut.DISPONIBLE
        equipement.save(update_fields=["statut", "updated_at"])
        historiser_equipement(avant, equipement, request.user)
        return Response(self.get_serializer(equipement).data)


class DemandeMobilisationViewSet(_CommonViewSet):
    serializer_class = DemandeMobilisationSerializer
    search_fields = ("code", "label",)

    def get_queryset(self):
        qs = DemandeMobilisation.objects.select_related("affaire", "ordre", "created_by")
        statut_ = self.request.query_params.get("statut")
        if statut_:
            qs = qs.filter(statut=statut_)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=["post"], url_path="proposer")
    @transaction.atomic
    def proposer(self, request):
        """Plan de charge M3 → demandes de mobilisation proposées (brouillon), sans doublon."""
        creees = proposer_demandes(request.user)
        return Response({"creees": len(creees), "codes": [d.code for d in creees]})

    @action(detail=True, methods=["post"], url_path="soumettre")
    def soumettre(self, request, pk=None):
        """Soumission d'un besoin opérationnel (RF-ERP-31)."""
        demande = self.get_object()
        if demande.statut != DemandeMobilisation.Statut.BROUILLON:
            raise ValidationError({"detail": tr("Demande %(statut)s : soumission impossible.") % {"statut": demande.get_statut_display().lower()}})
        demande.statut = DemandeMobilisation.Statut.SOUMISE
        demande.save(update_fields=["statut", "updated_at"])
        return Response(self.get_serializer(demande).data)

    @action(detail=True, methods=["post"], url_path="traiter")
    def traiter(self, request, pk=None):
        """Marque le besoin traité (affectation réalisée)."""
        demande = self.get_object()
        if demande.statut != DemandeMobilisation.Statut.SOUMISE:
            raise ValidationError({"detail": tr("Demande %(statut)s : seule une demande soumise se traite.") % {"statut": demande.get_statut_display().lower()}})
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
    search_fields = ("code", "reference_bc", "reference_gr",)

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

    def get_permissions(self):
        # Validation M2 / DR : rôles Achats / Direction contrôlés par le service (hors rôles d'écriture M4).
        if getattr(self, "action", None) in ("valider_m2", "valider_dr"):
            return [can_read_module("logistique")()]
        return super().get_permissions()

    def _verrou(self):
        return LocationGR.objects.select_for_update(of=("self",)).select_related("partenaire", "equipement").get(
            pk=self.get_object().pk
        )

    @action(detail=True, methods=["post"], url_path="valider-m2")
    @transaction.atomic
    def valider_m2(self, request, pk=None):
        """Validation Achats (M2) de la commande GR avant émission (seuil paramétré)."""
        return Response(self.get_serializer(valider_commande(self._verrou(), request.user, "m2")).data)

    @action(detail=True, methods=["post"], url_path="valider-dr")
    @transaction.atomic
    def valider_dr(self, request, pk=None):
        """Validation Direction (DR) de la commande GR avant émission (seuil paramétré)."""
        return Response(self.get_serializer(valider_commande(self._verrou(), request.user, "dr")).data)

    @action(detail=True, methods=["post"], url_path="lier-bc-achat")
    @transaction.atomic
    def lier_bc_achat(self, request, pk=None):
        """Relie le BC achats GLOBAL RENTAL (M2) à la prestation : même partenaire GR, compte 618."""
        from achats.models import PurchaseOrder

        bc = fk_input(request.data.get("bon_commande_achat"), PurchaseOrder.objects.all(), "bon_commande_achat")
        if bc is None:
            raise ValidationError({"bon_commande_achat": "BC achats requis."})
        return Response(self.get_serializer(lier_bc_achat(self._verrou(), bc)).data)

    @action(detail=True, methods=["post"], url_path="rapprocher-facture")
    @transaction.atomic
    def rapprocher_facture(self, request, pk=None):
        """Rapproche la facture fournisseur GR (M2 / M10) de la prestation ; écart vs montant attendu."""
        from achats.models import PurchaseInvoice

        facture = fk_input(
            request.data.get("facture_achat"), PurchaseInvoice.objects.select_related("purchase_order"), "facture_achat"
        )
        if facture is None:
            raise ValidationError({"facture_achat": "Facture requise."})
        return Response(self.get_serializer(rapprocher_facture(self._verrou(), facture)).data)

    @action(detail=True, methods=["post"], url_path="receptionner-bl")
    @transaction.atomic
    def receptionner_bl(self, request, pk=None):
        """Réception contrôlée du BL : écarts par ligne, escalade M12 au-delà du seuil paramétré."""
        jour = date_input(request.data.get("date_reception"), "date_reception", default=timezone.localdate())
        litige = str(request.data.get("litige", "")).lower() in ("1", "true", "oui", "on")
        reception = receptionner_bl(
            self._verrou(), request.user, (request.data.get("reference_bl") or "").strip()[:40], jour,
            reserves=str(request.data.get("reserves") or "")[:2000], litige=litige,
        )
        return Response(ReceptionBLGRSerializer(reception).data, status=201)

    @action(detail=True, methods=["post"], url_path="escalader")
    @transaction.atomic
    def escalader(self, request, pk=None):
        """Escalade manuelle d'un litige GR vers M12 (contentieux + dossier GR)."""
        motif = str(request.data.get("motif") or "").strip()
        if not motif:
            raise ValidationError({"motif": "Motif du litige requis."})
        contentieux, dossier = escalader_m12(self._verrou(), request.user, motif[:200])
        return Response({"contentieux": contentieux.code, "dossier_gr": dossier.code}, status=201)

    @action(detail=False, methods=["get"], url_path="donnees-618")
    def donnees_618(self, request):
        """Prestations GR à imputer au 618 (montant attendu, BC, facture) : lecture seule pour M10."""
        data = donnees_618(request.query_params.get("periode"))
        if not can_see_amount(request.user):
            for row in data["rows"]:
                row["montant_attendu"] = row["facture_ecart"] = None
        return Response(data)

    @action(detail=False, methods=["get"], url_path="flux-operations")
    def flux_operations(self, request):
        """Déversement M4 → M3 / M11 : machines, compteurs et BL par affaire."""
        return Response(flux_operations(request.query_params.get("affaire") or None))

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
        reporter_compteur(location.equipement, lecture, jour=date_retour, user=request.user)
        archiver_compteurs(location)
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
        reporter_compteur(lecture.location.equipement, lecture.valeur, jour=lecture.date, user=self.request.user)


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


# --------------------------------------------------------------------------------------------------
# Écarts M4
# --------------------------------------------------------------------------------------------------
class ReleveCompteurParcViewSet(_CommonViewSet):
    """Historique kilométrage / heures du parc : saisie (jamais à la baisse), aucune modification."""

    serializer_class = ReleveCompteurParcSerializer
    http_method_names = ["get", "post"]

    def get_queryset(self):
        qs = ReleveCompteurParc.objects.select_related("equipement", "saisi_par")
        if equipement := self.request.query_params.get("equipement"):
            qs = qs.filter(equipement_id=equipement)
        return qs

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        releve = enregistrer_releve_parc(
            d["equipement"], d["valeur"], d["date"], request.user, d.get("commentaire", "")
        )
        return Response(self.get_serializer(releve).data, status=201)


class HistoriqueEquipementViewSet(_CommonViewSet):
    serializer_class = HistoriqueEquipementSerializer
    http_method_names = ["get"]

    def get_queryset(self):
        qs = HistoriqueEquipement.objects.select_related("equipement", "modifie_par")
        if equipement := self.request.query_params.get("equipement"):
            qs = qs.filter(equipement_id=equipement)
        return qs


class AuditEquipementViewSet(_CommonViewSet):
    """Audit photo d'un équipement : empreinte SHA-256, conservation paramétrée ; ni modification ni suppression."""

    serializer_class = AuditEquipementSerializer
    http_method_names = ["get", "post"]

    def get_queryset(self):
        qs = AuditEquipement.objects.select_related("equipement", "auditeur")
        if equipement := self.request.query_params.get("equipement"):
            qs = qs.filter(equipement_id=equipement)
        return qs

    def perform_create(self, serializer):
        import hashlib

        photo = serializer.validated_data["photo"]
        h = hashlib.sha256()
        for chunk in photo.chunks():
            h.update(chunk)
        photo.seek(0)
        serializer.save(
            auditeur=self.request.user, photo_sha256=h.hexdigest(), conserver_jusqu_au=conservation_jusqu_au(),
        )


class LigneLocationGRViewSet(_CommonViewSet):
    """Lignes du BC GR (modifiables jusqu'à l'émission) ; quantité livrée saisie à la réception du BL."""

    serializer_class = LigneLocationGRSerializer

    def get_queryset(self):
        qs = LigneLocationGR.objects.select_related("location")
        if location := self.request.query_params.get("location"):
            qs = qs.filter(location_id=location)
        return qs

    def perform_destroy(self, instance):
        if instance.location.statut != LocationGR.Statut.BROUILLON or instance.location.emis_le:
            raise ValidationError({"detail": "Lignes du BC figées après émission du BC / GR."})
        instance.delete()

    @action(detail=True, methods=["post"], url_path="livrer")
    @transaction.atomic
    def livrer(self, request, pk=None):
        """Quantité livrée constatée au BL pour cette ligne (base du contrôle des écarts)."""
        ligne = LigneLocationGR.objects.select_for_update(of=("self",)).select_related("location").get(
            pk=self.get_object().pk
        )
        if ligne.location.statut in (LocationGR.Statut.TERMINEE, LocationGR.Statut.ANNULEE):
            raise ValidationError({"detail": "Prestation terminée ou annulée."})
        ligne.quantite_livree = positive_decimal(request.data.get("quantite_livree"), "quantite_livree")
        ligne.save(update_fields=["quantite_livree"])
        return Response(self.get_serializer(ligne).data)


class ReceptionBLGRViewSet(_CommonViewSet):
    serializer_class = ReceptionBLGRSerializer
    http_method_names = ["get"]

    def get_queryset(self):
        qs = ReceptionBLGR.objects.select_related("location", "contentieux", "dossier_gr", "recu_par")
        if location := self.request.query_params.get("location"):
            qs = qs.filter(location_id=location)
        return qs


class ArchiveCompteurGRViewSet(_CommonViewSet):
    serializer_class = ArchiveCompteurGRSerializer
    http_method_names = ["get"]

    def get_queryset(self):
        return ArchiveCompteurGR.objects.select_related("location")
