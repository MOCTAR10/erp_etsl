"""Vues API M7 — HSE : Hygiène, Sécurité & Environnement."""

from django.db import transaction
from django.utils import timezone
from integrations.idempotency import idempotent
from config.inputs import date_input, positive_decimal
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from rest_framework.permissions import BasePermission

from config.inputs import fk_input
from rh_paie.models import Employe
from users.models import User

from .models import (
    ConsommationEnvironnement,
    PlanReductionImpact,
    RevueDirectionHse,
    AptitudeMedicale,
    ParametreHse,
    ActionHse,
    AuditHse,
    BordereauDechet,
    ConstatAudit,
    Duer,
    Epi,
    EquipementAtex,
    EvaluationRisque,
    ExerciceUrgence,
    ExigenceHabilitation,
    FormationSecurite,
    Incident,
    PermisTravail,
    PlanUrgence,
)
from .serializers import (
    ConsommationEnvironnementSerializer,
    PlanReductionImpactSerializer,
    RevueDirectionHseSerializer,
    AptitudeMedicaleSerializer,
    ParametreHseSerializer,
    PersonnelHseSerializer,
    ActionHseSerializer,
    AuditHseSerializer,
    BordereauDechetSerializer,
    ConstatAuditSerializer,
    DuerSerializer,
    EpiSerializer,
    EquipementAtexSerializer,
    EvaluationRisqueSerializer,
    ExerciceUrgenceSerializer,
    ExigenceHabilitationSerializer,
    FormationSecuriteSerializer,
    IncidentSerializer,
    PermisTravailSerializer,
    PlanUrgenceSerializer,
)
from .services import (
    publier_formation_rh,
    PERMIS_NIVEAU_LIBELLES,
    CanManageHse,
    CanValidateHse,
    can_validate_hse,
    habilitations_manquantes,
    peut_signer_niveau,
)


def _as_bool(value):
    """Booléen tolérant multipart (DRF renvoie des chaînes "True"/"False")."""
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("true", "1", "yes")


class PermisTravailViewSet(viewsets.ModelViewSet):
    queryset = PermisTravail.objects.select_related(
        "affaire", "ordre", "demandeur", "validateur"
    ).all()
    serializer_class = PermisTravailSerializer
    search_fields = ("code", "emplacement",)
    permission_classes = [CanValidateHse]

    def get_permissions(self):
        # Le visa d'un niveau se contrôle dans l'action (signataires par niveau) : un chef d'atelier (superviseur)
        # doit pouvoir y accéder, alors que les autres écritures restent au cercle de validation HSE.
        # Demande, intervenants et pièces jointes : tout rôle d'écriture HSE (chef d'atelier demandeur, CDC M7-11) ;
        # la séparation des tâches reste garantie au visa (le demandeur ne signe aucun niveau).
        if self.action in ("valider", "create", "ajouter_intervenant", "joindre_photo", "joindre_plan"):
            return [CanManageHse()]
        return super().get_permissions()

    def perform_create(self, serializer):
        # Le demandeur est toujours l'auteur de la demande : sinon la séparation des tâches (le demandeur ne valide
        # pas son propre permis) se contourne en créant le permis « au nom » d'un collègue.
        from .services import notifier_niveau_suivant

        permis = serializer.save(demandeur=self.request.user)
        notifier_niveau_suivant(permis)
        if permis.site_gr:
            from .ecarts_m6m7 import partager_site_gr

            partager_site_gr(
                f"Site GLOBAL RENTAL : permis {permis.code} demandé",
                f"{permis.get_type_permis_display()} — {permis.emplacement}, début le {permis.date_debut:%d/%m/%Y}.",
                exclure=self.request.user,
            )

    def _modifiable(self, permis):
        if permis.statut in PermisTravail.STATUTS_FIGES:
            raise serializers.ValidationError({"detail": f"Permis {permis.get_statut_display().lower()} : figé."})

    @action(detail=True, methods=["post"], url_path="ajouter-intervenant")
    def ajouter_intervenant(self, request, pk=None):
        permis = self.get_object()
        self._modifiable(permis)
        employe = fk_input(request.data.get("employe"), Employe.objects.all(), "employe")
        if employe is None:
            raise serializers.ValidationError({"employe": "Salarié requis."})
        permis.intervenants.add(employe)
        return Response(self.get_serializer(permis).data)

    @action(detail=True, methods=["post"], url_path="joindre-photo")
    def joindre_photo(self, request, pk=None):
        return self._joindre(request, "photo")

    @action(detail=True, methods=["post"], url_path="joindre-plan")
    def joindre_plan(self, request, pk=None):
        return self._joindre(request, "plan")

    def _joindre(self, request, piece):
        """Photo de la zone ou plan / croquis du permis (CDC M7-11) : images ou PDF, 10 Mo au plus."""
        import os

        from .services import PIECE_TAILLE_MAX, PIECES_PERMIS

        permis = self.get_object()
        self._modifiable(permis)
        fichier = request.FILES.get("fichier")
        if fichier is None:
            raise serializers.ValidationError({"fichier": "Fichier requis."})
        if os.path.splitext(fichier.name)[1].lower() not in PIECES_PERMIS[piece]:
            raise serializers.ValidationError({"fichier": f"Formats acceptés : {', '.join(PIECES_PERMIS[piece])}."})
        if fichier.size > PIECE_TAILLE_MAX:
            raise serializers.ValidationError({"fichier": "Fichier trop volumineux (10 Mo au plus)."})
        getattr(permis, piece).save(fichier.name, fichier, save=False)
        permis.save(update_fields=[piece, "updated_at"])
        return Response(self.get_serializer(permis).data)

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if type_permis := params.get("type"):
            qs = qs.filter(type_permis=type_permis)
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        if params.get("actifs") == "1":
            qs = qs.filter(statut=PermisTravail.Statut.ACTIF)
        return qs

    @action(detail=True, methods=["post"], url_path="valider")
    @transaction.atomic
    def valider(self, request, pk=None):
        """Visa du niveau attendu (superviseur → HSE → DG, paramétrable) ; refus possible à chaque niveau."""
        permis = PermisTravail.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if permis.statut != PermisTravail.Statut.DEMANDE:
            return Response(
                {"detail": "Le permis n'est plus en attente de validation."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        niveau = permis.prochain_niveau
        if niveau is None:
            return Response({"detail": "Circuit de validation déjà complet."}, status=status.HTTP_400_BAD_REQUEST)
        libelle = PERMIS_NIVEAU_LIBELLES.get(niveau, niveau)
        if not peut_signer_niveau(request.user, niveau):
            return Response(
                {"detail": f"Visa attendu : niveau {libelle} — vous n'êtes pas signataire de ce niveau."},
                status=status.HTTP_403_FORBIDDEN,
            )
        # Séparation des tâches : le demandeur ne signe aucun niveau (hors admin), personne ne signe deux niveaux.
        if permis.demandeur_id == request.user.id and not (request.user.is_staff or request.user.role == "admin"):
            return Response({"detail": "Le demandeur ne peut pas valider son propre permis."},
                            status=status.HTTP_403_FORBIDDEN)
        deja = [n for n in ("superviseur", "hse", "dg") if getattr(permis, f"visa_{n}_par_id") == request.user.id]
        if deja:
            return Response(
                {"detail": f"Vous avez déjà signé le niveau {PERMIS_NIVEAU_LIBELLES[deja[0]]} : un autre signataire est requis."},
                status=status.HTTP_403_FORBIDDEN,
            )
        accept = _as_bool(request.data.get("accept", True))
        maintenant = timezone.now()
        setattr(permis, f"visa_{niveau}_par", request.user)
        setattr(permis, f"visa_{niveau}_le", maintenant)
        if not accept:
            permis.statut = PermisTravail.Statut.REFUSE
            permis.validateur = request.user
            permis.date_validation = maintenant
            if request.data.get("motif"):
                permis.notes = f"Refus niveau {libelle} : {request.data.get('motif')}"
        elif permis.prochain_niveau is None:  # dernière signature
            permis.statut = PermisTravail.Statut.VALIDE
            permis.validateur = request.user
            permis.date_validation = maintenant
        permis.save()
        if permis.statut == PermisTravail.Statut.DEMANDE:
            from .services import notifier_niveau_suivant

            notifier_niveau_suivant(permis)
        return Response(self.get_serializer(permis).data)

    @action(detail=True, methods=["post"], url_path="demarrer")
    def demarrer(self, request, pk=None):
        permis = self.get_object()
        if permis.statut != PermisTravail.Statut.VALIDE:
            return Response(
                {"detail": "Seul un permis validé peut être démarré."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        aujourdhui = timezone.localdate()
        if permis.date_debut > aujourdhui:
            return Response(
                {"detail": f"Le permis ne débute que le {permis.date_debut:%d/%m/%Y}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if permis.date_fin and permis.date_fin < aujourdhui:
            return Response(
                {"detail": "Permis expiré : sa date de fin est dépassée."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from .ecarts_m6m7 import controle_site_gr

        if erreur_gr := controle_site_gr(permis, aujourdhui):
            return Response({"detail": erreur_gr}, status=status.HTTP_400_BAD_REQUEST)
        if manquantes := habilitations_manquantes(permis, aujourdhui):
            return Response(
                {"detail": "Habilitation manquante ou expirée - " + " ; ".join(manquantes)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if permis.gaz_obligatoire and not permis.test_gaz_valide:
            return Response(
                {"detail": (
                    "Test gaz conforme requis avant démarrage "
                    f"(valable {PermisTravail.TEST_GAZ_VALIDITE_HEURES} h) - "
                    f"type {permis.get_type_permis_display()}."
                )},
                status=status.HTTP_400_BAD_REQUEST,
            )
        permis.statut = PermisTravail.Statut.ACTIF
        permis.save()
        return Response(self.get_serializer(permis).data)

    @action(detail=True, methods=["post"], url_path="test-gaz")
    @idempotent
    def test_gaz(self, request, pk=None):
        """Enregistre un test d'atmosphère (conforme / non conforme + mesures).

        Un résultat non conforme sur un permis actif l'arrête (retour à Validé).
        """
        permis = self.get_object()
        if permis.statut not in (PermisTravail.Statut.VALIDE, PermisTravail.Statut.ACTIF):
            return Response(
                {"detail": "Test gaz possible uniquement sur un permis validé ou actif."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        resultat = request.data.get("resultat")
        if resultat not in ("conforme", "non_conforme"):
            return Response(
                {"detail": "Résultat attendu : conforme ou non_conforme."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        permis.test_gaz_resultat = resultat
        permis.test_gaz_valeur = str(request.data.get("valeur", ""))[:120]
        permis.test_gaz_date = timezone.now()
        permis.test_gaz_par = request.user
        if resultat == "non_conforme" and permis.statut == PermisTravail.Statut.ACTIF:
            permis.statut = PermisTravail.Statut.VALIDE
            permis.notes = (permis.notes + "\n" if permis.notes else "") + (
                f"Arrêt : test gaz non conforme ({permis.test_gaz_valeur or 'sans mesure'})."
            )
        permis.save()
        return Response(self.get_serializer(permis).data)

    @action(detail=True, methods=["post"], url_path="cloturer")
    def cloturer(self, request, pk=None):
        permis = self.get_object()
        if permis.statut not in (PermisTravail.Statut.ACTIF, PermisTravail.Statut.VALIDE, PermisTravail.Statut.EXPIRE):
            return Response(
                {"detail": "Le permis n'est pas clôturable."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        permis.statut = PermisTravail.Statut.CLOTURE
        permis.date_cloture = timezone.now()
        permis.save()
        return Response(self.get_serializer(permis).data)


class EvaluationRisqueViewSet(viewsets.ModelViewSet):
    queryset = EvaluationRisque.objects.select_related("responsable", "affaire").all()
    serializer_class = EvaluationRisqueSerializer
    search_fields = ("code", "lieux", "activite",)
    permission_classes = [CanManageHse]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        if params.get("critiques") == "1":
            qs = [r for r in qs if r.criticite == EvaluationRisque.Criticite.CRITIQUE]
        if params.get("ouverts") == "1":
            qs = qs.exclude(statut=EvaluationRisque.Statut.CLOTUREE)
        return qs


class EquipementAtexViewSet(viewsets.ModelViewSet):
    queryset = EquipementAtex.objects.all()
    serializer_class = EquipementAtexSerializer
    search_fields = ("code", "designation",)
    permission_classes = [CanManageHse]

    def get_queryset(self):
        qs = super().get_queryset()
        if statut := self.request.query_params.get("statut"):
            qs = qs.filter(statut=statut)
        if self.request.query_params.get("expires") == "1":
            qs = [
                eq for eq in qs
                if eq.certificat_expire
            ]
        return qs


def escalader_si_grave(incident):
    """CDC M7 §9.8 : escalade DG obligatoire (une seule fois) dès qu'un incident est un accident grave."""
    if not incident.est_grave or incident.escalade_dg_le:
        return
    from users.models import User
    from workflow.models import Notification

    incident.escalade_dg_le = timezone.now()
    incident.save(update_fields=["escalade_dg_le", "updated_at"])
    sujet = f"ESCALADE DG — accident grave {incident.code}"
    message = (
        f"{incident.get_type_incident_display()} de gravité {incident.get_gravite_display().lower()} déclaré le "
        f"{timezone.localtime(incident.date_evenement):%d/%m/%Y %H:%M} à {incident.lieu} : {incident.description[:300]}. "
        "Investigation immédiate requise (CDC M7 §9.8)."
    )
    direction = list(User.objects.filter(is_active=True, role__in=[User.Role.PDG, User.Role.DGA]))
    from workflow.sms import envoyer_sms, sms_actif

    if sms_actif():
        transaction.on_commit(lambda: [envoyer_sms(u, f"{sujet} : {message}") for u in direction])
    Notification.objects.bulk_create([
        Notification(user=u, subject=sujet, message=message, kind="escalation")
        for u in direction
    ])


class IncidentViewSet(viewsets.ModelViewSet):
    queryset = Incident.objects.select_related(
        "declared_by", "enqueteur"
    ).prefetch_related("actions").all()
    serializer_class = IncidentSerializer
    search_fields = ("code", "lieu",)
    permission_classes = [CanManageHse]

    def perform_create(self, serializer):
        incident = serializer.save(declared_by=self.request.user)
        escalader_si_grave(incident)
        if incident.zone == "site_gr":
            from .ecarts_m6m7 import partager_site_gr

            partager_site_gr(
                f"Site GLOBAL RENTAL : {incident.get_type_incident_display().lower()} {incident.code}",
                f"Déclaré le {timezone.localtime(incident.date_evenement):%d/%m/%Y %H:%M} à {incident.lieu} "
                f"(gravité {incident.get_gravite_display().lower()}) : {incident.description[:300]}",
                exclure=self.request.user,
            )

    def perform_update(self, serializer):
        escalader_si_grave(serializer.save())

    @action(detail=False, methods=["get"], url_path="indicateurs")
    def indicateurs(self, request):
        """TRIR / LTIR / LTIFR de la période (défaut : année en cours) — lot 15, CDC M7 §9.7."""
        from .indicateurs import indicateurs_frequence

        today = timezone.localdate()
        params = request.query_params
        debut = date_input(params.get("debut"), "debut", default=today.replace(month=1, day=1))
        fin = date_input(params.get("fin"), "fin", default=today)
        heures = params.get("heures")
        heures = positive_decimal(heures, "heures") if heures not in (None, "") else None
        if fin < debut:
            raise serializers.ValidationError({"fin": "La fin doit suivre le début."})
        from .services import indicateurs_hse

        donnees = indicateurs_frequence(debut, fin, heures)
        donnees.update(indicateurs_hse(debut, fin, donnees["heures"]))
        return Response(donnees)

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if type_incident := params.get("type"):
            qs = qs.filter(type_incident=type_incident)
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        if gravite := params.get("gravite"):
            qs = qs.filter(gravite=gravite)
        if params.get("ouverts") == "1":
            qs = qs.exclude(statut=Incident.Statut.CLOTURE)
        if params.get("archive") == "1":
            qs = qs.filter(archive=True)
        return qs

    @action(detail=True, methods=["post"], url_path="ouvrir-enquete")
    def ouvrir_enquete(self, request, pk=None):
        incident = self.get_object()
        if incident.statut == Incident.Statut.CLOTURE:
            return Response(
                {"detail": "Incident clôturé : enquête impossible."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not can_validate_hse(request.user):
            return Response(
                {"detail": "Réservé au HSE et à la hiérarchie."},
                status=status.HTTP_403_FORBIDDEN,
            )
        incident.statut = Incident.Statut.EN_ENQUETE
        incident.enqueteur = request.user
        incident.date_ouverture_enquete = timezone.now()
        incident.save()
        return Response(self.get_serializer(incident).data)

    @action(detail=True, methods=["post"], url_path="plan-action")
    @transaction.atomic
    def plan_action(self, request, pk=None):
        """Enquête → plan d'action (MANUEL §9.6) : cause profonde identifiée et au moins une action décidée."""
        incident = Incident.objects.select_for_update().get(pk=self.get_object().pk)
        if not can_validate_hse(request.user):
            return Response({"detail": "Réservé au HSE et à la hiérarchie."}, status=status.HTTP_403_FORBIDDEN)
        if incident.statut != Incident.Statut.EN_ENQUETE:
            return Response({"detail": "Le plan d'action suit l'enquête."}, status=status.HTTP_400_BAD_REQUEST)
        if request.data.get("cause_profonde"):
            incident.cause_profonde = str(request.data.get("cause_profonde"))
        if not incident.cause_profonde.strip():
            return Response({"cause_profonde": "Cause profonde requise pour arrêter le plan d'action."}, status=status.HTTP_400_BAD_REQUEST)
        if not incident.actions.exists():
            return Response({"detail": "Au moins une action corrective ou préventive est requise."}, status=status.HTTP_400_BAD_REQUEST)
        incident.statut = Incident.Statut.PLAN_ACTION
        incident.plan_action_le = timezone.now()
        incident.save()
        return Response(self.get_serializer(incident).data)

    @action(detail=True, methods=["post"], url_path="ncr-hse")
    @transaction.atomic
    def ncr_hse(self, request, pk=None):
        """NCR-HSE (CDC M7-10) ouverte depuis l'événement : NC du socle qualité, variante HSE (traitement, CAPA, clôture)."""
        from qualite.models import NonConformite

        incident = self.get_object()
        if not can_validate_hse(request.user):
            return Response({"detail": "Réservé au HSE et à la hiérarchie."}, status=status.HTTP_403_FORBIDDEN)
        description = str(request.data.get("description") or "").strip()
        if not description:
            return Response({"description": "Description de l'écart requise."}, status=status.HTTP_400_BAD_REQUEST)
        gravite = request.data.get("gravite") or ("majeure" if incident.gravite != "mineure" else "mineure")
        if gravite not in NonConformite.Gravite.values:
            return Response({"gravite": "Gravité inconnue."}, status=status.HTTP_400_BAD_REQUEST)
        nc = NonConformite.objects.create(
            type_ncr="hse", incident_hse=incident, source=NonConformite.Source.INTERNE, gravite=gravite,
            description=description, decided_by=request.user,
        )
        return Response({"id": str(nc.pk), "code": nc.code, "statut": nc.statut}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="rapport-pdf")
    def rapport_pdf(self, request, pk=None):
        """Rapport d'incident / d'accident (PDF), à tout moment du cycle."""
        from django.http import HttpResponse

        from .services import rapport_incident_pdf

        incident = self.get_object()
        reponse = HttpResponse(rapport_incident_pdf(incident), content_type="application/pdf")
        reponse["Content-Disposition"] = f'inline; filename="{incident.code}.pdf"'
        return reponse

    @action(detail=False, methods=["get"], url_path="registre-osha")
    def registre_osha(self, request):
        """Registre des cas enregistrables (OSHA 300) et synthèse annuelle (OSHA 300A) ; `?export=csv`."""
        from .services import registre_osha

        try:
            annee = int(request.query_params.get("annee") or timezone.localdate().year)
        except ValueError:
            raise serializers.ValidationError({"annee": "Année attendue (AAAA)."})
        registre = registre_osha(annee)
        if request.query_params.get("export") == "csv":
            import csv
            import io

            from django.http import HttpResponse

            buf = io.StringIO()
            writer = csv.writer(buf, delimiter=";")
            writer.writerow(["Cas", "Date", "Lieu", "Zone", "Personnes", "Description", "Classification", "Jours d'arrêt"])
            for r in registre["rows"]:
                writer.writerow([r["cas"], r["date"], r["lieu"], r["zone"], r["personnes"], r["description"],
                                 r["classification"], r["jours_arret"]])
            reponse = HttpResponse(buf.getvalue().encode("utf-8-sig"), content_type="text/csv; charset=utf-8")
            reponse["Content-Disposition"] = f'attachment; filename="registre-osha-{annee}.csv"'
            return reponse
        return Response(registre)

    @action(detail=True, methods=["post"], url_path="cloturer")
    @transaction.atomic
    def cloturer(self, request, pk=None):
        incident = self.get_object()
        if incident.statut == Incident.Statut.CLOTURE:
            return Response(
                {"detail": "Incident déjà clôturé."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not can_validate_hse(request.user):
            return Response(
                {"detail": "Clôture réservée au HSE et à la hiérarchie."},
                status=status.HTTP_403_FORBIDDEN,
            )
        ouvertes = incident.actions.exclude(statut=ActionHse.Statut.CLOTUREE)
        if ouvertes.exists():
            return Response(
                {"detail": f"Actions non soldées : {', '.join(a.code for a in ouvertes)} — clôturez-les d'abord."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        rex = str(request.data.get("retour_experience") or incident.retour_experience or "").strip()
        if incident.type_incident in (Incident.TypeIncident.QUASI_ACCIDENT, Incident.TypeIncident.SITUATION_DANGEREUSE) and not rex:
            return Response(
                {"retour_experience": "Retour d'expérience obligatoire pour clôturer un presque-accident."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        incident.retour_experience = rex
        # La clôture archive l'incident (traçabilité §9.9) : elle engage le HSE, comme l'ouverture d'enquête.
        if not can_validate_hse(request.user):
            return Response(
                {"detail": "Clôture réservée au HSE et à la hiérarchie."},
                status=status.HTTP_403_FORBIDDEN,
            )
        rapport = (request.data.get("rapport") or incident.rapport or "").strip()
        # MANUEL §9.6 : déclaration → enquête → rapport → clôture. Un accident ou un événement majeur/critique
        # ne se clôture pas sans rapport d'enquête.
        if not rapport and (
            incident.type_incident == Incident.TypeIncident.ACCIDENT
            or incident.gravite in (Incident.Gravite.MAJEURE, Incident.Gravite.CRITIQUE)
        ):
            return Response(
                {"rapport": "Rapport d'enquête obligatoire pour clôturer un accident ou un événement majeur/critique."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        raw_date = request.data.get("date_rapport")
        if raw_date:
            try:
                incident.date_rapport = serializers.DateField().run_validation(raw_date)
            except serializers.ValidationError as exc:
                return Response({"date_rapport": exc.detail}, status=status.HTTP_400_BAD_REQUEST)
        incident.rapport = rapport
        incident.statut = Incident.Statut.CLOTURE
        incident.archive = True
        incident.save()
        # Conservation 10 ans (CDC M7 §9.5 / §9.6) : rapport PDF scellé en GED, lié à l'incident.
        from .services import TYPE_GED_RAPPORT_HSE, archiver_ged, rapport_incident_pdf

        incident.document = archiver_ged(
            rapport_incident_pdf(incident), f"{incident.code}.pdf",
            f"Rapport d'incident {incident.code} — {incident.get_type_incident_display()}", TYPE_GED_RAPPORT_HSE,
            "Rapports HSE (incidents, accidents)", incident.code, "hse.incident", incident.pk, request.user,
            mots=("hse", "incident", incident.code),
        )
        incident.save(update_fields=["document"])
        return Response(self.get_serializer(incident).data)

    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        today = timezone.localdate()
        j30 = today + timezone.timedelta(days=30)

        last_accident = (
            Incident.objects.filter(
                type_incident__in=[
                    Incident.TypeIncident.ACCIDENT,
                    Incident.TypeIncident.BLESSURE,
                ],
                date_evenement__lte=timezone.now(),
            ).order_by("-date_evenement").first()
        )
        jours_sans_accident = None
        if last_accident:
            jours_sans_accident = max(
                (timezone.now() - last_accident.date_evenement).days,
                0,
            )

        risques_ouverts = EvaluationRisque.objects.exclude(
            statut=EvaluationRisque.Statut.CLOTUREE
        )
        risques_critiques = sum(
            1
            for r in risques_ouverts
            if r.criticite == EvaluationRisque.Criticite.CRITIQUE
        )

        return Response(
            {
                "jours_sans_accident": jours_sans_accident,
                "incidents_ouverts": Incident.objects.exclude(
                    statut=Incident.Statut.CLOTURE
                ).count(),
                "incidents_critiques": Incident.objects.filter(
                    gravite=Incident.Gravite.CRITIQUE
                ).exclude(statut=Incident.Statut.CLOTURE).count(),
                "actions_ouvertes": ActionHse.objects.exclude(
                    statut=ActionHse.Statut.CLOTUREE
                ).count(),
                "permis_actifs": PermisTravail.objects.filter(
                    statut=PermisTravail.Statut.ACTIF
                ).count(),
                "risques_critiques": risques_critiques,
                "epi_a_renouveler": Epi.objects.filter(
                    statut=Epi.Statut.EN_USAGE,
                    date_renouvellement__lte=j30,
                ).count(),
                "formations_prevues": FormationSecurite.objects.filter(
                    statut=FormationSecurite.Statut.PLANIFIEE
                ).count(),
                "bsd_en_attente": BordereauDechet.objects.filter(
                    statut=BordereauDechet.Statut.EN_ATTENTE
                ).count(),
                "atex_quarantaine": EquipementAtex.objects.filter(
                    statut=EquipementAtex.Statut.QUARANTAINE
                ).count(),
            }
        )


class ActionHseViewSet(viewsets.ModelViewSet):
    queryset = ActionHse.objects.select_related("incident", "risque", "responsable").all()
    serializer_class = ActionHseSerializer
    search_fields = ("code",)
    permission_classes = [CanManageHse]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if incident := params.get("incident"):
            qs = qs.filter(incident_id=incident)
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        if params.get("ouvertes") == "1":
            qs = qs.exclude(statut=ActionHse.Statut.CLOTUREE)
        return qs

    @action(detail=True, methods=["post"], url_path="cloturer")
    def cloturer(self, request, pk=None):
        action = self.get_object()
        if action.statut == ActionHse.Statut.CLOTUREE:
            return Response({"detail": "Action déjà clôturée."}, status=status.HTTP_400_BAD_REQUEST)
        action.statut = ActionHse.Statut.CLOTUREE
        action.closed_at = timezone.now()
        if "efficace" in request.data:
            action.efficace = _as_bool(request.data.get("efficace"))
        action.save()
        return Response(self.get_serializer(action).data)


class FormationSecuriteViewSet(viewsets.ModelViewSet):
    queryset = FormationSecurite.objects.all()
    serializer_class = FormationSecuriteSerializer
    search_fields = ("code", "theme",)
    permission_classes = [CanManageHse]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if type_session := params.get("type"):
            qs = qs.filter(type_session=type_session)
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        if params.get("prevues") == "1":
            qs = qs.filter(statut=FormationSecurite.Statut.PLANIFIEE)
        return qs

    def _apres_enregistrement(self, formation):
        formation.nb_participants = formation.participants.count() or formation.nb_participants
        formation.save(update_fields=["nb_participants"])
        if formation.statut == FormationSecurite.Statut.REALISEE:
            publier_formation_rh(formation)

    def perform_create(self, serializer):
        self._apres_enregistrement(serializer.save())

    def perform_update(self, serializer):
        self._apres_enregistrement(serializer.save())

    @action(detail=True, methods=["post"], url_path="ajouter-participant")
    @transaction.atomic
    def ajouter_participant(self, request, pk=None):
        formation = self.get_object()
        employe = fk_input(request.data.get("employe"), Employe.objects.all(), "employe")
        if employe is None:
            raise serializers.ValidationError({"employe": "Salarié requis."})
        formation.participants.add(employe)
        self._apres_enregistrement(formation)
        return Response(self.get_serializer(formation).data)

    @action(detail=True, methods=["post"], url_path="realiser")
    @transaction.atomic
    def realiser(self, request, pk=None):
        """Session réalisée : chaque participant reçoit sa qualification RH (certificat, échéance de recyclage)."""
        formation = self.get_object()
        if not formation.participants.exists():
            raise serializers.ValidationError({"participants": "Ajouter les participants avant de valider la session."})
        formation.statut = FormationSecurite.Statut.REALISEE
        formation.save(update_fields=["statut", "updated_at"])
        self._apres_enregistrement(formation)
        return Response(self.get_serializer(formation).data)


class EpiViewSet(viewsets.ModelViewSet):
    queryset = Epi.objects.select_related("beneficiaire").all()
    serializer_class = EpiSerializer
    search_fields = ("code", "designation",)
    permission_classes = [CanManageHse]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if type_epi := params.get("type"):
            qs = qs.filter(type_epi=type_epi)
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        if params.get("a_renouveler") == "1":
            j30 = timezone.localdate() + timezone.timedelta(days=30)
            qs = qs.filter(
                statut=Epi.Statut.EN_USAGE,
                date_renouvellement__lte=j30,
            )
        return qs

    @action(detail=False, methods=["get"], url_path="fiche-dotation")
    def fiche_dotation(self, request):
        """Fiche individuelle de dotation EPI d'un salarié (`?employe=`), PDF avec `&export=pdf`."""
        from django.http import HttpResponse

        from .services import _pdf

        employe = fk_input(request.query_params.get("employe"), Employe.objects.all(), "employe")
        if employe is None:
            raise serializers.ValidationError({"employe": "Salarié requis."})
        epi = Epi.objects.filter(employe=employe).order_by("-date_dotation")
        if request.query_params.get("export") != "pdf":
            return Response(EpiSerializer(epi, many=True, context=self.get_serializer_context()).data)
        tableau = [["EPI", "Désignation", "Taille", "Dotation", "Renouvellement", "Statut"]] + [
            [e.get_type_epi_display(), e.designation, e.taille or "—", f"{e.date_dotation:%d/%m/%Y}",
             f"{e.date_renouvellement:%d/%m/%Y}" if e.date_renouvellement else "—", e.get_statut_display()]
            for e in epi
        ]
        contenu = _pdf(f"Fiche individuelle de dotation EPI — {employe}", [("Matricule", employe.code)],
                       tableau if len(tableau) > 1 else None)
        reponse = HttpResponse(contenu, content_type="application/pdf")
        reponse["Content-Disposition"] = f'inline; filename="dotation-epi-{employe.code}.pdf"'
        return reponse


class BordereauDechetViewSet(viewsets.ModelViewSet):
    queryset = BordereauDechet.objects.select_related("transporteur").all()
    serializer_class = BordereauDechetSerializer
    search_fields = ("code", "numero_bsd",)
    permission_classes = [CanManageHse]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if type_dechet := params.get("type"):
            qs = qs.filter(type_dechet=type_dechet)
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        if params.get("dangereux") == "1":
            from .ecarts_m6m7 import codes_dangereux

            qs = qs.filter(type_dechet__in=codes_dangereux())
        return qs

    def _transition(self, request, cible, depuis):
        """Émission puis traitement du BSD : statut posé par action, prestataire agréé contrôlé (paramètre)."""
        from .ecarts_m6m7 import controle_prestataire_bsd

        bsd = BordereauDechet.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if bsd.statut not in depuis:
            return Response({"detail": "Transition impossible depuis ce statut."}, status=status.HTTP_400_BAD_REQUEST)
        if erreur := controle_prestataire_bsd(bsd.type_dechet, bsd.prestataire, bsd.date_enlevement):
            return Response({"prestataire": erreur}, status=status.HTTP_400_BAD_REQUEST)
        if cible == BordereauDechet.Statut.EMIS:
            numero = str(request.data.get("numero_bsd") or bsd.numero_bsd or "").strip()[:80]
            if not numero:
                return Response({"numero_bsd": "N° de BSD requis à l'émission."}, status=status.HTTP_400_BAD_REQUEST)
            bsd.numero_bsd = numero
            bsd.date_enlevement = bsd.date_enlevement or timezone.localdate()
        bsd.statut = cible
        bsd.save()
        if cible == BordereauDechet.Statut.TRAITE:
            self._archiver(bsd)
        return Response(self.get_serializer(bsd).data)

    @action(detail=True, methods=["post"], url_path="affecter-prestataire")
    @transaction.atomic
    def affecter_prestataire(self, request, pk=None):
        """Affecte un prestataire déchets agréé (en cours de validité, type couvert) à un BSD en attente."""
        from .ecarts_m6m7 import controle_prestataire_bsd
        from .models import PrestataireDechet

        bsd = BordereauDechet.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if bsd.statut != BordereauDechet.Statut.EN_ATTENTE:
            return Response({"detail": "BSD déjà émis : prestataire figé."}, status=status.HTTP_400_BAD_REQUEST)
        prestataire = fk_input(request.data.get("prestataire"), PrestataireDechet.objects.all(), "prestataire")
        if prestataire is None:
            return Response({"prestataire": "Prestataire requis."}, status=status.HTTP_400_BAD_REQUEST)
        if not prestataire.est_valide(bsd.date_enlevement) or not prestataire.couvre(bsd.type_dechet):
            erreur = controle_prestataire_bsd(bsd.type_dechet, prestataire, bsd.date_enlevement)
            return Response({"prestataire": erreur or "Prestataire non agréé pour ce BSD."}, status=status.HTTP_400_BAD_REQUEST)
        bsd.prestataire = prestataire
        bsd.save(update_fields=["prestataire", "updated_at"])
        return Response(self.get_serializer(bsd).data)

    @action(detail=True, methods=["post"], url_path="emettre")
    @transaction.atomic
    def emettre(self, request, pk=None):
        return self._transition(request, BordereauDechet.Statut.EMIS, (BordereauDechet.Statut.EN_ATTENTE,))

    @action(detail=True, methods=["post"], url_path="traiter")
    @transaction.atomic
    def traiter(self, request, pk=None):
        return self._transition(request, BordereauDechet.Statut.TRAITE, (BordereauDechet.Statut.EMIS,))

    def perform_update(self, serializer):
        """BSD traité / valorisé : bordereau scellé et archivé en GED (conservation 10 ans, CDC M7 §9.5)."""
        avant = serializer.instance.statut
        bsd = serializer.save()
        if bsd.statut == BordereauDechet.Statut.TRAITE and avant != BordereauDechet.Statut.TRAITE:
            self._archiver(bsd)

    def _archiver(self, bsd):
        if not bsd.document_id:
            from .services import TYPE_GED_BSD, archiver_ged, bsd_pdf

            bsd.document = archiver_ged(
                bsd_pdf(bsd), f"{bsd.code}.pdf", f"BSD {bsd.code} — {bsd.get_type_dechet_display()}", TYPE_GED_BSD,
                "Bordereaux de suivi des déchets", bsd.code, "hse.bordereaudechet", bsd.pk, self.request.user,
                mots=("hse", "bsd", bsd.code),
            )
            bsd.save(update_fields=["document"])

    def perform_destroy(self, instance):
        if instance.document_id:
            raise serializers.ValidationError({"detail": "BSD archivé : conservé 10 ans, suppression interdite."})
        instance.delete()


class ExigenceHabilitationViewSet(viewsets.ModelViewSet):
    queryset = ExigenceHabilitation.objects.all()
    serializer_class = ExigenceHabilitationSerializer
    permission_classes = [CanValidateHse]


class AuditHseViewSet(viewsets.ModelViewSet):
    queryset = AuditHse.objects.all()
    serializer_class = AuditHseSerializer
    search_fields = ("code", "zone",)
    permission_classes = [CanManageHse]

    def get_queryset(self):
        qs = super().get_queryset()
        if statut := self.request.query_params.get("statut"):
            qs = qs.filter(statut=statut)
        return qs

    @action(detail=True, methods=["post"], url_path="realiser")
    @transaction.atomic
    def realiser(self, request, pk=None):
        audit = AuditHse.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if audit.statut != AuditHse.Statut.PLANIFIE:
            return Response({"detail": "Seul un audit planifié peut être réalisé."}, status=status.HTTP_400_BAD_REQUEST)
        from .ecarts_m6m7 import score_checklist

        if audit.reponses_checklist.filter(reponse="en_attente").exists():
            return Response({"detail": "Check-list incomplète : évaluer tous les points avant de réaliser l'audit."},
                            status=status.HTTP_400_BAD_REQUEST)
        brut = request.data.get("score")
        if brut in (None, "") and score_checklist(audit) is not None:
            brut = score_checklist(audit)  # score calculé sur la check-list
        try:
            score = serializers.IntegerField(min_value=0, max_value=100).run_validation(brut)
            jour = serializers.DateField().run_validation(request.data.get("date_realisation") or timezone.localdate())
        except serializers.ValidationError as exc:
            return Response({"detail": exc.detail}, status=status.HTTP_400_BAD_REQUEST)
        audit.score, audit.date_realisation = score, jour
        audit.statut = AuditHse.Statut.REALISE
        audit.realise_par = request.user
        audit.save()
        return Response(self.get_serializer(audit).data)

    @action(detail=True, methods=["post"], url_path="cloturer")
    @transaction.atomic
    def cloturer(self, request, pk=None):
        audit = AuditHse.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if audit.statut != AuditHse.Statut.REALISE:
            return Response({"detail": "Seul un audit réalisé peut être clôturé."}, status=status.HTTP_400_BAD_REQUEST)
        if ecarts := audit.ecarts_ouverts:
            return Response(
                {"detail": f"{len(ecarts)} écart(s) sans action corrective clôturée : clôture impossible."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        audit.statut = AuditHse.Statut.CLOTURE
        audit.cloture_par, audit.cloture_le = request.user, timezone.now()
        audit.save()
        return Response(self.get_serializer(audit).data)

    @action(detail=True, methods=["post"], url_path="appliquer-checklist")
    @transaction.atomic
    def appliquer_checklist(self, request, pk=None):
        """Charge les questions d'un modèle de check-list sur l'audit (une fois par modèle)."""
        from .ecarts_m6m7 import appliquer_checklist
        from .models import ModeleChecklistHse

        audit = AuditHse.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if audit.statut != AuditHse.Statut.PLANIFIE:
            return Response({"detail": "Check-list applicable à un audit planifié seulement."}, status=status.HTTP_400_BAD_REQUEST)
        modele = fk_input(request.data.get("modele"), ModeleChecklistHse.objects.filter(actif=True), "modele")
        if modele is None:
            return Response({"modele": "Modèle de check-list requis."}, status=status.HTTP_400_BAD_REQUEST)
        if audit.reponses_checklist.filter(modele=modele).exists():
            return Response({"detail": "Check-list déjà appliquée à cet audit."}, status=status.HTTP_400_BAD_REQUEST)
        appliquer_checklist(audit, modele)
        return Response(self.get_serializer(audit).data)

    @action(detail=True, methods=["get"], url_path="rapport-pdf")
    def rapport_pdf(self, request, pk=None):
        """Rapport d'audit PDF : en-tête, check-list, constats et actions correctives (trame provisoire)."""
        from .ecarts_m6m7 import rapport_audit_pdf

        audit = self.get_object()
        return _pdf_response(rapport_audit_pdf(audit), f"rapport-audit-{audit.code}.pdf")


class ConstatAuditViewSet(viewsets.ModelViewSet):
    queryset = ConstatAudit.objects.select_related("audit", "action").all()
    serializer_class = ConstatAuditSerializer
    permission_classes = [CanManageHse]

    def get_queryset(self):
        qs = super().get_queryset()
        if audit := self.request.query_params.get("audit"):
            qs = qs.filter(audit_id=audit)
        return qs


class DuerViewSet(viewsets.ModelViewSet):
    queryset = Duer.objects.all()
    serializer_class = DuerSerializer
    search_fields = ("code", "perimetre",)
    permission_classes = [CanValidateHse]

    @action(detail=True, methods=["post"], url_path="approuver")
    @transaction.atomic
    def approuver(self, request, pk=None):
        duer = Duer.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if duer.statut == Duer.Statut.APPROUVE:
            return Response({"detail": "DUER déjà approuvé."}, status=status.HTTP_400_BAD_REQUEST)
        risques = list(duer.risques.all())
        if not risques:
            return Response({"detail": "Aucun risque évalué : approbation impossible."}, status=status.HTTP_400_BAD_REQUEST)
        sans_mesure = [
            r.code for r in risques
            if r.criticite in (EvaluationRisque.Criticite.ELEVEE, EvaluationRisque.Criticite.CRITIQUE)
            and not r.mesure.strip()
        ]
        if sans_mesure:
            return Response(
                {"detail": f"Risque(s) élevé(s)/critique(s) sans mesure de prévention : {', '.join(sans_mesure)}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        duer.statut = Duer.Statut.APPROUVE
        duer.approuve_par, duer.approuve_le = request.user, timezone.now()
        duer.save()
        return Response(self.get_serializer(duer).data)


class PlanUrgenceViewSet(viewsets.ModelViewSet):
    queryset = PlanUrgence.objects.all()
    serializer_class = PlanUrgenceSerializer
    search_fields = ("code", "intitule",)
    permission_classes = [CanManageHse]

    def list(self, request, *args, **kwargs):
        # `en_retard` dépend des exercices : filtre calculé en Python (volume faible : quelques plans par site).
        if request.query_params.get("en_retard") == "1":
            plans = [p for p in self.filter_queryset(self.get_queryset()) if p.en_retard]
            page = self.paginate_queryset(plans)
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return super().list(request, *args, **kwargs)


class ExerciceUrgenceViewSet(viewsets.ModelViewSet):
    queryset = ExerciceUrgence.objects.select_related("plan").all()
    serializer_class = ExerciceUrgenceSerializer
    permission_classes = [CanManageHse]

    def get_queryset(self):
        qs = super().get_queryset()
        if plan := self.request.query_params.get("plan"):
            qs = qs.filter(plan_id=plan)
        return qs


HSE_SANTE_ROLES = (
    User.Role.ADMIN, User.Role.HSE, User.Role.RH, User.Role.PDG, User.Role.DGA, User.Role.DIRECTION,
    User.Role.DIRECTEUR_OPERATIONS,
)


class CanAptitude(BasePermission):
    """Données d'aptitude médicale : HSE, RH et direction seulement (lecture comme écriture)."""

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and (u.is_staff or u.role in HSE_SANTE_ROLES))


class AptitudeMedicaleViewSet(viewsets.ModelViewSet):
    queryset = AptitudeMedicale.objects.select_related("employe").all()
    serializer_class = AptitudeMedicaleSerializer
    permission_classes = [CanAptitude]

    def get_queryset(self):
        qs = super().get_queryset()
        if employe := self.request.query_params.get("employe"):
            qs = qs.filter(employe_id=employe)
        return qs


class PersonnelHseViewSet(viewsets.ReadOnlyModelViewSet):
    """Annuaire minimal du personnel (identité seulement) pour les saisies HSE : EPI, formations, aptitudes."""

    queryset = Employe.objects.all().order_by("nom", "prenom")
    serializer_class = PersonnelHseSerializer
    permission_classes = [CanManageHse]
    search_fields = ("code", "nom", "prenom")

    @action(detail=True, methods=["get"], url_path="passeport")
    def passeport(self, request, pk=None):
        """Passeport sécurité du salarié (formations, habilitations, aptitude, EPI) ; `?export=pdf`."""
        from django.http import HttpResponse

        from .services import passeport_pdf, passeport_securite

        employe = self.get_object()
        if request.query_params.get("export") == "pdf":
            reponse = HttpResponse(passeport_pdf(employe), content_type="application/pdf")
            reponse["Content-Disposition"] = f'inline; filename="passeport-securite-{employe.code}.pdf"'
            return reponse
        donnees = passeport_securite(employe)
        if not CanAptitude().has_permission(request, self):
            donnees["aptitude"] = None  # secret médical : seulement HSE, RH, direction
        return Response(donnees)


class ParametreHseViewSet(viewsets.ModelViewSet):
    queryset = ParametreHse.objects.all()
    serializer_class = ParametreHseSerializer
    permission_classes = [CanManageHse]
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_queryset(self):
        from .services import PARAMETRES_HSE_DEFAUT, get_param_hse

        for code in PARAMETRES_HSE_DEFAUT:
            get_param_hse(code)
        return super().get_queryset()

    def create(self, request, *args, **kwargs):
        return Response({"detail": "Paramètres prédéfinis : modification seulement."}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @action(detail=True, methods=["post"], url_path="confirmer")
    def confirmer(self, request, pk=None):
        if not can_validate_hse(request.user):
            return Response({"detail": "Confirmation réservée au HSE et à la hiérarchie."}, status=status.HTTP_403_FORBIDDEN)
        p = self.get_object()
        p.statut_valeur = ParametreHse.StatutValeur.CONFIRME
        p.confirme_par = request.user
        p.confirme_le = timezone.now()
        p.save(update_fields=["statut_valeur", "confirme_par", "confirme_le"])
        return Response(self.get_serializer(p).data)


def _annee(request):
    from rest_framework.fields import IntegerField

    brut = request.query_params.get("annee")
    if brut in (None, ""):
        return timezone.localdate().year
    return IntegerField(min_value=2000, max_value=2100).run_validation(brut)


def _pdf_response(contenu, nom):
    from django.http import HttpResponse

    reponse = HttpResponse(contenu, content_type="application/pdf")
    reponse["Content-Disposition"] = f'inline; filename="{nom}"'
    return reponse


class ConsommationEnvironnementViewSet(viewsets.ModelViewSet):
    """Consommations mensuelles (énergie, carburants, eau) et émissions calculées — ISO 14001 (CDC M7-06)."""

    queryset = ConsommationEnvironnement.objects.all()
    serializer_class = ConsommationEnvironnementSerializer
    permission_classes = [CanManageHse]
    search_fields = ("code", "site")

    def get_queryset(self):
        qs = super().get_queryset()
        if ressource := self.request.query_params.get("ressource"):
            qs = qs.filter(ressource=ressource)
        if self.request.query_params.get("annee"):
            qs = qs.filter(periode__year=_annee(self.request))
        return qs

    def perform_create(self, serializer):
        serializer.save(saisi_par=self.request.user)

    @action(detail=False, methods=["get"], url_path="rapport")
    def rapport(self, request):
        """Rapport environnemental de l'année (`?annee=`) : consommations, émissions, déchets, plans ; `&export=pdf`."""
        from .services import bilan_annuel, bilan_pdf

        annee = _annee(request)
        bilan = bilan_annuel(annee)
        donnees = {k: bilan[k] for k in ("annee", "environnement", "dechets", "plans_reduction")}
        donnees["incidents_environnement"] = bilan["indicateurs"]["incidents_environnement"]
        if request.query_params.get("export") == "pdf":
            return _pdf_response(bilan_pdf(bilan, f"Rapport environnemental {annee}"), f"rapport-environnemental-{annee}.pdf")
        return Response(donnees)


class PlanReductionImpactViewSet(viewsets.ModelViewSet):
    queryset = PlanReductionImpact.objects.all()
    serializer_class = PlanReductionImpactSerializer
    permission_classes = [CanManageHse]
    search_fields = ("code", "objectif")


class RevueDirectionHseViewSet(viewsets.ModelViewSet):
    """Bilan annuel HSE et revue de direction (CDC §9.8) : validée par la hiérarchie, scellée et archivée 10 ans."""

    queryset = RevueDirectionHse.objects.select_related("validee_par").all()
    serializer_class = RevueDirectionHseSerializer
    permission_classes = [CanManageHse]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def perform_create(self, serializer):
        from .services import bilan_annuel

        serializer.save(bilan=bilan_annuel(serializer.validated_data["annee"]))

    def perform_update(self, serializer):
        if serializer.instance.statut == RevueDirectionHse.Statut.VALIDEE:
            raise serializers.ValidationError({"detail": "Revue validée : scellée, non modifiable."})
        serializer.save()

    @action(detail=False, methods=["get"], url_path="bilan")
    def bilan(self, request):
        """Bilan HSE annuel calculé à la volée (`?annee=`), `&export=pdf`."""
        from .services import bilan_annuel, bilan_pdf

        annee = _annee(request)
        bilan = bilan_annuel(annee)
        if request.query_params.get("export") == "pdf":
            return _pdf_response(bilan_pdf(bilan, f"Bilan HSE annuel {annee}"), f"bilan-hse-{annee}.pdf")
        return Response(bilan)

    @action(detail=True, methods=["post"], url_path="actualiser")
    def actualiser(self, request, pk=None):
        from .services import bilan_annuel

        revue = self.get_object()
        if revue.statut == RevueDirectionHse.Statut.VALIDEE:
            return Response({"detail": "Revue validée : bilan figé."}, status=status.HTTP_400_BAD_REQUEST)
        revue.bilan = bilan_annuel(revue.annee)
        revue.save(update_fields=["bilan"])
        return Response(self.get_serializer(revue).data)

    @action(detail=True, methods=["post"], url_path="valider")
    @transaction.atomic
    def valider(self, request, pk=None):
        from .services import TYPE_GED_RAPPORT_HSE, archiver_ged, bilan_pdf

        revue = RevueDirectionHse.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if not can_validate_hse(request.user):
            return Response({"detail": "Réservé au HSE et à la hiérarchie."}, status=status.HTTP_403_FORBIDDEN)
        if revue.statut == RevueDirectionHse.Statut.VALIDEE:
            return Response({"detail": "Revue déjà validée."}, status=status.HTTP_400_BAD_REQUEST)
        manquants = [c for c in ("participants", "conclusions", "decisions") if not getattr(revue, c).strip()]
        if manquants:
            return Response({c: "Obligatoire pour valider la revue." for c in manquants}, status=status.HTTP_400_BAD_REQUEST)
        revue.statut = RevueDirectionHse.Statut.VALIDEE
        revue.validee_par, revue.validee_le = request.user, timezone.now()
        titre = f"Revue de direction HSE {revue.annee}"
        revue.document = archiver_ged(
            bilan_pdf(revue.bilan, titre, revue), f"{revue.code}.pdf", titre, TYPE_GED_RAPPORT_HSE, "Rapports HSE",
            revue.code, "hse.revuedirectionhse", revue.pk, user=request.user, mots=("revue de direction", "bilan HSE"),
        )
        revue.save(update_fields=["statut", "validee_par", "validee_le", "document"])
        return Response(self.get_serializer(revue).data)

    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request, pk=None):
        from .services import bilan_pdf

        revue = self.get_object()
        return _pdf_response(bilan_pdf(revue.bilan, f"Revue de direction HSE {revue.annee}", revue), f"{revue.code}.pdf")
