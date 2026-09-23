"""Seed M12 — Juridique & GED : courrier, convention, contentieux, caution,
assurance, réunion et dossier intra-groupe GLOBAL RENTAL démo (RF-ERP-B0...B4).
ASCII-safe."""

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from juridique.models import (
    Assurance,
    Caution,
    Contentieux,
    Convention,
    Courrier,
    DossierGlobalRental,
    Reunion,
)
from referentiels.models import Partner


def _today(offset_days=0):
    return timezone.localdate() + timedelta(days=offset_days)


class Command(BaseCommand):
    help = "Seed les données de démonstration du module Juridique & GED (M12)."

    def handle(self, *args, **options):
        # Partenaires (banque / assureur / GR).
        banque, _ = Partner.objects.get_or_create(
            code="BANQUE-01",
            defaults=dict(name="BGFI Bank Gabon", kind="fournisseur", is_global_rental=False),
        )
        assureur, _ = Partner.objects.get_or_create(
            code="ASSUREUR-01",
            defaults=dict(name="AXA Gabon", kind="fournisseur", is_global_rental=False),
        )
        gr, _ = Partner.objects.get_or_create(
            code="GR-01",
            defaults=dict(name="GLOBAL RENTAL", kind="fournisseur", is_global_rental=True),
        )

        # Courrier entrant (bureau d'ordre, §3.3).
        Courrier.objects.get_or_create(
            code="COU00001",
            defaults=dict(
                sens="entrant", type="lettre", objet="Rappel de garantie - chantier Oveng",
                reference="GR-REF-2026-014", tiers=gr, statut="enregistre",
                date_courrier=_today(-5), date_reception=_today(-3),
            ),
        )
        Courrier.objects.get_or_create(
            code="COU00002",
            defaults=dict(
                sens="sortant", type="note", objet="Transmission compte rendu comite",
                reference="ETSL/SG/2026/118", statut="recu", date_courrier=_today(-1),
            ),
        )

        # Convention / contrat (§3.6 / 8.3) — échéance à 75 jours (alerte J-90).
        Convention.objects.get_or_create(
            code="CON00001",
            defaults=dict(
                type="maintenance", titre="Contrat maintenance groupe electrogene",
                partenaire=gr, montant=Decimal("8500000"),
                date_debut=_today(-90), date_fin=_today(75), renouvelable=True,
                statut="signe",
            ),
        )

        # Contentieux (§8.5) ouvert.
        Contentieux.objects.get_or_create(
            code="LIT00001",
            defaults=dict(
                nature="commercial", objet="Litige litigieux paiement - site Libreville",
                partie_adverse="SOCIETE BTP", montant_en_jeu=Decimal("12000000"),
                phase="pre_contentieux", statut="ouvert",
            ),
        )

        # Caution (§8.6) en cours — échéance à 45 jours (alerte J-60/J-30).
        Caution.objects.get_or_create(
            code="CAU00001",
            defaults=dict(
                type="bonne_execution", emetteur=banque,
                beneficiaire="Client Petrolier SA", objet="Bon de commande mise en service",
                montant=Decimal("5000000"), numero_instrument="BR000001",
                date_emission=_today(-60), date_echeance=_today(45), statut="en_cours",
            ),
        )

        # Assurance (§8.6) — échéance à 20 jours (alerte J-30), active.
        Assurance.objects.get_or_create(
            code="ASS00001",
            defaults=dict(
                type="tous_risques", assureur=assureur, numero_police="POL-2026-001",
                prime_annuelle=Decimal("3200000"), date_debut=_today(-340),
                date_echeance=_today(20), objets_couverts="Chantiers ETSL",
                statut="active",
            ),
        )

        # Réunion (§3.7) planifiée.
        Reunion.objects.get_or_create(
            code="REU00001",
            defaults=dict(
                type="comite_direction", objet="Point mensuel affaires & caution",
                date_reunion=timezone.now() + timedelta(days=2), lieu="Siege",
                statut="planifiee",
            ),
        )

        # Dossier intra-groupe GLOBAL RENTAL (§RF-ERP-B4, compte 618).
        DossierGlobalRental.objects.get_or_create(
            code="GRD00001",
            defaults=dict(
                partenaire_gr=gr, objet="Location engins - chantier Port-Gentil",
                montant_estime=Decimal("18000000"), signe_618=True,
                date_debut=_today(), date_fin=_today(120), statut="ouvert",
                references_documents=["BC-00042", "GR-00021", "BL-0033"],
            ),
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Juridique M12 prêt : courriers={Courrier.objects.count()}, "
                f"conventions={Convention.objects.count()}, contentieux={Contentieux.objects.count()}, "
                f"cautions={Caution.objects.count()}, assurances={Assurance.objects.count()}, "
                f"reunions={Reunion.objects.count()}, dossiers-GR={DossierGlobalRental.objects.count()}."
            )
        )