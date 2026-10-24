"""Vitrine — achats (M2) et dépenses (M10) : demandes d'achat, bons de commande imputés aux affaires, réceptions
(contrôle qualité M6 puis entrée en stock M5), factures rapprochées 3-way et comptabilisées (618 pour GLOBAL RENTAL),
règlements fournisseurs ; engagements de frais généraux visés puis payés.

Tout passe par l'API réelle (comptes démo logistique / qualité / finance / PDG), dates métier passées en paramètre.
"""

from datetime import timedelta
from decimal import Decimal

from django.db import transaction

from achats.models import GoodsReceipt, PurchaseInvoice, PurchaseOrder, PurchaseRequest
from comptabilite.models import Engagement, Paiement
from qualite.models import ControleQualite
from referentiels.models import Account, Article, Partner
from stocks.models import Depot

from .donnees import ACHATS_TYPES, PAQUETS_AFFAIRE
from .outils import MOIS, alea, antidater, arrondi, dater_documents, debut_mois, instant, jour_du_mois, ouvre, saison

LOG, QA, FIN, PDG = "logistique@etls.local", "qaqc@etls.local", "finance@etls.local", "pdg@etls.local"
NOTE = "Vitrine achat "  # marqueur d'idempotence posé dans `notes` du BC
# Part du chiffre d'affaires mensuel d'une affaire achetée à l'extérieur (matière, sous-traitance, intérim) et part
# du loyer GLOBAL RENTAL refacturé au client qui revient à GLOBAL RENTAL (618) : marges crédibles (~20-30 %).
PART_ACHATS = Decimal("0.52")
PART_GR = Decimal("0.68")

# Frais généraux mensuels (engagement visé puis payé) : (objet, compte, fournisseur, montant de base, périodicité)
FRAIS = [
    ("Entretien des véhicules et engins de liaison", "624000", "FRN-206", 2_600_000, 1),
    ("Maintenance informatique et réseaux", "624000", "FRN-213", 1_150_000, 1),
    ("Frais et commissions bancaires", "631000", None, 420_000, 1),
    ("Taxes et redevances (patente, taxe foncière)", "641000", None, 7_800_000, 3),
]


def _mensuel(affaire):
    return affaire.contract_amount / max(1, round((affaire.end_date - affaire.start_date).days / 30.4))


class VitrineAchats:
    def achats(self):
        self.depots = [Depot.objects.filter(code=c).first() for c in ("DEP-PGN", "DEP-LBV")]
        self.depots = [d for d in self.depots if d] or [Depot.objects.order_by("code").first()]
        fin_agrement = self.today + timedelta(days=330)
        # Agréments qualité / HSE des fournisseurs achetés (un BC vers un fournisseur non agréé est refusé, M2 §5.8).
        codes = {f for f, _, _ in ACHATS_TYPES} | {f for f, _ in PAQUETS_AFFAIRE}
        Partner.objects.filter(code__in=codes, agree_qualite_jusqu__isnull=True).update(
            agree_qualite_jusqu=fin_agrement, agree_hse_jusqu=fin_agrement)
        codes_articles = [c for _, paquet in PAQUETS_AFFAIRE for c, _ in paquet] + [c for _, c, _ in ACHATS_TYPES]
        articles = {a.code: a for a in Article.objects.filter(code__in=codes_articles + ["SRV-LOC-GR"])}
        affaires = list(self.affaires_vitrine.values())
        for k in range(MOIS - 1, -1, -1):
            mois = debut_mois(self.today, k)
            actives = [a for a in affaires if a.start_date <= mois.replace(day=28) and a.end_date >= mois]
            r = alea(f"achats-{mois}")
            for n, affaire in enumerate(actives):
                if affaire.is_global_rental:
                    # Location intra-groupe GLOBAL RENTAL : part du loyer refacturé au client, imputée au 618.
                    lignes = [(articles["SRV-LOC-GR"], 1, Decimal(arrondi(_mensuel(affaire) * PART_GR)))]
                    self._achat(f"{mois:%Y-%m}-GR-{affaire.code}", k, n, "GR-0001", lignes, affaire)
                    continue
                fournisseur, paquet = PAQUETS_AFFAIRE[(k + n) % len(PAQUETS_AFFAIRE)]
                budget = _mensuel(affaire) * PART_ACHATS * saison(self.today, k) * Decimal(r.choice(("0.85", "1", "1.1")))
                lignes = []
                for code, part in paquet:
                    article = articles[code]
                    quantite = max(1, int(budget * Decimal(part) / article.purchase_price))
                    lignes.append((article, quantite, article.purchase_price))
                self._achat(f"{mois:%Y-%m}-{affaire.code}", k, n, fournisseur, lignes, affaire)
            standards = [a for a in actives if not a.is_global_rental]
            for n, (fournisseur, code, quantite) in enumerate(r.sample(ACHATS_TYPES, 2)):
                if standards:
                    qte = max(1, int(quantite * saison(self.today, k)))
                    self._achat(f"{mois:%Y-%m}-F{n}", k, n + 5, fournisseur,
                                [(articles[code], qte, articles[code].purchase_price)], standards[(n + k) % len(standards)])
        self._demandes_achat(affaires)

    def _achat(self, tag, k, n, code_fournisseur, lignes, affaire):
        """BC -> confirmation -> réception (CQ M6, entrée en stock M5) -> facture 3-way -> comptabilisation -> règlement."""
        note = f"{NOTE}{tag}"
        if PurchaseOrder.objects.filter(notes=note).exists():
            return
        fournisseur = Partner.objects.get(code=code_fournisseur)
        commande = ouvre(jour_du_mois(self.today, k, 2 + (5 * n) % 20))
        reception = min(commande + timedelta(days=8), self.today - timedelta(days=1))
        facture_le = min(reception + timedelta(days=4), self.today - timedelta(days=1))
        gr = fournisseur.is_global_rental
        # Mois courant : un BC encore en brouillon, un confirmé en attente de livraison, les autres reçus non facturés.
        jusqu_a = "paye" if k >= 2 else ("comptabilise" if k == 1 else ("brouillon", "confirme", "recu", "recu")[n % 4])
        with transaction.atomic(), dater_documents(reception):
            bc = PurchaseOrder.objects.get(pk=self.call(LOG, "post", "/api/achats/orders/", {
                "supplier": str(fournisseur.pk), "order_date": str(commande), "expected_date": str(commande + timedelta(days=10)),
                "is_global_rental": gr, "notes": note, "affaire": str(affaire.pk),
                **({"analytic": str(affaire.analytic_id)} if affaire.analytic_id else {}),
            })["id"])
            antidater(PurchaseOrder, bc.pk, created_at=instant(commande))
            postes = []
            for article, quantite, prix in lignes:
                ligne = self.call(LOG, "post", "/api/achats/order-lines/", {
                    "purchase_order": str(bc.pk), "article": str(article.pk), "label": article.label,
                    "quantity": quantite, "unit_price": str(prix),
                })
                postes.append((article, quantite, prix, ligne["id"]))
            if jusqu_a == "brouillon":
                return
            self.call(LOG, "post", f"/api/achats/orders/{bc.pk}/confirmer/")
            if jusqu_a == "confirme":
                return
            br = self.call(LOG, "post", "/api/achats/receipts/", {"purchase_order": str(bc.pk), "received_at": str(reception)})
            for i, (article, quantite, prix, ligne) in enumerate(postes):
                tracabilite = {}
                if article.is_stockable and article.article_type in ("matiere", "produit"):
                    # Matière tracée : n° de lot, de coulée et certificat MTC saisis à la réception -> lot + certificat M5.
                    tracabilite = {
                        "numero_lot": f"L{reception:%y%m%d}-{n + 1}{i}",
                        "numero_coulee": f"C{alea(tag + str(i)).randint(10000, 99999)}", "certificat_type": "mtc",
                        "numero_certificat": f"MTC-{fournisseur.code[-3:]}-{reception:%y%m}{n}{i}",
                        "organisme_certificat": fournisseur.name,
                    }
                self.call(LOG, "post", "/api/achats/receipt-lines/", {
                    "receipt": br["id"], "purchase_order_line": ligne, "quantity": quantite, **tracabilite,
                })
            ctrl = ControleQualite.objects.filter(reception_id=br["id"]).first()
            if ctrl is not None:
                self.call(QA, "patch", f"/api/qualite/controles/{ctrl.pk}/", {"statut": "valide", "resultat": "conforme"})
                antidater(ControleQualite, ctrl.pk, created_at=instant(reception, 11), date_controle=reception)
            depot = self.depots[n % len(self.depots)]
            self.call(LOG, "post", f"/api/achats/receipts/{br['id']}/valider/", {"depot": str(depot.pk)})
            antidater(GoodsReceipt, br["id"], received_at=reception, created_at=instant(reception, 10))
            self._dater_mouvements(bc, reception)
            self._valider_certificats(br["id"], reception, attente=k == 0 and n % 2 == 1)
            if jusqu_a == "recu":
                return
            inv = self.call(LOG, "post", "/api/achats/invoices/", {
                "purchase_order": str(bc.pk), "supplier": str(fournisseur.pk),
                "invoice_ref": f"F{fournisseur.code[-3:]}-{facture_le:%y%m}-{100 + n}", "invoice_date": str(facture_le),
            })
            for article, quantite, prix, ligne in postes:
                self.call(LOG, "post", "/api/achats/invoice-lines/", {
                    "invoice": inv["id"], "purchase_order_line": ligne, "quantity": quantite, "unit_price": str(prix),
                })
            self.call(FIN, "post", f"/api/achats/invoices/{inv['id']}/rapprocher/")
            self.call(FIN, "post", f"/api/achats/invoices/{inv['id']}/comptabiliser/")
            antidater(PurchaseInvoice, inv["id"], created_at=instant(facture_le, 14))
            facture = PurchaseInvoice.objects.get(pk=inv["id"])
            reglement = facture_le + timedelta(days=30 + alea(tag).randint(0, 20))
            if jusqu_a == "paye" and reglement < self.today:
                data = self.call(FIN, "post", "/api/comptabilite/paiements/", {
                    "sens": "sortie", "mode": "virement", "montant": str(facture.total_ttc), "date": str(reglement),
                    "compte_bancaire": str(self.banque.pk), "tiers": str(fournisseur.pk), "facture": str(facture.pk),
                })
                self.call(FIN, "post", f"/api/comptabilite/paiements/{data['id']}/comptabiliser/")
                antidater(Paiement, data["id"], created_at=instant(reglement, 9))

    def _valider_certificats(self, reception_id, jour, attente=False):
        """Certificats matière (MTC) saisis à la réception validés conformes par QA/QC : le lot peut sortir du stock."""
        from stocks.models import CertificatMatiere

        for cert in CertificatMatiere.objects.filter(lot__lignes_reception__receipt_id=reception_id, date_validation__isnull=True):
            if attente:  # dernière réception du mois courant : certificat encore à valider (lot non consommable)
                continue
            self.call(QA, "post", f"/api/stocks/certificats/{cert.pk}/valider/", {"conforme": True})
            antidater(CertificatMatiere, cert.pk, date_validation=min(jour + timedelta(days=1), self.today))

    @staticmethod
    def _dater_mouvements(bc, jour):
        """Entrées en stock datées du jour de réception (le mouvement est créé à la validation)."""
        from stocks.models import MouvementStock

        refs = [bc.code] + list(bc.receipts.values_list("code", flat=True))
        for ref in refs:
            MouvementStock.objects.filter(document_reference__icontains=ref).update(date=jour)

    def _demandes_achat(self, affaires):
        """Quelques demandes d'achat récentes (besoins chantier) en attente de traitement."""
        besoins = [
            ("Tubes et accessoires pour reprise de ligne", "TUB-API5L-6", 60),
            ("Consommables de soudage TIG", "FIL-ER70S", 12),
            ("EPI pour renfort d'équipe", "EPI-SOUD", 8),
            ("Vannes de sectionnement 4 pouces", "VAN-BS-4", 2),
            ("Peinture de finition époxy", "PEI-EPOXY", 4),
        ]
        actives = [a for a in affaires if a.status == "en_cours" and not a.is_global_rental] or affaires
        for i, (objet, code_article, quantite) in enumerate(besoins):
            if PurchaseRequest.objects.filter(title=objet).exists():
                continue
            article = Article.objects.get(code=code_article)
            data = self.call(LOG, "post", "/api/achats/requests/", {
                "title": objet, "department": "Chantiers", "is_urgent": i == 3,
                "expected_date": str(self.today + timedelta(days=10 + 3 * i)),
                "affaire": str(actives[i % len(actives)].pk),
            })
            self.call(LOG, "post", "/api/achats/request-lines/", {
                "request": data["id"], "article": str(article.pk), "label": article.label, "quantity": quantite,
                "estimated_price": str(article.purchase_price),
            })
            antidater(PurchaseRequest, data["id"], created_at=instant(self.today - timedelta(days=2 + 4 * i)))

    # -- engagements de frais généraux ------------------------------------------------------------------------
    def engagements(self):
        for k in range(MOIS - 1, -1, -1):
            for n, (objet, compte, fournisseur, base, periodicite) in enumerate(FRAIS):
                mois = debut_mois(self.today, k)
                if mois.month % periodicite:
                    continue
                libelle = f"{objet} - {mois:%m/%Y}"
                if Engagement.objects.filter(objet=libelle).exists():
                    continue
                montant = arrondi(Decimal(base) * (Decimal("0.9") + Decimal(alea(libelle).randint(0, 20)) / 100))
                quand = ouvre(jour_du_mois(self.today, k, 5 + 2 * n))
                # Mois courant : un engagement à viser, un visé non réglé (décaissement prévisionnel), le reste réglé.
                cible = "paye" if k >= 1 else ("soumis", "approuve", "approuve", "brouillon")[n % 4]
                with transaction.atomic():
                    self._engagement(libelle, compte, fournisseur, montant, quand, cible)

    def _engagement(self, libelle, compte, fournisseur, montant, quand, cible):
        data = self.call(FIN, "post", "/api/comptabilite/engagements/", {
            "objet": libelle, "montant": str(montant), "compte_depense": str(Account.objects.get(code=compte).pk),
            "date_engagement": str(quand), **({"fournisseur": str(Partner.objects.get(code=fournisseur).pk)} if fournisseur else {}),
        })
        antidater(Engagement, data["id"], created_at=instant(quand))
        if cible == "brouillon":
            return
        self.call(FIN, "post", f"/api/comptabilite/engagements/{data['id']}/soumettre/")
        if cible == "soumis":
            return
        self.call(PDG, "post", f"/api/comptabilite/engagements/{data['id']}/approuver/")
        if cible != "paye":
            return
        reglement = min(quand + timedelta(days=12), self.today - timedelta(days=1))
        paiement = self.call(FIN, "post", "/api/comptabilite/paiements/", {
            "sens": "sortie", "mode": "virement", "montant": str(montant), "date": str(reglement),
            "compte_bancaire": str(self.banque.pk), "engagement": data["id"],
            **({"tiers": str(Partner.objects.get(code=fournisseur).pk)} if fournisseur else {}),
        })
        self.call(FIN, "post", f"/api/comptabilite/paiements/{paiement['id']}/comptabiliser/")
        antidater(Paiement, paiement["id"], created_at=instant(reglement, 9))
