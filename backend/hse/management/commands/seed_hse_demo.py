"""Jeu de données de démonstration M7 — HSE (idempotent).

⚠️ ASCII-safe pour la console Windows (cp1252) : rester sur des messages
ASCII dans les stdout.write (UnicodeEncodeError), ou lancer avec `python -X utf8`.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from hse.models import (
    ActionHse,
    BordereauDechet,
    Epi,
    EquipementAtex,
    EvaluationRisque,
    FormationSecurite,
    Incident,
    PermisTravail,
)
from users.models import User


class Command(BaseCommand):
    help = "Seed demo M7 (hse) : permis, risques, ATEX, incidents, actions, formations, EPI, BSD."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seed M7 - HSE (demo)")

        hse_user = User.objects.filter(role=User.Role.HSE).first()
        if hse_user is None:
            hse_user = User.objects.filter(is_superuser=True).first() or User.objects.first()
        if hse_user is None:
            self.stdout.write("Aucun utilisateur HSE - seed interrompu.")
            return

        if PermisTravail.objects.exists():
            self.stdout.write("Deja seed - rien a faire.")
            return

        today = timezone.localdate()

        PermisTravail.objects.create(
            type_permis=PermisTravail.TypePermis.CHAUD,
            emplacement="Chantier RTC - zone montage line A",
            description="Soudure SMAW - rattachement piquage 6 pouces",
            mesures="Bache anti-feu, extincteur 2x, vigie incendie",
            demandeur=hse_user,
            validateur=hse_user,
            date_debut=today,
            date_fin=today + timedelta(days=2),
            statut=PermisTravail.Statut.ACTIF,
            date_validation=timezone.now(),
        )
        PermisTravail.objects.create(
            type_permis=PermisTravail.TypePermis.HAUTEUR,
            emplacement="Atelier - echafaudage porte-camion",
            description="Travaux a 6 m - pose garde-corps traversée",
            demandeur=hse_user,
            date_debut=today + timedelta(days=5),
            date_fin=today + timedelta(days=6),
            statut=PermisTravail.Statut.DEMANDE,
        )
        PermisTravail.objects.create(
            type_permis=PermisTravail.TypePermis.ATEX,
            emplacement="Z20 - reservoir de stockage",
            description="Inspection interne zone 1 - sondeur d'ultrasons",
            demandeur=hse_user,
            date_debut=today - timedelta(days=10),
            date_fin=today - timedelta(days=8),
            statut=PermisTravail.Statut.CLOTURE,
            date_validation=timezone.now() - timedelta(days=9),
            date_cloture=timezone.now() - timedelta(days=8),
        )

        EvaluationRisque.objects.create(
            lieux="Z20 - reservoir",
            activite="Travaux a chaud",
            description="Risque d'inflammation des vapeurs d'hydrocarbures",
            probabilite=4,
            gravite=5,
            mesure="Detection gaz + permis chaud + vigie + exclusions ATEX",
            responsable=hse_user,
            statut=EvaluationRisque.Statut.OUVERTE,
        )
        EvaluationRisque.objects.create(
            lieux="Chantier RTC",
            activite="Levage de tiges lourdes",
            description="Chute de charge - manipulation de porte-camions",
            probabilite=3,
            gravite=4,
            mesure="Balizage + calage + formation eperillage",
            responsable=hse_user,
            statut=EvaluationRisque.Statut.TRAITEE,
        )

        today_r = timezone.localdate()
        EquipementAtex.objects.create(
            designation="Scie a eau ATEX Zone 1",
            zone_atex="Zone 1",
            marquage="II 2G Ex h IIB T4 Gb",
            fabricant="SawAtex",
            numero_serie="SA-2024-118",
            certificat="INERIS-241",
            date_expiration_certificat=today_r + timedelta(days=300),
            date_derniere_inspection=today_r - timedelta(days=15),
            prochaine_inspection=today_r + timedelta(days=350),
            statut=EquipementAtex.Statut.DISPONIBLE,
        )
        EquipementAtex.objects.create(
            designation="Projecteur eclair Z1",
            zone_atex="Zone 1",
            marquage="II 2G Ex db IIB T6",
            fabricant="LuxPro",
            numero_serie="LP-7301",
            certificat="LCIE-102",
            date_expiration_certificat=today_r - timedelta(days=5),
            date_derniere_inspection=today_r - timedelta(days=60),
            prochaine_inspection=today_r - timedelta(days=5),
            statut=EquipementAtex.Statut.QUARANTAINE,
        )

        Incident.objects.create(
            type_incident=Incident.TypeIncident.QUASI_ACCIDENT,
            gravite=Incident.Gravite.MINEURE,
            date_evenement=timezone.now() - timedelta(days=30),
            lieu="Depot principal",
            description="Deplacement d'un fardeau de tubes avec equilibre instable",
            cause_immediate="Elingage en retrait",
            cause_profonde="Absence de plan de levage pour la piece",
            consequences="Aucun blessé - near miss declare",
            rapport="Retrait du signalement et re-briefing equipe.",
            statut=Incident.Statut.CLOTURE,
            archive=True,
            declared_by=hse_user,
            enqueteur=hse_user,
            date_ouverture_enquete=timezone.now() - timedelta(days=29),
            date_rapport=today_r - timedelta(days=25),
        )
        incident = Incident.objects.create(
            type_incident=Incident.TypeIncident.POLLUTION,
            gravite=Incident.Gravite.MAJEURE,
            date_evenement=timezone.now() - timedelta(days=3),
            lieu="Aire de lavage",
            description="Deversement d'hydrocarbures hors bassin de retention",
            consequences="Env. 40 L dans le sol - confinement partiel",
            statut=Incident.Statut.EN_ENQUETE,
            declared_by=hse_user,
            enqueteur=hse_user,
            date_ouverture_enquete=timezone.now() - timedelta(days=2),
        )
        ActionHse.objects.create(
            incident=incident,
            type=ActionHse.TypeAction.CORRECTIVE,
            description="Confiner la zone et evacuater le sol pollue via filiere agreee",
            responsable=hse_user,
            echeance=today + timedelta(days=3),
            statut=ActionHse.Statut.EN_COURS,
        )
        ActionHse.objects.create(
            incident=incident,
            type=ActionHse.TypeAction.PREVENTIVE,
            description="Revue de procedure bassin de retention + briefing equipe",
            responsable=hse_user,
            echeance=today + timedelta(days=15),
            statut=ActionHse.Statut.OUVERTE,
        )

        FormationSecurite.objects.create(
            type_session=FormationSecurite.TypeSession.CAUSERIE,
            theme="Causerie securite - manipulations en hauteur",
            formateur="Equipe HSE",
            date_session=today + timedelta(days=4),
            statut=FormationSecurite.Statut.PLANIFIEE,
        )
        FormationSecurite.objects.create(
            type_session=FormationSecurite.TypeSession.FORMATION,
            theme="Formation habilitations electrique / ATEX",
            formateur="CAP ETSL",
            date_session=today - timedelta(days=20),
            duree_heures=6,
            nb_participants=12,
            evalue=True,
            statut=FormationSecurite.Statut.REALISEE,
        )

        benef = User.objects.exclude(pk=hse_user.pk)
        first_benef = benef.order_by("pk").first() or hse_user

        Epi.objects.create(
            type_epi=Epi.TypeEpi.CASQUE,
            designation="Casque ballistique blanc",
            beneficiaire=first_benef,
            date_dotation=today - timedelta(days=120),
            date_renouvellement=today + timedelta(days=10),
            statut=Epi.Statut.EN_USAGE,
        )
        Epi.objects.create(
            type_epi=Epi.TypeEpi.CHAUSSURES,
            designation="Chaussures S3 - pointeur",
            beneficiaire=first_benef,
            date_dotation=today - timedelta(days=200),
            date_renouvellement=today - timedelta(days=20),
            statut=Epi.Statut.EN_USAGE,
        )

        BordereauDechet.objects.create(
            type_dechet=BordereauDechet.TypeDechet.HUILES,
            quantite=120,
            unite=BordereauDechet.Unite.L,
            numero_bsd="BSD-GAB-2026-001",
            date_enlevement=today + timedelta(days=2),
            statut=BordereauDechet.Statut.EMIS,
        )
        BordereauDechet.objects.create(
            type_dechet=BordereauDechet.TypeDechet.METAUX,
            quantite=1.5,
            unite=BordereauDechet.Unite.T,
            destination="Recyclage metaux - Libreville",
            statut=BordereauDechet.Statut.EN_ATTENTE,
        )

        self.stdout.write(
            f"OK: {PermisTravail.objects.count()} permis, {EvaluationRisque.objects.count()} risques, "
            f"{EquipementAtex.objects.count()} ATEX, {Incident.objects.count()} incidents, "
            f"{ActionHse.objects.count()} actions, {FormationSecurite.objects.count()} formations, "
            f"{Epi.objects.count()} EPI, {BordereauDechet.objects.count()} BSD."
        )