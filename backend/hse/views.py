"""Vues API M7 — HSE : Hygiène, Sécurité & Environnement."""

from django.db import transaction
from django.utils import timezone
from integrations.idempotency import idempotent
from config.inputs import date_input, positive_decimal
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
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
        if self.action == "valider":
            return [CanManageHse()]
        return super().get_permissions()

    def perform_create(self, serializer):
        # Le demandeur est toujours l'auteur de la demande : sinon la séparation des tâches (le demandeur ne valide
        # pas son propre permis) se contourne en créant le permis « au nom » d'un collègue.
        serializer.save(demandeur=self.request.user)

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
        if permis.statut not in (PermisTravail.Statut.ACTIF, PermisTravail.Statut.VALIDE):
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
    Notification.objects.bulk_create([
        Notification(user=u, subject=sujet, message=message, kind="escalation")
        for u in User.objects.filter(is_active=True, role__in=[User.Role.PDG, User.Role.DGA])
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
        return Response(indicateurs_frequence(debut, fin, heures))

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
            qs = qs.filter(type_dechet__in=[
                BordereauDechet.TypeDechet.HUILES,
                BordereauDechet.TypeDechet.SOLVANTS,
                BordereauDechet.TypeDechet.BATTERIES,
                BordereauDechet.TypeDechet.PEINTURES,
            ])
        return qs

    def perform_update(self, serializer):
        """BSD traité / valorisé : bordereau scellé et archivé en GED (conservation 10 ans, CDC M7 §9.5)."""
        avant = serializer.instance.statut
        bsd = serializer.save()
        if bsd.statut == BordereauDechet.Statut.TRAITE and avant != BordereauDechet.Statut.TRAITE and not bsd.document_id:
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
        try:
            score = serializers.IntegerField(min_value=0, max_value=100).run_validation(request.data.get("score"))
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
