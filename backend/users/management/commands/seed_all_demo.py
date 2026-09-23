"""Orchestrate toutes les commandes de seed démo, dans l'ordre des dépendances.

Cible des bases de régression (test E2E Playwright, démo). Toutes les commandes
sont idempotentes → rejouable à volonté. ASCII-safe.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand

from achats.models import (
    ConsultationRequest,
    GoodsReceipt,
    PurchaseInvoice,
    PurchaseOrder,
    PurchaseRequest,
)
from achats.models import AchatsSequence
from commercial.models import Affaire, Contract, Estimate, Milestone, Opportunity
from commercial.models import CommercialSequence
from comptabilite.models import (
    CompteBancaire,
    ControleInterne,
    DeclarationTva,
    Engagement,
    Paiement,
    RapprochementBancaire,
    ReleveBancaire,
)
from comptabilite.models import ComptabiliteSequence
from controle_gestion.models import Budget, BudgetRevision, ClotureGestion
from controle_gestion.models import ControleGestionSequence
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
from hse.models import HseSequence
from juridique.models import (
    Assurance,
    Caution,
    Contentieux,
    Convention,
    Courrier,
    DossierGlobalRental,
    Reunion,
)
from juridique.models import JuridiqueSequence
from logistique.models import (
    AffectationParc,
    DemandeMobilisation,
    EquipementParc,
    LectureCompteur,
    LocationGR,
)
from logistique.models import LogistiqueSequence
from maintenance.models import Actif, Inspection, OrdreTravail
from maintenance.models import MaintenanceSequence
from operations.models import (
    GammeOperatoire,
    OrdreFabrication,
    PointageChantier,
    SituationTravaux,
)
from operations.models import OperationsSequence
from qualite.models import (
    ActionCorrective,
    ControleQualite,
    NonConformite,
    PvControle,
    QualificationSoudeur,
    Soudeur,
    WpsWpqr,
)
from qualite.models import QualiteSequence
from rh_paie.models import (
    BulletinPaie,
    ContratTravail,
    DemandesConge,
    DemandeRecrutement,
    Employe,
    Formation,
    Qualification,
    SaisieTemps,
    Sanction,
)
from rh_paie.models import RhPaieSequence
from stocks.models import (
    CertificatMatiere,
    Depot,
    Inventaire,
    LotMatiere,
    MouvementStock,
)
from stocks.models import StocksSequence


SEQUENCE_APPS = [
    # (séquence_modèle, [(kind, prefix, modèle)] ) — codes servis par chaque modèle.
    # Les seeds créent souvent des codes explicites (COU00001, BC00001…) sans avancer
    # les compteurs → resynchronisation obligatoire, sinon le prochain POST API
    # régénère un code déjà pris (UniqueViolation 500). C'est le correctif central.
    (
        AchatsSequence,
        [
            ("DA", "DA", PurchaseRequest),
            ("CONS", "CONS", ConsultationRequest),
            ("BC", "BC", PurchaseOrder),
            ("BL", "BL", GoodsReceipt),
            ("RC", "RC", PurchaseInvoice),
        ],
    ),
    (
        CommercialSequence,
        [
            ("OPP", "OPP", Opportunity),
            ("EST", "EST", Estimate),
            ("AFF", "AFF", Affaire),
            ("MIL", "J", Milestone),
            ("CTT", "CTT", Contract),
        ],
    ),
    (
        ComptabiliteSequence,
        [
            ("BQ", "BQ", CompteBancaire),
            ("REL", "REL", ReleveBancaire),
            ("RAP", "RAP", RapprochementBancaire),
            ("ENG", "ENG", Engagement),
            ("PAI", "PAI", Paiement),
            ("TVA", "TVA", DeclarationTva),
            ("CON", "CON", ControleInterne),
        ],
    ),
    (
        ControleGestionSequence,
        [
            ("BUD", "BUD", Budget),
            ("REV", "REV", BudgetRevision),
            ("CLO", "CLO", ClotureGestion),
        ],
    ),
    (
        HseSequence,
        [
            ("PERM", "PERM", PermisTravail),
            ("EVR", "EVR", EvaluationRisque),
            ("ATX", "ATX", EquipementAtex),
            ("INC", "INC", Incident),
            ("ACT", "ACT", ActionHse),
            ("FOR", "FOR", FormationSecurite),
            ("EPI", "EPI", Epi),
            ("BSD", "BSD", BordereauDechet),
        ],
    ),
    (
        JuridiqueSequence,
        [
            ("COU", "COU", Courrier),
            ("CON", "CON", Convention),
            ("LIT", "LIT", Contentieux),
            ("CAU", "CAU", Caution),
            ("ASS", "ASS", Assurance),
            ("REU", "REU", Reunion),
            ("GRD", "GRD", DossierGlobalRental),
        ],
    ),
    (
        LogistiqueSequence,
        [
            ("PAR", "PAR", EquipementParc),
            ("DEM", "DEM", DemandeMobilisation),
            ("AFF", "AFF", AffectationParc),
            ("LOC", "LOC", LocationGR),
            ("CPT", "CPT", LectureCompteur),
        ],
    ),
    (
        MaintenanceSequence,
        [
            ("EQ", "EQ", Actif),
            ("OT", "OT", OrdreTravail),
            ("INS", "INS", Inspection),
        ],
    ),
    (
        OperationsSequence,
        [
            ("GAM", "GAM", GammeOperatoire),
            ("OF", "OF", OrdreFabrication),
            ("PTS", "PTS", PointageChantier),
            ("SIT", "SIT", SituationTravaux),
        ],
    ),
    (
        QualiteSequence,
        [
            ("SOU", "SOU", Soudeur),
            ("QUAL", "QUAL", QualificationSoudeur),
            ("WPS", "WPS", WpsWpqr),
            ("CTR", "CTR", ControleQualite),
            ("NC", "NC", NonConformite),
            ("CAP", "CAP", ActionCorrective),
            ("PV", "PV", PvControle),
        ],
    ),
    (
        RhPaieSequence,
        [
            ("EMP", "EMP", Employe),
            ("CTR", "CTR", ContratTravail),
            ("SQH", "SQH", Qualification),
            ("REC", "REC", DemandeRecrutement),
            ("FOR", "FOR", Formation),
            ("CON", "CON", DemandesConge),
            ("SAN", "SAN", Sanction),
            ("TMP", "TMP", SaisieTemps),
            ("BUL", "BUL", BulletinPaie),
        ],
    ),
    (
        StocksSequence,
        [
            ("DEP", "DEP", Depot),
            ("LOT", "LOT", LotMatiere),
            ("CERT", "CERT", CertificatMatiere),
            ("MVT", "MVT", MouvementStock),
            ("INV", "INV", Inventaire),
        ],
    ),
]


def _sync_sequences():
    """Réaligne les compteurs de séquence au-delà des derniers codes existants.

    Retourne le nombre de compteurs ajustés. Idempotent et ASCII-safe.
    """
    synced = 0
    for seq_model, kinds in SEQUENCE_APPS:
        for kind, prefix, model in kinds:
            numbers = []
            for code in model.objects.filter(code__startswith=prefix).values_list(
                "code", flat=True
            ):
                suffix = code[len(prefix):]
                if suffix.isdigit() and suffix != "":
                    numbers.append(int(suffix))
            if not numbers:
                continue
            seq, _ = seq_model.objects.get_or_create(
                kind=kind, defaults={"prefix": prefix, "padding": 5}
            )
            if seq.next_number <= max(numbers):
                seq.next_number = max(numbers) + 1
                seq.save(update_fields=["next_number"])
                synced += 1
    return synced

SEED_ORDER = [
    # Référentiels minimaux avant tout (currencies, accounts SYSCOHADA dont 618,
    # partners, articles, axes analytiques) + 270 annexes + users démo.
    "seed_referentiels",
    "seed_annexes",
    "seed_demo_users",
    # Socle GED / workflow / registres (circuits MANUEL, registres par an).
    "seed_document_types",
    "seed_manual_circuits",
    "seed_workflow",
    "seed_registres",
    # Noyau comptable (exercice, périodes, journaux, séquences).
    "seed_accounting",
    # Modules métier M1-M12, dans l'ordre DECOUPAGE (commercial → juridique).
    "seed_commercial_demo",
    "seed_achats_demo",
    "seed_operations_demo",
    "seed_logistique_demo",
    "seed_stocks_demo",
    "seed_qualite_demo",
    "seed_hse_demo",
    "seed_maintenance_demo",
    "seed_rh_paie_demo",
    "seed_comptabilite_demo",
    "seed_controle_gestion_demo",
    "seed_juridique_demo",
]


class Command(BaseCommand):
    """Applique l'ensemble des seeds de démonstration (idempotent, ordonné)."""

    help = "Seeds toutes les données de démonstration (ordre de dépendances, idempotent)."

    def handle(self, *args, **options):
        for cmd in SEED_ORDER:
            self.stdout.write(self.style.MIGRATE_HEADING(f"==> {cmd}"))
            call_command(cmd)
        synced = _sync_sequences()
        self.stdout.write(
            self.style.SUCCESS(
                f"Seed complet terminé ({len(SEED_ORDER)} commandes, "
                f"{synced} séquences réalignées)."
            )
        )