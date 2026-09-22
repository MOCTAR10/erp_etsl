"""Seed M9 — RH & Paie : 3 employés, contrats, qualifications, congés, formations,
saisie temps, rubriques de paie et bulletins démo (RF-ERP-80…83). ASCII-safe."""

from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand

from rh_paie.models import (
    BulletinLigne,
    BulletinPaie,
    ContratTravail,
    DemandeRecrutement,
    DemandesConge,
    Employe,
    Formation,
    Qualification,
    RhPaieSequence,
    RubriquePaie,
    SaisieTemps,
    Sanction,
)


def _get_or_create_employe(code, **kwargs):
    return Employe.objects.get_or_create(code=code, defaults=kwargs)[0]


class Command(BaseCommand):
    help = "Seed les données de démonstration du module RH & Paie (M9)."

    def handle(self, *args, **options):
        today = date.today()
        m1 = today.replace(day=1)

        e1 = _get_or_create_employe(
            "EMP00001", civilite="masculin", nom="NGOUA", prenom="Alain",
            date_naissance=date(1985, 3, 12), categorie="cadre",
            fonction="Directeur de projet", departement="Projets",
            site="Libreville", statut="actif", date_embauche=date(2018, 1, 15),
            numero_securite_sociale="CNSS0001234",
        )
        e2 = _get_or_create_employe(
            "EMP00002", civilite="feminin", nom="MBADINGA", prenom="Rachel",
            date_naissance=date(1992, 7, 24), categorie="agent_maitrise",
            fonction="Chef de service qualité", departement="QA/QC",
            site="Libreville", statut="actif", date_embauche=date(2020, 9, 1),
            numero_securite_sociale="CNSS0005678",
        )
        e3 = _get_or_create_employe(
            "EMP00003", civilite="masculin", nom="BOUKANDOU", prenom="Junior",
            date_naissance=date(1996, 11, 3), categorie="ouvrier",
            fonction="Soudeur", departement="Atelier", site="Port-Gentil",
            statut="actif", date_embauche=date(2022, 4, 18),
            numero_securite_sociale="CNSS0009012",
        )

        contrat1, _ = ContratTravail.objects.get_or_create(
            employe=e1,
            date_debut=date(2021, 6, 1),
            defaults=dict(
                type="cdi", salaire_base=1_200_000, lieu_affectation="Libreville",
                statut="actif",
            ),
        )
        contrat2, _ = ContratTravail.objects.get_or_create(
            employe=e2,
            date_debut=date(2022, 10, 1),
            defaults=dict(
                type="cdd", salaire_base=850_000, lieu_affectation="Libreville",
                statut="actif", date_fin=today + timedelta(days=45),
            ),
        )
        ContratTravail.objects.get_or_create(
            employe=e3,
            date_debut=date(2023, 2, 15),
            defaults=dict(
                type="chantier", salaire_base=550_000, lieu_affectation="Port-Gentil",
                statut="actif", date_fin=today + timedelta(days=120),
            ),
        )

        Qualification.objects.get_or_create(
            employe=e3,
            type="habilitation",
            intitule="Habilitation soudure SMAW",
            defaults=dict(
                organisme="Bureau Veritas",
                date_obtention=date(2023, 3, 1),
                date_validite=today + timedelta(days=150),
            ),
        )
        Qualification.objects.get_or_create(
            employe=e2,
            type="certificat",
            intitule="Certification QA/QC ISO 9001",
            defaults=dict(
                organisme="SGS S.A.",
                date_obtention=date(2021, 5, 10),
                date_validite=today - timedelta(days=10),
            ),
        )

        dr, _ = DemandeRecrutement.objects.get_or_create(
            poste="Chef de chantier — Zone industrielle",
            defaults=dict(
                type="remplacement", justification="Départ retraite du titulaire",
                date_souhaitee=today + timedelta(days=60), statut="demande",
            ),
        )
        if dr.statut == "demande":
            dr.statut = "validee"
            dr.save()

        Formation.objects.get_or_create(
            theme="Formation sécurité en hauteur (CHOBOTH)",
            defaults=dict(
                organisme="FormaTec",
                date_session=today + timedelta(days=20),
                type="planifie", duree_heures=8,
            ),
        )

        DemandesConge.objects.get_or_create(
            employe=e2,
            date_debut=today + timedelta(days=10),
            date_fin=today + timedelta(days=24),
            defaults=dict(type="annuel", nb_jours=15, motif="Congé annuel", statut="demande"),
        )
        DemandesConge.objects.get_or_create(
            employe=e1,
            date_debut=today - timedelta(days=15),
            date_fin=today - timedelta(days=5),
            defaults=dict(type="annuel", nb_jours=10, motif="Congé annuel validé", statut="valide"),
        )

        Sanction.objects.get_or_create(
            employe=e3,
            date_constat=today - timedelta(days=20),
            defaults=dict(
                type="avertissement",
                faits="Retard répété sur chantier",
                statut="constate",
            ),
        )

        SaisieTemps.objects.get_or_create(
            employe=e1,
            date=m1,
            defaults=dict(heures=160, type="normal", source="saisie", statut="saisi"),
        )
        SaisieTemps.objects.get_or_create(
            employe=e3,
            date=m1 + timedelta(days=1),
            defaults=dict(heures=12, type="supplementaire", source="rh", statut="saisi"),
        )

        self._seed_rubriques()
        self._seed_bulletins(e1, e2, m1)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed RH&Paie OK : {Employe.objects.count()} employes, "
                f"{ContratTravail.objects.count()} contrats, "
                f"{BulletinPaie.objects.count()} bulletins."
            )
        )

    def _seed_rubriques(self):
        rubriques = [
            ("SAL", "Salaire de base", "gain", "salaire", None, 10),
            ("PAN", "Prime de panier", "gain", "fixe", None, 20),
            ("TRA", "Prime transport", "gain", "fixe", None, 30),
            ("HRS", "Heures supplémentaires", "gain", "brut", 150.0, 40),
            ("CNS", "Cotisation CNSS'", "retenue", "salaire", 5.0, 50),
            ("CMA", "Cotisation CNAMGS", "retenue", "salaire", 2.5, 60),
        ]
        for code, label, nature, base, taux, ordre in rubriques:
            RubriquePaie.objects.get_or_create(
                code=code,
                defaults=dict(label=label, nature=nature, base=base, taux=taux, ordre=ordre),
            )

    def _seed_bulletins(self, e1, e2, m1):
        rub = {r.code: r for r in RubriquePaie.objects.all()}
        for emp, base in ((e1, 1_200_000), (e2, 850_000)):
            bulletin, created = BulletinPaie.objects.get_or_create(
                employe=emp, periode=m1,
                defaults=dict(salaire_base=base, statut="valide"),
            )
            if created:
                BulletinLigne.objects.create(
                    bulletin=bulletin, rubrique=rub["SAL"], libelle=rub["SAL"].label, montant=base
                )
                BulletinLigne.objects.create(
                    bulletin=bulletin, rubrique=rub["PAN"], libelle=rub["PAN"].label, montant=15_000
                )
                cotis = Decimal(str(base)) * Decimal("0.05")
                cotam = Decimal(str(base)) * Decimal("0.025")
                BulletinLigne.objects.create(
                    bulletin=bulletin, rubrique=rub["CNS"], libelle="Cotisation CNSS (5%)",
                    montant=cotis,
                )
                BulletinLigne.objects.create(
                    bulletin=bulletin, rubrique=rub["CMA"], libelle="Cotisation CNAMGS (2,5%)",
                    montant=cotam,
                )
                gains = Decimal(str(base)) + Decimal("15000")
                bulletin.brut = gains
                bulletin.net = gains - cotis - cotam
                bulletin.save()