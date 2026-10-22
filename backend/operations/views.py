"""API module M3 — Opérations (Atelier + Chantier) (RF-ERP-20…23)."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from integrations.idempotency import idempotent
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from .models import (
    AffectationEquipe,
    CapaciteAtelier,
    Equipe,
    PresenceChantier,
    DossierOperationnel,
    GammeOperatoire,
    GammeOperation,
    OrdreFabrication,
    PointageChantier,
    SituationTravaux,
)
from .serializers import (
    AffectationEquipeSerializer,
    CapaciteAtelierSerializer,
    EquipeSerializer,
    PresenceChantierSerializer,
    DossierOperationnelSerializer,
    GammeOperatoireSerializer,
    GammeOperationSerializer,
    OrdreFabricationSerializer,
    PointageChantierSerializer,
    SituationTravauxSerializer,
)
from users.permissions import can_read_module
from .cloture import figer_dossier, transferer_paie, valider_pointage
from .services import CanManageOperations, can_see_amount, charge_stats
from .terrain_a3 import ConsommationOfMixin, controler_synchro


def _pdf_reponse(contenu, nom, type_mime="application/pdf"):
    reponse = HttpResponse(contenu, content_type=type_mime)
    reponse["Content-Disposition"] = f'attachment; filename="{nom}"'
    return reponse


class _CommonViewSet(viewsets.ModelViewSet):
    """Lecture authentifiée ; écriture réservée aux rôles Opérations."""

    http_method_names = ["get", "post", "patch", "delete"]

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [can_read_module("operations")()]
        return [CanManageOperations()]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["can_view_amount"] = can_see_amount(self.request.user)
        return context


class GammeViewSet(_CommonViewSet):
    serializer_class = GammeOperatoireSerializer
    search_fields = ("code", "label",)

    def get_queryset(self):
        qs = GammeOperatoire.objects.all()
        status_ = self.request.query_params.get("status")
        if status_:
            qs = qs.filter(status=status_)
        return qs

    def retrieve(self, request, *args, **kwargs):
        if request.query_params.get("export") == "pdf":  # impression de la gamme
            from .ecarts import gamme_pdf

            gamme = self.get_object()
            return _pdf_reponse(gamme_pdf(gamme), f"{gamme.code}.pdf")
        return super().retrieve(request, *args, **kwargs)


class GammeOperationViewSet(_CommonViewSet):
    serializer_class = GammeOperationSerializer

    def get_queryset(self):
        qs = GammeOperation.objects.select_related("gamme").all()
        gamme = self.request.query_params.get("gamme")
        if gamme:
            qs = qs.filter(gamme_id=gamme)
        return qs


class OrdreFabricationViewSet(ConsommationOfMixin, _CommonViewSet):
    serializer_class = OrdreFabricationSerializer
    search_fields = ("code", "label",)

    def get_queryset(self):
        qs = OrdreFabrication.objects.select_related(
            "affaire", "gamme", "article", "responsible"
        )
        status_ = self.request.query_params.get("status")
        if status_:
            qs = qs.filter(status=status_)
        scope = self.request.query_params.get("scope")
        if scope:
            qs = qs.filter(scope=scope)
        affaire = self.request.query_params.get("affaire")
        if affaire:
            qs = qs.filter(affaire_id=affaire)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        if request.query_params.get("export") == "pdf":  # impression de l'OF (gamme, besoins, pointages)
            from .ecarts import of_pdf

            of = self.get_object()
            return _pdf_reponse(of_pdf(of), f"{of.code}.pdf")
        return super().retrieve(request, *args, **kwargs)

    SCELLES = (OrdreFabrication.Status.CLOTURE, OrdreFabrication.Status.ANNULE)

    def update(self, request, *args, **kwargs):
        of = self.get_object()
        if of.status in self.SCELLES:  # seule une réécriture à l'identique (rejeu des seeds) est tolérée
            ser = self.get_serializer(of, data=request.data, partial=True)
            ser.is_valid(raise_exception=True)
            for champ, valeur in ser.validated_data.items():
                actuel = getattr(of, champ)
                if champ == "soudeurs":
                    differe = {s.pk for s in actuel.all()} != {s.pk for s in valeur}
                else:
                    differe = actuel != valeur
                if differe:
                    raise DRFValidationError("OF clôturé ou annulé : scellé (conservation des données opérationnelles).")
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        of = self.get_object()
        if of.status != OrdreFabrication.Status.PREVU or of.pointages.exists():
            raise DRFValidationError(
                "OF lancé ou déjà pointé : suppression interdite (conservation 10 ans) — l'annuler à la place."
            )
        return super().destroy(request, *args, **kwargs)

    def _transition(self, depuis, vers, controle=None):
        of = OrdreFabrication.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if of.status not in depuis:
            return Response({"detail": f"OF {of.get_status_display().lower()} : action impossible."},
                            status=status.HTTP_400_BAD_REQUEST)
        if controle:
            blocage = controle(of)
            if blocage:
                return Response({"detail": blocage}, status=status.HTTP_400_BAD_REQUEST)
        of.status = vers
        of.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(of).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def lancer(self, request, pk=None):
        reponse = self._transition([OrdreFabrication.Status.PREVU], OrdreFabrication.Status.LANCE)
        if reponse.status_code == status.HTTP_200_OK:
            from .ecarts import verifier_besoins

            verifier_besoins(OrdreFabrication.objects.get(pk=pk), request.user)  # réservation / rupture ⇒ DA + alerte
        return reponse

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def demarrer(self, request, pk=None):
        return self._transition([OrdreFabrication.Status.LANCE], OrdreFabrication.Status.EN_COURS, controle_demarrage)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def terminer(self, request, pk=None):
        reponse = self._transition([OrdreFabrication.Status.EN_COURS], OrdreFabrication.Status.TERMINE)
        if reponse.status_code == status.HTTP_200_OK:
            from .ecarts import archiver_rapport_execution

            archiver_rapport_execution(OrdreFabrication.objects.get(pk=pk), request.user)  # PDF scellé en GED
        return reponse

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def liberer(self, request, pk=None):
        """Libération (clôture) : conformité qualité obligatoire (CDC M3 §6.8, M6 §8.10)."""
        reponse = self._transition([OrdreFabrication.Status.TERMINE], OrdreFabrication.Status.CLOTURE, controle_liberation)
        if reponse.status_code == status.HTTP_200_OK:
            figer_dossier(OrdreFabrication.objects.get(pk=pk))  # dossier opérationnel scellé, archivage 10 ans
            from stocks.reservations import liberer_ordre

            liberer_ordre(OrdreFabrication.objects.get(pk=pk), "OF clôturé : reliquat de réservation libéré")
        return reponse

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def annuler(self, request, pk=None):
        reponse = self._transition(
            [OrdreFabrication.Status.PREVU, OrdreFabrication.Status.LANCE, OrdreFabrication.Status.EN_COURS],
            OrdreFabrication.Status.ANNULE,
        )
        if reponse.status_code == status.HTTP_200_OK:
            from stocks.reservations import liberer_ordre

            liberer_ordre(OrdreFabrication.objects.get(pk=pk), "OF annulé : réservation libérée")
        return reponse

    @action(detail=False, methods=["get"], url_path="charge")
    def charge(self, request):
        """Plan de charge & capacité atelier (RF-ERP-23)."""
        return Response(charge_stats())

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def replanifier(self, request, pk=None):
        """Replanification (ré-ordonnancement) : nouvelles dates ou décalage en jours, motif tracé."""
        from datetime import timedelta

        from config.inputs import date_input

        of = OrdreFabrication.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if of.status not in (OrdreFabrication.Status.PREVU, OrdreFabrication.Status.LANCE, OrdreFabrication.Status.EN_COURS):
            raise DRFValidationError("Seul un OF prévu, lancé ou en cours peut être replanifié.")
        decalage = request.data.get("decalage_jours")
        if decalage not in (None, ""):
            try:
                jours = int(str(decalage))
            except ValueError:
                raise DRFValidationError({"decalage_jours": "Nombre entier de jours attendu."})
            if not of.planned_start:
                raise DRFValidationError({"decalage_jours": "OF sans date de début : saisir les nouvelles dates."})
            debut = of.planned_start + timedelta(days=jours)
            fin = of.planned_end + timedelta(days=jours) if of.planned_end else None
        else:
            debut = date_input(request.data.get("planned_start"), "planned_start", of.planned_start)
            fin = date_input(request.data.get("planned_end"), "planned_end", of.planned_end)
        if debut and fin and fin < debut:
            raise DRFValidationError({"planned_end": "La fin prévue doit être postérieure au début."})
        motif = str(request.data.get("motif", "") or "").strip()
        if not motif:
            raise DRFValidationError({"motif": "Le motif de replanification est obligatoire."})
        of.planned_start, of.planned_end = debut, fin
        of.motif_replanification = motif[:255]
        of.replanifie_le = timezone.now()
        of.save(update_fields=["planned_start", "planned_end", "motif_replanification", "replanifie_le", "updated_at"])
        return Response(self.get_serializer(of).data)

    @action(detail=True, methods=["post"], url_path="verifier-besoins")
    def verifier_besoins(self, request, pk=None):
        """Disponibilité matière de l'OF : réservation, ou rupture ⇒ DA de réapprovisionnement (M2) + alerte."""
        from .ecarts import verifier_besoins
        from .serializers import BesoinMatiereSerializer

        besoins = verifier_besoins(self.get_object(), request.user)
        return Response(BesoinMatiereSerializer(besoins, many=True).data)

    @action(detail=False, methods=["get"])
    def suivi(self, request):
        """Avancement par OF et par affaire (% chantier), coûts engagés et marge à terminaison (montants masqués)."""
        from .ecarts import avancement_et_marges

        return Response(avancement_et_marges(voir_montants=can_see_amount(request.user)))

    @action(detail=False, methods=["post"], url_path="publier-marges")
    @transaction.atomic
    def publier_marges(self, request):
        """Transmission à M11 : événements outbox `operations.marge_terminaison` (rôles montants)."""
        from .ecarts import publier_marges

        if not can_see_amount(request.user):
            return Response({"detail": "Montants restreints : publication réservée."}, status=status.HTTP_403_FORBIDDEN)
        return Response({"publiees": publier_marges(request.user)})

    @action(detail=False, methods=["get"])
    def indicateurs(self, request):
        """Productivité et taux de rebut (rapports d'exécution validés), MO directe / indirecte, retards, ruptures."""
        from datetime import timedelta

        from config.inputs import date_input

        from .ecarts import indicateurs

        fin = date_input(request.query_params.get("fin"), "fin", timezone.localdate())
        debut = date_input(request.query_params.get("debut"), "debut", fin - timedelta(days=30))
        return Response(indicateurs(debut, fin))

    @action(detail=False, methods=["get"], url_path="charge-journaliere")
    def charge_journaliere(self, request):
        """Plan de charge journalier (main-d'œuvre et machine) vs capacité."""
        from config.inputs import date_input

        from .ecarts import charge_journaliere

        debut = date_input(request.query_params.get("debut"), "debut", timezone.localdate())
        try:
            jours = max(1, min(int(request.query_params.get("jours", 14)), 62))
        except ValueError:
            raise DRFValidationError({"jours": "Nombre entier attendu."})
        return Response(charge_journaliere(debut, jours))

    @action(detail=False, methods=["post"], url_path="escalader-surcharges")
    @transaction.atomic
    def escalader_surcharges(self, request):
        """Escalade des surcharges au-delà du seuil (sous-traitance / GLOBAL RENTAL) vers la direction, une fois par semaine."""
        from .ecarts import escalader_surcharges

        return Response({"escalades": len(escalader_surcharges(request.user))})

    @action(detail=False, methods=["get"], url_path="rapport-periodique")
    def rapport_periodique(self, request):
        """Rapport hebdomadaire / mensuel consolidé : JSON, `?export=pdf` ou `?export=xlsx`."""
        from config.inputs import date_input

        from .ecarts import rapport_periodique, rapport_periodique_pdf, rapport_periodique_xlsx

        periode = request.query_params.get("periode", "hebdo")
        if periode not in ("hebdo", "mensuel"):
            raise DRFValidationError({"periode": "hebdo ou mensuel."})
        ref = date_input(request.query_params.get("date"), "date", timezone.localdate())
        data = rapport_periodique(periode, ref, voir_montants=can_see_amount(request.user))
        export = request.query_params.get("export")
        nom = f"rapport-operations-{periode}-{data['debut']}"
        if export == "pdf":
            return _pdf_reponse(rapport_periodique_pdf(data), f"{nom}.pdf")
        if export == "xlsx":
            return _pdf_reponse(rapport_periodique_xlsx(data), f"{nom}.xlsx",
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        return Response(data)


class CapaciteAtelierViewSet(_CommonViewSet):
    serializer_class = CapaciteAtelierSerializer
    queryset = CapaciteAtelier.objects.all()


class EquipeViewSet(_CommonViewSet):
    serializer_class = EquipeSerializer

    def get_queryset(self):
        qs = Equipe.objects.prefetch_related("membres")
        metier = self.request.query_params.get("metier")
        return qs.filter(metier=metier) if metier else qs


class AffectationEquipeViewSet(_CommonViewSet):
    serializer_class = AffectationEquipeSerializer

    def get_queryset(self):
        qs = AffectationEquipe.objects.select_related("equipe", "ordre")
        for param, champ in (("ordre", "ordre_id"), ("equipe", "equipe_id"), ("statut", "statut")):
            valeur = self.request.query_params.get(param)
            if valeur:
                qs = qs.filter(**{champ: valeur})
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def _assert_planifiee(self):
        if self.get_object().statut != AffectationEquipe.Statut.PLANIFIEE:
            raise DRFValidationError("Affectation mobilisée ou terminée : non modifiable ni supprimable.")

    def update(self, request, *args, **kwargs):
        self._assert_planifiee()
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._assert_planifiee()
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def mobiliser(self, request, pk=None):
        """Fiche de mobilisation : atteste la mobilisation de l'équipe (serveur) ; l'OF ne doit pas être clos."""
        aff = AffectationEquipe.objects.select_for_update(of=("self",)).select_related("ordre").get(pk=self.get_object().pk)
        if aff.statut != AffectationEquipe.Statut.PLANIFIEE:
            raise DRFValidationError("Seule une affectation planifiée peut être mobilisée.")
        if aff.ordre.status in (OrdreFabrication.Status.CLOTURE, OrdreFabrication.Status.ANNULE):
            raise DRFValidationError(f"OF {aff.ordre.code} clos ou annulé : mobilisation impossible.")
        from .ecarts import controler_mobilisation

        blocage = controler_mobilisation(aff)  # absences / congés M9 des membres sur la période
        if blocage:
            raise DRFValidationError(blocage)
        aff.statut = AffectationEquipe.Statut.MOBILISEE
        aff.mobilise_par = request.user
        aff.mobilise_le = timezone.now()
        aff.save(update_fields=["statut", "mobilise_par", "mobilise_le"])
        return Response(self.get_serializer(aff).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def terminer(self, request, pk=None):
        aff = AffectationEquipe.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if aff.statut != AffectationEquipe.Statut.MOBILISEE:
            raise DRFValidationError("Seule une affectation mobilisée peut être terminée.")
        aff.statut = AffectationEquipe.Statut.TERMINEE
        aff.save(update_fields=["statut"])
        return Response(self.get_serializer(aff).data)


class PresenceChantierViewSet(_CommonViewSet):
    serializer_class = PresenceChantierSerializer

    def get_queryset(self):
        qs = PresenceChantier.objects.select_related("ordre", "employe")
        for param, champ in (("ordre", "ordre_id"), ("employe", "employe_id"), ("statut", "statut")):
            valeur = self.request.query_params.get(param)
            if valeur:
                qs = qs.filter(**{champ: valeur})
        if self.request.query_params.get("from"):
            qs = qs.filter(date__gte=self.request.query_params["from"])
        if self.request.query_params.get("to"):
            qs = qs.filter(date__lte=self.request.query_params["to"])
        return qs

    def perform_create(self, serializer):
        serializer.save(releve_par=self.request.user)


class DossierOperationnelViewSet(viewsets.ReadOnlyModelViewSet):
    """Dossiers opérationnels scellés à la libération des OF (lecture seule)."""

    serializer_class = DossierOperationnelSerializer
    queryset = DossierOperationnel.objects.select_related("ordre")

    def get_permissions(self):
        return [can_read_module("operations")()]

    @action(detail=False, methods=["get"])
    def registre(self, request):
        """Registre documentaire M3 : documents GED liés aux objets opérations (rapports, pièces jointes aux OF)."""
        from juridique.models import LienDocument

        liens = LienDocument.objects.filter(module="M3").select_related("document", "document__type").order_by("-created_at")[:500]
        return Response([
            {"id": str(l.pk), "document": str(l.document_id), "titre": l.document.title, "reference": l.document.reference,
             "type": l.document.type.label if l.document.type_id else None, "objet": l.objet_label,
             "sha256": l.document.sha256, "note": l.note, "lie_le": l.created_at.isoformat()}
            for l in liens
        ])


class PointageChantierViewSet(_CommonViewSet):
    serializer_class = PointageChantierSerializer
    search_fields = ("code", "worker_name",)

    def get_queryset(self):
        qs = PointageChantier.objects.select_related("ordre", "worker").all()
        ordre = self.request.query_params.get("ordre")
        if ordre:
            qs = qs.filter(ordre_id=ordre)
        status_ = self.request.query_params.get("status")
        if status_:
            qs = qs.filter(status=status_)
        if self.request.query_params.get("from"):
            qs = qs.filter(date__gte=self.request.query_params["from"])
        if self.request.query_params.get("to"):
            qs = qs.filter(date__lte=self.request.query_params["to"])
        return qs

    def perform_create(self, serializer):
        d = serializer.validated_data
        if d.get("saisi_le"):  # saisie terrain synchronisée : conflits (délai, doublon) avant enregistrement
            doublons = PointageChantier.objects.filter(ordre=d["ordre"], date=d["date"], hours=d["hours"])
            if d.get("employe"):
                doublons = doublons.filter(employe=d["employe"])
            elif d.get("worker"):
                doublons = doublons.filter(worker=d["worker"])
            else:
                doublons = doublons.filter(worker_name__iexact=d.get("worker_name", ""))
            controler_synchro(d["saisi_le"], self.request, doublons, "Pointage")
        serializer.save(created_by=self.request.user)

    @idempotent
    def create(self, request, *args, **kwargs):  # saisie terrain rejouable (hors-ligne)
        return super().create(request, *args, **kwargs)


    def _assert_saisi(self):
        if self.get_object().status != PointageChantier.Status.SAISI:
            raise DRFValidationError("Pointage validé ou transféré en paie : non modifiable ni supprimable.")

    def update(self, request, *args, **kwargs):
        self._assert_saisi()
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._assert_saisi()
        if self.get_object().ordre.status in (OrdreFabrication.Status.TERMINE, OrdreFabrication.Status.CLOTURE):
            raise DRFValidationError("OF terminé ou clôturé : pointage conservé (conservation 10 ans).")
        return super().destroy(request, *args, **kwargs)

    def _pointage_action(self, fonction, *args):
        pointage = self.get_object()
        try:
            fonction(pointage, *args)
        except DjangoValidationError as exc:
            raise DRFValidationError(exc.messages)
        return Response(self.get_serializer(pointage).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def valider(self, request, pk=None):
        """Validation par un tiers du saisisseur (séparation des tâches)."""
        return self._pointage_action(valider_pointage, request.user)

    @action(detail=True, methods=["post"], url_path="transferer-paie")
    @transaction.atomic
    def transferer_paie(self, request, pk=None):
        """Sortie vers M9 : crée la saisie temps de paie (idempotent)."""
        return self._pointage_action(transferer_paie)


class SituationTravauxViewSet(_CommonViewSet):
    serializer_class = SituationTravauxSerializer
    search_fields = ("code", "label",)

    def get_queryset(self):
        qs = SituationTravaux.objects.select_related("affaire", "created_by", "validated_by").all()
        status_ = self.request.query_params.get("status")
        if status_:
            qs = qs.filter(status=status_)
        affaire = self.request.query_params.get("affaire")
        if affaire:
            qs = qs.filter(affaire_id=affaire)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    LOCKED = (SituationTravaux.Status.VALIDEE, SituationTravaux.Status.FACTUREE)

    def _assert_unlocked(self):
        if self.get_object().status in self.LOCKED:
            raise DRFValidationError("Situation validée ou facturée : non modifiable ni supprimable.")

    def update(self, request, *args, **kwargs):
        self._assert_unlocked()
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._assert_unlocked()
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def soumettre(self, request, pk=None):
        """Brouillon → soumise à validation (circuit : le créateur soumet, un tiers valide)."""
        situation = SituationTravaux.objects.select_for_update().get(pk=self.get_object().pk)
        if situation.status != SituationTravaux.Status.BROUILLON:
            raise DRFValidationError("Seule une situation en brouillon peut être soumise.")
        situation.status = SituationTravaux.Status.SOUMISE
        situation.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(situation).data)

    @action(detail=True, methods=["post"], url_path="validate")
    @transaction.atomic
    def validate(self, request, pk=None):
        """Validation d'une situation de travaux (RF-ERP-22) — une seule fois, par un tiers du créateur."""
        situation = SituationTravaux.objects.select_for_update().get(pk=self.get_object().pk)
        if situation.created_by_id and situation.created_by_id == request.user.id:
            raise DRFValidationError("Séparation des tâches : le créateur d'une situation ne peut pas la valider.")
        if situation.status not in (
            SituationTravaux.Status.BROUILLON,
            SituationTravaux.Status.SOUMISE,
        ):
            raise DRFValidationError("Situation déjà validée ou facturée.")
        situation.status = SituationTravaux.Status.VALIDEE
        situation.validated_by = request.user
        situation.validated_at = timezone.now()
        situation.save(update_fields=["status", "validated_by", "validated_at", "updated_at"])
        return Response(self.get_serializer(situation).data)


    @action(detail=False, methods=["get"], url_path="a-facturer")
    def a_facturer(self, request):
        """Sortie vers M10 : situations validées, valorisées et non encore facturées."""
        qs = self.get_queryset().filter(status=SituationTravaux.Status.VALIDEE, amount__gt=0)
        return Response(self.get_serializer(qs, many=True).data)

    @action(detail=True, methods=["post"], url_path="marquer-facturee")
    @transaction.atomic
    def marquer_facturee(self, request, pk=None):
        """Retour de M10 : référence de la facture émise ; la situation est ensuite scellée."""
        situation = SituationTravaux.objects.select_for_update().get(pk=self.get_object().pk)
        ref = str(request.data.get("facture_ref", "")).strip()
        if situation.status != SituationTravaux.Status.VALIDEE:
            raise DRFValidationError("Seule une situation validée peut être facturée.")
        from .ecarts import param

        if param("RECU_CLIENT_OBLIGATOIRE") and not situation.recue_le:
            raise DRFValidationError("Reçu client obligatoire avant facturation (paramètre provisoire).")
        if not ref:
            raise DRFValidationError({"facture_ref": "La référence de la facture est obligatoire."})
        situation.status = SituationTravaux.Status.FACTUREE
        situation.facture_ref = ref
        situation.facture_le = timezone.localdate()
        situation.save(update_fields=["status", "facture_ref", "facture_le", "updated_at"])
        return Response(self.get_serializer(situation).data)

    @action(detail=True, methods=["post"], url_path="accuser-reception")
    @transaction.atomic
    def accuser_reception(self, request, pk=None):
        """Étape « reçu » : le client accuse réception de la situation validée (signataire tracé)."""
        situation = SituationTravaux.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        signataire = str(request.data.get("recue_signataire", "") or "").strip()
        if situation.status not in (SituationTravaux.Status.VALIDEE, SituationTravaux.Status.FACTUREE):
            raise DRFValidationError("Seule une situation validée peut être reçue par le client.")
        if situation.recue_le:
            raise DRFValidationError("Reçu client déjà enregistré.")
        if not signataire:
            raise DRFValidationError({"recue_signataire": "Le nom du signataire client est obligatoire."})
        situation.recue_le = timezone.now()
        situation.recue_signataire = signataire[:150]
        situation.save(update_fields=["recue_le", "recue_signataire", "updated_at"])
        return Response(self.get_serializer(situation).data)

    @action(detail=True, methods=["post"], url_path="valoriser-attachements")
    @transaction.atomic
    def valoriser_attachements(self, request, pk=None):
        """Montant de la situation = somme des attachements signés rattachés (métrés × prix)."""
        from decimal import Decimal

        situation = SituationTravaux.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if situation.status not in (SituationTravaux.Status.BROUILLON, SituationTravaux.Status.SOUMISE):
            raise DRFValidationError("Situation validée ou facturée : montant figé.")
        signes = list(situation.attachements.filter(statut="signe"))
        if not signes:
            raise DRFValidationError("Aucun attachement signé rattaché à la situation.")
        situation.amount = sum((a.montant for a in signes), Decimal("0"))
        situation.save(update_fields=["amount", "updated_at"])
        return Response(self.get_serializer(situation).data)


def controle_demarrage(of):
    """Démarrage d'un OF : permis HSE en vigueur pour un chantier (CDC M3 §6.8, M7 §9.10) et soudeurs affectés
    qualifiés à la date du jour (CDC M6 §8.11). Retourne le motif de blocage, ou None."""
    from hse.models import PermisTravail
    from qualite.models import QualificationSoudeur

    jour = timezone.localdate()
    if of.scope == OrdreFabrication.Scope.CHANTIER:
        permis_ok = PermisTravail.objects.filter(
            ordre=of, statut__in=[PermisTravail.Statut.VALIDE, PermisTravail.Statut.ACTIF], date_debut__lte=jour,
        ).filter(Q(date_fin__isnull=True) | Q(date_fin__gte=jour)).exists()
        if not permis_ok:
            return f"OF chantier {of.code} : aucun permis de travail HSE en vigueur — démarrage interdit (CDC M3 §6.8)."
    non_qualifies = [
        str(s) for s in of.soudeurs.all()
        if not QualificationSoudeur.objects.filter(
            soudeur=s, statut=QualificationSoudeur.Statut.VALIDE, date_validite__gte=jour
        ).exists()
    ]
    if non_qualifies:
        return f"Soudeur(s) sans qualification valide : {', '.join(non_qualifies)} — démarrage interdit (CDC M6 §8.11)."
    return None


def controle_liberation(of):
    """Libération : au moins un contrôle qualité validé conforme, aucun contrôle en attente ou non conforme, aucune NC
    ouverte sur l'OF (CDC M3 §6.11 « aucun OF libéré sans conformité qualité »)."""
    from qualite.models import ControleQualite, NonConformite

    controles = ControleQualite.objects.filter(ordre=of).exclude(statut=ControleQualite.Statut.ANNULE)
    if not controles.filter(statut=ControleQualite.Statut.VALIDE, resultat=ControleQualite.Resultat.CONFORME).exists():
        return f"OF {of.code} : aucun contrôle qualité validé conforme (CND / ITP) — libération interdite."
    en_attente = controles.exclude(statut=ControleQualite.Statut.VALIDE).count()
    if en_attente:
        return f"OF {of.code} : {en_attente} contrôle(s) qualité non validé(s) (ITP / CND en cours) — libération interdite."
    if controles.filter(resultat=ControleQualite.Resultat.NON_CONFORME).exists():
        return f"OF {of.code} : contrôle non conforme — reprise et re-contrôle requis avant libération."
    if NonConformite.objects.filter(controle__ordre=of).exclude(statut=NonConformite.Statut.CLOTUREE).exists():
        return f"OF {of.code} : NC ouverte(s) sur l'OF — traitement et clôture requis avant libération."
    from qualite.models import PunchItem

    bloquantes = PunchItem.objects.filter(ordre=of, categorie=PunchItem.Categorie.A, statut=PunchItem.Statut.OUVERTE).count()
    if bloquantes:
        return f"OF {of.code} : {bloquantes} réserve(s) A de la punch list ouverte(s) — levée requise avant libération."
    return None


# ----------------------------------------------------------------------------------------------------------------
# Écarts M3 (lot 2)
# ----------------------------------------------------------------------------------------------------------------
from rest_framework.exceptions import PermissionDenied  # noqa: E402

from config.inputs import positive_decimal  # noqa: E402

from . import ecarts  # noqa: E402
from .models import (  # noqa: E402
    Attachement,
    BesoinMatiere,
    BonTransfert,
    EscaladeSurcharge,
    FicheControleChantier,
    FichePreparation,
    ParametreOperations,
    RapportExecution,
    RepartitionAffaireOF,
)
from .serializers import (  # noqa: E402
    AttachementSerializer,
    BesoinMatiereSerializer,
    BonTransfertSerializer,
    EscaladeSurchargeSerializer,
    FicheControleChantierSerializer,
    FichePreparationSerializer,
    ParametreOperationsSerializer,
    RapportExecutionSerializer,
    RepartitionAffaireOFSerializer,
    valider_parametre,
)
from .services import OPERATIONS_CONFIRM_ROLES  # noqa: E402


def _fichier(contenu, nom, type_mime):
    reponse = HttpResponse(contenu, content_type=type_mime)
    reponse["Content-Disposition"] = f'attachment; filename="{nom}"'
    return reponse


def _pdf(contenu, nom):
    return _fichier(contenu, nom, "application/pdf")


class _PdfMixin:
    """`GET <détail>/?export=pdf` : impression PDF de la pièce (reportlab)."""

    pdf_builder = None

    def retrieve(self, request, *args, **kwargs):
        if request.query_params.get("export") == "pdf":
            obj = self.get_object()
            return _pdf(type(self).pdf_builder(obj), f"{obj.code}.pdf")
        return super().retrieve(request, *args, **kwargs)


def _locked(viewset, champ, ouverts, message):
    if getattr(viewset.get_object(), champ) not in ouverts:
        raise DRFValidationError(message)


class ParametreOperationsViewSet(_CommonViewSet):
    """Paramètres M3 provisoires : modifiables par les rôles opérations, confirmés par la direction des opérations."""

    serializer_class = ParametreOperationsSerializer
    queryset = ParametreOperations.objects.all()
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        ecarts.assurer_parametres()
        return super().get_queryset()

    def create(self, request, *args, **kwargs):
        return Response({"detail": "Paramètres prédéfinis : modification seulement."}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def _modifier(self, p, valeur):
        valider_parametre(p.code, valeur)
        if valeur != p.valeur:
            p.valeur = valeur
            p.statut_valeur = ParametreOperations.StatutValeur.PROVISOIRE
            p.confirme_par = None
            p.confirme_le = None
            p.save()
        return Response(self.get_serializer(p).data)

    def partial_update(self, request, *args, **kwargs):
        return self._modifier(self.get_object(), positive_decimal(request.data.get("valeur"), "valeur"))

    def update(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def modifier(self, request, pk=None):
        p = ParametreOperations.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        return self._modifier(p, positive_decimal(request.data.get("valeur"), "valeur"))

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def confirmer(self, request, pk=None):
        u = request.user
        if not (u.is_staff or u.role in OPERATIONS_CONFIRM_ROLES):
            raise PermissionDenied("Confirmation réservée à la direction des opérations et au-dessus.")
        p = ParametreOperations.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        p.statut_valeur = ParametreOperations.StatutValeur.CONFIRME
        p.confirme_par = u
        p.confirme_le = timezone.now()
        p.save(update_fields=["statut_valeur", "confirme_par", "confirme_le"])
        return Response(self.get_serializer(p).data)


class FichePreparationViewSet(_PdfMixin, _CommonViewSet):
    serializer_class = FichePreparationSerializer
    pdf_builder = ecarts.fiche_preparation_pdf

    def get_queryset(self):
        qs = FichePreparation.objects.select_related("ordre", "valide_par")
        ordre = self.request.query_params.get("ordre")
        return qs.filter(ordre_id=ordre) if ordre else qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def update(self, request, *args, **kwargs):
        _locked(self, "statut", [FichePreparation.Statut.BROUILLON], "Fiche validée : non modifiable.")
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        _locked(self, "statut", [FichePreparation.Statut.BROUILLON], "Fiche validée : non supprimable.")
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def valider(self, request, pk=None):
        """Préparation prête : contrôle de disponibilité matière (réservation / rupture ⇒ DA), puis visa."""
        fiche = FichePreparation.objects.select_for_update(of=("self",)).select_related("ordre").get(pk=self.get_object().pk)
        if fiche.statut != FichePreparation.Statut.BROUILLON:
            raise DRFValidationError("Fiche déjà validée.")
        besoins = ecarts.verifier_besoins(fiche.ordre, request.user)
        ruptures = [b for b in besoins if b.statut == BesoinMatiere.Statut.RUPTURE]
        if ruptures:
            raise DRFValidationError(
                f"Rupture matière sur {len(ruptures)} article(s) : DA générée(s), préparation non validable."
            )
        fiche.statut = FichePreparation.Statut.VALIDEE
        fiche.valide_par = request.user
        fiche.valide_le = timezone.now()
        fiche.save(update_fields=["statut", "valide_par", "valide_le"])
        return Response(self.get_serializer(fiche).data)


class BesoinMatiereViewSet(_CommonViewSet):
    serializer_class = BesoinMatiereSerializer

    def get_queryset(self):
        qs = BesoinMatiere.objects.select_related("ordre", "article", "demande_achat")
        for param, champ in (("ordre", "ordre_id"), ("statut", "statut")):
            valeur = self.request.query_params.get(param)
            if valeur:
                qs = qs.filter(**{champ: valeur})
        return qs

    def update(self, request, *args, **kwargs):
        _locked(self, "statut", [BesoinMatiere.Statut.A_VERIFIER, BesoinMatiere.Statut.RUPTURE], "Besoin réservé ou servi : non modifiable.")
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        _locked(self, "statut", [BesoinMatiere.Statut.A_VERIFIER, BesoinMatiere.Statut.RUPTURE], "Besoin réservé ou servi : non supprimable.")
        return super().destroy(request, *args, **kwargs)


class RapportExecutionViewSet(_PdfMixin, _CommonViewSet):
    serializer_class = RapportExecutionSerializer
    pdf_builder = ecarts.rapport_pdf

    def get_queryset(self):
        qs = RapportExecution.objects.select_related("ordre", "valide_par")
        for param, champ in (("ordre", "ordre_id"), ("type", "type"), ("statut", "statut")):
            valeur = self.request.query_params.get(param)
            if valeur:
                qs = qs.filter(**{champ: valeur})
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def update(self, request, *args, **kwargs):
        _locked(self, "statut", [RapportExecution.Statut.BROUILLON], "Rapport validé : non modifiable.")
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        _locked(self, "statut", [RapportExecution.Statut.BROUILLON], "Rapport validé : non supprimable (conservation).")
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def valider(self, request, pk=None):
        rapport = RapportExecution.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if rapport.statut != RapportExecution.Statut.BROUILLON:
            raise DRFValidationError("Rapport déjà validé.")
        rapport.statut = RapportExecution.Statut.VALIDE
        rapport.valide_par = request.user
        rapport.valide_le = timezone.now()
        rapport.save(update_fields=["statut", "valide_par", "valide_le"])
        return Response(self.get_serializer(rapport).data)


class FicheControleChantierViewSet(_CommonViewSet):
    """Fiche d'autocontrôle chantier : saisie unique, inaltérable (visa serveur)."""

    serializer_class = FicheControleChantierSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = FicheControleChantier.objects.select_related("ordre", "controle_par")
        ordre = self.request.query_params.get("ordre")
        return qs.filter(ordre_id=ordre) if ordre else qs

    def perform_create(self, serializer):
        fiche = serializer.save(controle_par=self.request.user)
        if not fiche.conforme:
            ecarts._notifier(
                ecarts._destinataires("qaqc", "directeur_operations", ordre=fiche.ordre),
                f"Contrôle chantier non conforme — {fiche.ordre.code}",
                f"Fiche {fiche.code} ({fiche.objet}) : point(s) non conforme(s). Traitement qualité à engager (M6).",
            )


class BonTransfertViewSet(_PdfMixin, _CommonViewSet):
    serializer_class = BonTransfertSerializer
    pdf_builder = ecarts.transfert_pdf

    def get_queryset(self):
        qs = BonTransfert.objects.select_related("ordre")
        for param, champ in (("ordre", "ordre_id"), ("statut", "statut"), ("type", "type")):
            valeur = self.request.query_params.get(param)
            if valeur:
                qs = qs.filter(**{champ: valeur})
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def update(self, request, *args, **kwargs):
        _locked(self, "statut", [BonTransfert.Statut.PREPARE], "Bon expédié : non modifiable.")
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        _locked(self, "statut", [BonTransfert.Statut.PREPARE], "Bon expédié : non supprimable.")
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def expedier(self, request, pk=None):
        bt = BonTransfert.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if bt.statut != BonTransfert.Statut.PREPARE:
            raise DRFValidationError("Seul un bon préparé peut être expédié.")
        bt.statut = BonTransfert.Statut.EXPEDIE
        bt.expedie_par = request.user
        bt.expedie_le = timezone.now()
        bt.save(update_fields=["statut", "expedie_par", "expedie_le"])
        return Response(self.get_serializer(bt).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def receptionner(self, request, pk=None):
        bt = BonTransfert.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if bt.statut != BonTransfert.Statut.EXPEDIE:
            raise DRFValidationError("Seul un bon expédié peut être réceptionné.")
        bt.statut = BonTransfert.Statut.RECEPTIONNE
        bt.receptionne_par = request.user
        bt.receptionne_le = timezone.now()
        bt.reserves = str(request.data.get("reserves", "") or "")[:255]
        bt.save(update_fields=["statut", "receptionne_par", "receptionne_le", "reserves"])
        return Response(self.get_serializer(bt).data)


class AttachementViewSet(_CommonViewSet):
    serializer_class = AttachementSerializer

    def get_queryset(self):
        qs = Attachement.objects.select_related("ordre", "situation")
        for param, champ in (("ordre", "ordre_id"), ("situation", "situation_id"), ("statut", "statut")):
            valeur = self.request.query_params.get(param)
            if valeur:
                qs = qs.filter(**{champ: valeur})
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def update(self, request, *args, **kwargs):
        _locked(self, "statut", [Attachement.Statut.BROUILLON], "Attachement signé : non modifiable.")
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        _locked(self, "statut", [Attachement.Statut.BROUILLON], "Attachement signé : non supprimable.")
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def signer(self, request, pk=None):
        """Signature contradictoire du métré par le client (nom du signataire obligatoire)."""
        att = Attachement.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        signataire = str(request.data.get("signataire_client", "") or "").strip()
        if att.statut != Attachement.Statut.BROUILLON:
            raise DRFValidationError("Attachement déjà signé.")
        if not signataire:
            raise DRFValidationError({"signataire_client": "Le nom du signataire client est obligatoire."})
        att.statut = Attachement.Statut.SIGNE
        att.signataire_client = signataire[:150]
        att.signe_le = timezone.now()
        att.save(update_fields=["statut", "signataire_client", "signe_le"])
        return Response(self.get_serializer(att).data)


class RepartitionAffaireOFViewSet(_CommonViewSet):
    serializer_class = RepartitionAffaireOFSerializer

    def get_queryset(self):
        qs = RepartitionAffaireOF.objects.select_related("ordre", "affaire")
        ordre = self.request.query_params.get("ordre")
        return qs.filter(ordre_id=ordre) if ordre else qs


class EscaladeSurchargeViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EscaladeSurchargeSerializer
    queryset = EscaladeSurcharge.objects.select_related("escalade_par")

    def get_permissions(self):
        return [can_read_module("operations")()]


class FluxM4View(viewsets.ViewSet):
    """Flux M4 → M3 par affaire (machines parc / GR, compteurs, BL), lu par l'écran opérations (lecture seule)."""

    permission_classes = [can_read_module("operations")]

    def list(self, request):
        from logistique.services import flux_operations

        affaire = request.query_params.get("affaire") or None
        if affaire:
            import uuid as _uuid

            try:
                _uuid.UUID(str(affaire))
            except ValueError:
                raise DRFValidationError({"affaire": "Identifiant d'affaire invalide."})
        return Response(flux_operations(affaire))
