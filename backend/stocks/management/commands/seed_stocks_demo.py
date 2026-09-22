"""Données de démonstration M5 — Stocks & Traçabilité matière.

Idempotent (get_or_create par code). `--force` recrée un mouvement d'écart
d'inventaire pour illustrer l'ajustement et la clôture.
"""

from datetime import date, timedelta

from django.core.management.base import BaseCommand

from referentiels.models import Article, Currency, Partner
from stocks.models import (
    ArticleStock,
    CertificatMatiere,
    Depot,
    Inventaire,
    InventaireLigne,
    LotMatiere,
    MouvementStock,
    StockQuant,
)
from stocks.services import apply_move, cloturer_inventaire

from users.models import User


class Command(BaseCommand):
    help = "Seed de démonstration M5 — Stocks (dépôts, lots, certificats, mouvements, inventaire)."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Re-créer un inventaire d'exemple.")
        parser.add_argument("--flush", action="store_true", help="Purge des données stocks.")

    def handle(self, *args, **options):
        if options["flush"]:
            StockQuant.objects.all().delete()
            InventaireLigne.objects.all().delete()
            Inventaire.objects.all().delete()
            MouvementStock.objects.all().delete()
            CertificatMatiere.objects.all().delete()
            LotMatiere.objects.all().delete()
            ArticleStock.objects.all().delete()
            Depot.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("Données stocks purgées."))
            return

        user = User.objects.filter(role=User.Role.LOGISTIQUE).first() or (
            User.objects.filter(role=User.Role.ADMIN).first()
        )

        deput, _ = Depot.objects.get_or_create(
            code="DEP-LBV",
            defaults={
                "label": "Dépôt central Libreville",
                "site": "Zone Industrielle d'Owendo",
                "responsable": user,
            },
        )
        dep_pg, _ = Depot.objects.get_or_create(
            code="DEP-PGN",
            defaults={"label": "Magasin chantier Port-Gentil", "site": "Port-Gentil"},
        )

        rue, _ = Article.objects.get_or_create(
            code="TUBE-01",
            defaults={
                "label": "Tube acier API 5L Gr.B D=12'' x 12m",
                "article_type": Article.ArticleType.MATIERE,
                "unit": self._get_unit(),
            },
        )
        roupiller, _ = Article.objects.get_or_create(
            code="VANNE-02",
            defaults={
                "label": "Vanne à opercule DN80 PN16",
                "article_type": Article.ArticleType.MATIERE,
                "unit": self._get_unit(),
            },
        )
        ArticleStock.objects.get_or_create(
            article=rue,
            defaults={
                "methode": ArticleStock.Methode.CUMP,
                "seuil_minimal": 10,
                "gestion_lots": True,
            },
        )
        ArticleStock.objects.get_or_create(
            article=roupiller,
            defaults={"methode": ArticleStock.Methode.PP, "prix_standard": 850_000},
        )

        xaf = Currency.objects.filter(code="XAF").first()
        acero = Partner.objects.filter(name__icontains="Acier").first()

        lot = LotMatiere.objects.filter(
            article=rue, numero_lot="MTC-2026-0417"
        ).first()
        if not lot:
            lot = LotMatiere.objects.create(
                code="LOT-TUBE-001",
                article=rue,
                numero_lot="MTC-2026-0417",
                date_reception=date.today() - timedelta(days=20),
                quantite_initiale=120,
                quantite_restante=0,
            )
            self.stdout.write(f"  Lot {lot.code} créé.")

        cert = CertificatMatiere.objects.filter(lot=lot, numero_certificat="MTC-2026-0417").first()
        if not cert:
            cert = CertificatMatiere.objects.create(
                code="CERT-TUBE-001",
                lot=lot,
                type=CertificatMatiere.Type.MTC,
                numero_certificat="MTC-2026-0417",
                fournisseur=acero,
                organisme="Labo SGS Gabon",
                date_emission=date.today() - timedelta(days=18),
                date_validation=date.today() - timedelta(days=15),
                conforme=True,
                notes="Soudabilité conforme, épaisseur nominale vérifiée.",
            )
            self.stdout.write(f"  Certificat {cert.code} créé.")

        mv = MouvementStock.objects.filter(
            lot=lot, document_reference="BC-2026-0061 / BL-2026-0032"
        ).first()
        if not mv:
            mv = MouvementStock.objects.create(
                type_mouvement=MouvementStock.Type.RECEPTION,
                article=rue,
                quantite=120,
                prix_unitaire=45_000,
                devise=xaf,
                destination=deput,
                lot=lot,
                document_reference="BC-2026-0061 / BL-2026-0032",
                date=date.today() - timedelta(days=20),
                created_by=user,
            )
        if not mv.executed:
            apply_move(mv)
            self.stdout.write(f"  Mouvement {mv.code} (réception 120) appliqué.")

        mv2 = MouvementStock.objects.filter(document_reference="TRANSFERT-001").first()
        if not mv2:
            mv2 = MouvementStock.objects.create(
                type_mouvement=MouvementStock.Type.TRANSFERT,
                article=rue,
                quantite=30,
                prix_unitaire=45_000,
                devise=xaf,
                source=deput,
                destination=dep_pg,
                lot=lot,
                document_reference="TRANSFERT-001",
                date=date.today() - timedelta(days=5),
                created_by=user,
            )
            apply_move(mv2)
            self.stdout.write(f"  Mouvement {mv2.code} (transfert 30 vers Port-Gentil) appliqué.")

        if options["force"]:
            inv, created = Inventaire.objects.get_or_create(
                code="INV-DEP-LBV-2026-06",
                defaults={
                    "depot": deput,
                    "date": date.today(),
                    "statut": Inventaire.Statut.BROUILLON,
                    "responsable": user,
                    "created_by": user,
                    "note": "Inventaire périodique du dépôt central.",
                },
            )
            q = StockQuant.objects.filter(depot=deput, article=rue).first()
            systeme = float(q.quantity) if q else 0
            InventaireLigne.objects.get_or_create(
                inventaire=inv,
                article=rue,
                lot=lot,
                defaults={"quantite_systeme": systeme, "quantite_reelle": systeme - 2},
            )
            if inv.statut != Inventaire.Statut.CLOTURE:
                cloturer_inventaire(inv, user)
                self.stdout.write(
                    self.style.SUCCESS(f"  Inventaire {inv.code} clôturé (écart -2 tubes).")
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed M5 OK : {Depot.objects.count()} dépôts, "
                f"{LotMatiere.objects.count()} lots, "
                f"{CertificatMatiere.objects.count()} certificats, "
                f"{MouvementStock.objects.count()} mouvements."
            )
        )

    def _get_unit(self):
        from referentiels.models import UnitOfMeasure

        unit, _ = UnitOfMeasure.objects.get_or_create(
            code="U", defaults={"label": "Unité", "symbol": "u"}
        )
        return unit