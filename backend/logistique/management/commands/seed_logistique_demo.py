from django.core.management.base import BaseCommand

from logistique.models import (
    AffectationParc,
    DemandeMobilisation,
    EquipementParc,
    LectureCompteur,
    LocationGR,
)
from referentiels.models import Currency, Partner


class Command(BaseCommand):
    help = "Seed démo module M4 — Logistique ETSL & GLOBAL RENTAL, idempotent."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Réinitialise puis reseed")

    def handle(self, *args, **options):
        if options["force"]:
            for model in (LectureCompteur, LocationGR, AffectationParc,
                          DemandeMobilisation, EquipementParc):
                model.objects.all().delete()

        currency, _ = Currency.objects.get_or_create(
            code="XAF", defaults={"label": "Franc CFA (BEAC)", "symbol": "FCFA", "decimals": 0}
        )

        gr1, _ = Partner.objects.get_or_create(
            code="GR-1000",
            defaults={
                "name": "GLOBAL RENTAL — Parc Gabon",
                "kind": Partner.Kind.FOURNISSEUR,
                "currency": currency,
                "is_global_rental": True,
            },
        )
        gr2, _ = Partner.objects.get_or_create(
            code="GR-2000",
            defaults={
                "name": "GLOBAL RENTAL — PCG / contractant",
                "kind": Partner.Kind.AUTRE,
                "currency": currency,
                "is_global_rental": True,
            },
        )

        eq_grue, created = EquipementParc.objects.get_or_create(
            code="PAR00001",
            defaults={
                "label": "Grue de levage 25 t",
                "registration": "GR-25T-001",
                "categorie": EquipementParc.Categorie.LEVAGE,
                "statut": EquipementParc.Statut.DISPONIBLE,
                "compteur_type": EquipementParc.Compteur.HEURES,
                "compteur_value": 1250,
                "site": "Base Libreville",
                "is_global_rental": True,
                "proprietaire": gr1,
                "signe_618": True,
            },
        )
        if created:
            eq_grue.compteur_value = 1250
            eq_grue.save(update_fields=["compteur_value"])

        eq_camion, _ = EquipementParc.objects.get_or_create(
            code="PAR00002",
            defaults={
                "label": "Camion benne 20 t",
                "registration": "ET-2034-CB",
                "categorie": EquipementParc.Categorie.TRANSPORT,
                "statut": EquipementParc.Statut.DISPONIBLE,
                "compteur_type": EquipementParc.Compteur.KM,
                "compteur_value": 68_500,
                "site": "Dépôt Port-Gentil",
                "is_global_rental": False,
                "signe_618": False,
            },
        )

        eq_gr, _ = EquipementParc.objects.get_or_create(
            code="PAR00009",
            defaults={
                "label": "Chargeuse 950 (rétrocédée GR)",
                "registration": "GR-LOAD-950",
                "categorie": EquipementParc.Categorie.ENGIN,
                "statut": EquipementParc.Statut.DISPONIBLE,
                "compteur_type": EquipementParc.Compteur.HEURES,
                "compteur_value": 840,
                "site": "Base Libreville",
                "is_global_rental": True,
                "proprietaire": gr2,
                "signe_618": True,
            },
        )

        for code, label, date_debut, statut in [
            ("DEM00001", "Mobilisation grue — base Libreville", "2026-09-01",
             DemandeMobilisation.Statut.SOUMISE),
            ("DEM00002", "Benne hebdomadaire — dépôt Port-Gentil", "2026-09-15",
             DemandeMobilisation.Statut.TRAITEE),
        ]:
            DemandeMobilisation.objects.get_or_create(
                code=code,
                defaults={
                    "label": label,
                    "departement": "Opérations",
                    "date_debut": date_debut,
                    "date_fin": "2026-10-31",
                    "statut": statut,
                },
            )

        AffectationParc.objects.get_or_create(
            code="AFF00001",
            defaults={
                "equipement": eq_camion,
                "demande": DemandeMobilisation.objects.filter(code="DEM00002").first(),
                "date_debut": "2026-09-15",
                "date_fin": "2026-10-15",
                "statut": AffectationParc.Statut.ACTIVE,
            },
        )

        loc, created_loc = LocationGR.objects.get_or_create(
            code="LOC00001",
            defaults={
                "partenaire": gr1,
                "equipement": eq_grue,
                "reference_bc": "BC-2026-0187",
                "reference_gr": "GR-MOB-2026-014",
                "reference_bl": "BL-2026-0331",
                "date_debut": "2026-09-01",
                "date_fin": "2026-12-31",
                "periodicite": LocationGR.Periodicite.HEURE,
                "tarif": 45_000,
                "devise": currency,
                "montant_estime": 12_600_000,
                "lecture_initiale": 1250,
                "statut": LocationGR.Statut.ACTIVE,
                "imputation_618": True,
            },
        )
        if created_loc:
            eq_grue.statut = EquipementParc.Statut.EN_LOCATION
            eq_grue.save(update_fields=["statut"])

        LectureCompteur.objects.get_or_create(
            code="CPT00001",
            defaults={
                "location": loc,
                "date": "2026-09-01",
                "valeur": 1250,
                "type_lecture": LectureCompteur.TypeLecture.INITIALE,
                "source": LectureCompteur.Source.GR,
            },
        )
        LectureCompteur.objects.get_or_create(
            code="CPT00002",
            defaults={
                "location": loc,
                "date": "2026-09-30",
                "valeur": 1286,
                "type_lecture": LectureCompteur.TypeLecture.PERIODIQUE,
                "source": LectureCompteur.Source.SAISIE,
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed M4 OK : parc={EquipementParc.objects.count()} "
                f"demandes={DemandeMobilisation.objects.count()} "
                f"affectations={AffectationParc.objects.count()} "
                f"locations={LocationGR.objects.count()} "
                f"lectures={LectureCompteur.objects.count()}"
            )
        )