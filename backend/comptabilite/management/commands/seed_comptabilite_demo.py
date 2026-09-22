"""Seed M10 — Comptabilité & Trésorerie : TVA 18%, comptes bancaires, relevés,
rapprochement, engagement, paiements et déclaration TVA démo (RF-ERP-90...94).
ASCII-safe."""

from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from accounting_kernel.models import AccountMove
from comptabilite.models import (
    CompteBancaire,
    ControleInterne,
    DeclarationTva,
    Engagement,
    LigneReleve,
    Paiement,
    RapprochementBancaire,
    ReleveBancaire,
    TauxTva,
)
from referentiels.models import Account, Partner


def _account(code):
    return Account.objects.get(code=code)


class Command(BaseCommand):
    help = "Seed les données de démonstration du module Comptabilité & Trésorerie (M10)."

    def handle(self, *args, **options):
        # TVA 18 % (RF-ERP-90).
        tva18, created = TauxTva.objects.get_or_create(
            code="TVA18",
            defaults=dict(
                label="TVA 18 % (Gabon)", taux=Decimal("18.00"),
                compte_collecte=_account("443000"),
                compte_deductible=_account("445000"),
                is_default=True, is_active=True,
            ),
        )
        tva18.is_default = True
        tva18.save(update_fields=["is_default"])

        # Comptes bancaires (RF-ERP-91).
        bq1, _ = CompteBancaire.objects.get_or_create(
            label="BGFI Business",
            defaults=dict(
                banque="BGFI Bank Gabon", numero="BGFI0000000001",
                compte_comptable=_account("512000"), solde_initial=Decimal("25000000"),
            ),
        )
        bq2, _ = CompteBancaire.objects.get_or_create(
            label="UBA Compte exploitation",
            defaults=dict(
                banque="UBA Gabon", numero="UBA0000000002",
                compte_comptable=_account("512000"), solde_initial=Decimal("12000000"),
            ),
        )

        # Partenaire fournisseur (pour paiement sur facture M2).
        fournisseur = Partner.objects.filter(kind__in=["fournisseur", "both"]).first()

        # Engagement de dépense (proc. 4.3) approuvé.
        eng, created = Engagement.objects.get_or_create(
            objet="Carburant atelier Libreville - mois",
            defaults=dict(
                montant=Decimal("2500000"), compte_depense=_account("601000"),
                fournisseur=fournisseur, statut="approuve", date_engagement=date.today(),
            ),
        )

        # Relevé bancaire BGFI avec lignes (import CFONB simplifié).
        releve, created = ReleveBancaire.objects.get_or_create(
            code="REL00001",
            defaults=dict(
                compte_bancaire=bq1, date_debut=date(date.today().year, date.today().month, 1),
                date_fin=date.today(), solde_initial=Decimal("25000000"),
                solde_final=Decimal("22400000"), statut="valide", source="cfonb",
            ),
        )
        if not releve.lignes.exists():
            LigneReleve.objects.create(
                releve=releve, date=releve.date_debut,
                libelle="Virement client ETSL - situ 01", credit=Decimal("2000000"),
            )
            LigneReleve.objects.create(
                releve=releve, date=releve.date_debut,
                libelle="Paiement fournisseur carburant", debit=Decimal("2500000"),
                rapprochee=True,
            )
            LigneReleve.objects.create(
                releve=releve, date=releve.date_fin,
                libelle="Frais bancaires BGFI", debit=Decimal("100000"),
            )

        # Rapprochement partiel.
        rap, created = RapprochementBancaire.objects.get_or_create(
            code="RAP00001",
            defaults=dict(compte_bancaire=bq1, statut="brouillon", notes="Rapprochement BGFI mois"),
        )

        # Paiement fournisseur (proc. 4.5) - brouillon.
        paiement, created = Paiement.objects.get_or_create(
            code="PAI00001",
            defaults=dict(
                sens="sortie", mode="virement", montant=Decimal("1250000"),
                date=date.today(), compte_bancaire=bq1, engagement=eng,
                tiers=fournisseur, statut="brouillon",
            ),
        )
        # Encaisse client lié au relevé.
        encaisse, created = Paiement.objects.get_or_create(
            code="PAI00002",
            defaults=dict(
                sens="entree", mode="virement", montant=Decimal("2000000"),
                date=releve.date_debut, compte_bancaire=bq1, statut="brouillon",
            ),
        )

        # Déclaration TVA du mois en cours.
        decl, created = DeclarationTva.objects.get_or_create(
            mois=date(date.today().year, date.today().month, 1),
            taux_tva=tva18,
            defaults=dict(),
        )

        # Contrôle interne (proc. 4.6).
        controle, created = ControleInterne.objects.get_or_create(
            code="CON00001",
            defaults=dict(
                libelle="Verification rapprochements bancaires du mois",
                reference_procedure="proc. 4.7", statut="planifie",
                date_prevue=date.today(),
            ),
        )

        n = AccountMove.objects.filter(source="M10").count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Compta M10 prêt : TVA {tva18.taux}%, banques={CompteBancaire.objects.count()}, "
                f"releves={ReleveBancaire.objects.count()}, rapprochements={RapprochementBancaire.objects.count()}, "
                f"engagements={Engagement.objects.count()}, paiements={Paiement.objects.count()}, "
                f"TVA=1, controles={ControleInterne.objects.count()}, ecritures M10={n}."
            )
        )