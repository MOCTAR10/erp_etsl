"""Jeu de données de démonstration M8 — Maintenance & GMAO (idempotent).

⚠️ ASCII-safe pour la console Windows (cp1252) : rester sur des messages
ASCII dans les stdout.write (UnicodeEncodeError), ou lancer avec python -X utf8.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from logistique.models import EquipementParc
from maintenance.models import Actif, Inspection, OrdreTravail
from users.models import User


class Command(BaseCommand):
    help = "Seed demo M8 (maintenance) : actifs, OT, inspections."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seed M8 - Maintenance & GMAO (demo)")

        maint = User.objects.filter(role=User.Role.MAINTENANCE).first()
        if maint is None:
            maint = User.objects.filter(is_superuser=True).first() or User.objects.first()
        if maint is None:
            self.stdout.write("Aucun utilisateur Maintenance - seed interrompu.")
            return

        if Actif.objects.exists():
            self.stdout.write("Deja seed - rien a faire.")
            return

        today = timezone.localdate()

        gr = EquipementParc.objects.filter(is_global_rental=True).first()
        gr_ref = f" (GR {gr.code})" if gr else ""
        actifs = [
            Actif.objects.create(
                designation="Groupe de soudage SMAW 400A" + gr_ref,
                categorie=Actif.Categorie.MACHINE,
                fabricant="Lincoln",
                modele="Vantage-400",
                numero_serie="LN-44921",
                site="Atelier principal",
                date_mise_en_service=today - timedelta(days=700),
                garanti_jusqu=today - timedelta(days=50),
                compteur_type=Actif.Compteur.HEURES,
                compteur_value=1240,
                is_global_rental=bool(gr),
                equipement_gr=gr,
                signe_618=bool(gr),
            ),
            Actif.objects.create(
                designation="Chariot elevateur 3t",
                categorie=Actif.Categorie.ENGIN,
                fabricant="Toyota",
                modele="3F-Series",
                numero_serie="TY-80123",
                site="Depot principal",
                date_mise_en_service=today - timedelta(days=1100),
                compteur_type=Actif.Compteur.HEURES,
                compteur_value=3210,
                statut=Actif.Statut.EN_PANNE,
            ),
            Actif.objects.create(
                designation="Potence lievage line A",
                categorie=Actif.Categorie.LEVAGE,
                fabricant="Magrini",
                modele="MP-2000",
                numero_serie="MG-3318",
                site="Chantier RTC",
                date_mise_en_service=today - timedelta(days=300),
                compteur_type=Actif.Compteur.AUCUN,
                compteur_value=0,
            ),
        ]

        ot_correctif = OrdreTravail.objects.create(
            actif=actifs[1],
            type_ot=OrdreTravail.TypeOT.CORRECTIF,
            priorite=OrdreTravail.Priorite.HAUTE,
            description="Panne hydraulique - fuite verin de levage",
            cause="Joint de verin use",
            demandeur=maint,
            technicien=maint,
            date_demande=today - timedelta(days=2),
            statut=OrdreTravail.Statut.EN_COURS,
            date_debut=timezone.now() - timedelta(hours=4),
            created_by=maint,
        )

        OrdreTravail.objects.create(
            actif=actifs[0],
            type_ot=OrdreTravail.TypeOT.PREVENTIF,
            priorite=OrdreTravail.Priorite.MOYENNE,
            description="Maintenance preventive 500h - vidange + filtration",
            demandeur=maint,
            technicien=maint,
            date_demande=today,
            date_planifiee=today + timedelta(days=6),
            statut=OrdreTravail.Statut.PLANIFIE,
            created_by=maint,
        )

        OrdreTravail.objects.create(
            actif=actifs[2],
            type_ot=OrdreTravail.TypeOT.INSPECTION,
            priorite=OrdreTravail.Priorite.MOYENNE,
            description="Inspection reglementaire annuelle potence",
            demandeur=maint,
            technicien=maint,
            date_demande=today - timedelta(days=30),
            date_planifiee=today - timedelta(days=28),
            date_debut=timezone.now() - timedelta(days=27),
            date_fin=timezone.now() - timedelta(days=27),
            heures_mo=3,
            tarif_horaire=1500,
            cout_pieces=0,
            rapport="Inspection OK, palan desmonte et controle.",
            statut=OrdreTravail.Statut.CLOTURE,
            created_by=maint,
        )

        Inspection.objects.create(
            actif=actifs[2],
            type_inspection=Inspection.TypeInspection.LEVAGE,
            date_inspection=today - timedelta(days=25),
            prochaine_inspection=today + timedelta(days=340),
            organisme="tiers",
            organisme_libelle="Apave Gabon",
            resultat=Inspection.Resultat.CONFORME,
            constat="Aucun defaut constate.",
            intervenant=maint,
            statut=Inspection.Statut.REALISEE,
        )
        Inspection.objects.create(
            actif=actifs[1],
            type_inspection=Inspection.TypeInspection.FONCTIONNELLE,
            date_inspection=today + timedelta(days=10),
            organisme="interne",
            statut=Inspection.Statut.PLANIFIEE,
        )

        self.stdout.write(
            f"OK: {Actif.objects.count()} actifs, {OrdreTravail.objects.count()} OT "
            f"({ot_correctif.code} en cours), {Inspection.objects.count()} inspections."
        )