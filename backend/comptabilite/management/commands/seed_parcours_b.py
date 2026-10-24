"""Lot B du seed « parcours démo » : situations -> facture M10 -> encaissement -> lettrage ; achats M2 (dont GR / 618) ;
litiges fournisseurs ; inventaire tournant M5.

Même méthode que le lot A : le workflow est piloté par l'API réelle (APIClient authentifié comme les comptes démo).
À lancer APRÈS `seed_parcours_demo` (il réutilise l'affaire chantier du lot A). Idempotent : repérage par libellé / note.
Toutes les valeurs sont des DONNÉES DE DÉMONSTRATION. ASCII-safe en sortie.
"""

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone

from accounting_kernel.models import AccountMoveLine
from achats.models import LitigeFournisseur, PurchaseOrder
from comptabilite.models import CompteBancaire, FactureClient, Paiement
from commercial.management.commands.seed_parcours_demo import PREFIXE, Command as ParcoursA
from commercial.models import Affaire
from operations.models import SituationTravaux
from qualite.models import ControleQualite
from referentiels.models import Account, Article, Partner
from stocks.models import InventaireLigne, PlanInventaireTournant, StockQuant

NOTE = PREFIXE  # marqueur d'idempotence posé dans `notes` des BC
TVA = Decimal("1.18")


class Command(ParcoursA):
    help = "Seed parcours demo lot B : situations -> facture -> encaissement -> lettrage, achats M2, litiges, inventaire tournant."

    def handle(self, *args, **options):
        with override_settings(ALLOWED_HOSTS=["testserver", "localhost"]):
            self._run()

    def _run(self):
        from analytics.vitrine.nettoyage import renommer_libelles_herites
        from users.management.commands.seed_all_demo import _sync_sequences

        _sync_sequences()
        renommer_libelles_herites()  # bases chargées avec les anciens libellés « (demo) » / sans accents
        self.clients = {}
        self.today = timezone.localdate()
        # 411 doit être lettrable (sinon le lettrage client est refusé) : paramétrage de référence, pas une donnée.
        Account.objects.filter(code__in=["411000", "411100", "401000", "401100"]).update(reconcile=True)
        self.parcours_situations()
        self.parcours_achats()
        self.parcours_inventaire()
        self.stdout.write(self.style.SUCCESS("Parcours lot B pret."))

    # -- M3 -> M10 : situations, facture, encaissement, lettrage ---------------------------------------------
    def _situation(self, affaire, label, montant, avancement, decalage):
        existante = SituationTravaux.objects.filter(affaire=affaire, label=label).first()
        if existante:
            return existante
        debut = self.today - timedelta(days=30 * (decalage + 1))
        data = self.call("atelier@etls.local", "post", "/api/operations/situations/", {
            "affaire": str(affaire.pk), "label": label, "period_start": str(debut),
            "period_end": str(debut + timedelta(days=29)), "amount": montant, "progress": avancement,
            "ordres": [str(o.pk) for o in affaire.ordres_fabrication.all()],
        })
        return SituationTravaux.objects.get(pk=data["id"])

    def _avancer(self, situation, jusqu_a):
        """brouillon -> soumise (créateur) -> validée (tiers)."""
        situation.refresh_from_db()
        if jusqu_a == "brouillon":
            return
        if situation.status == SituationTravaux.Status.BROUILLON:
            self.call("atelier@etls.local", "post", f"/api/operations/situations/{situation.pk}/soumettre/")
        if jusqu_a == "soumise":
            return
        situation.refresh_from_db()
        if situation.status == SituationTravaux.Status.SOUMISE:
            self.call("admin@etls.local", "post", f"/api/operations/situations/{situation.pk}/validate/")

    def parcours_situations(self):
        affaire = Affaire.objects.filter(title=PREFIXE + "Montage tuyauterie chantier").first()
        if affaire is None:
            raise CommandError("Affaire du lot A absente : lancer seed_parcours_demo avant seed_parcours_b.")
        etapes = (
            ("Situation n°1 - installation", 30_000_000, 25, "facturee"),
            ("Situation n°2 - tuyauterie principale", 24_000_000, 50, "validee"),
            ("Situation n°3 - essais", 18_000_000, 70, "soumise"),
            ("Situation n°4 - parachèvement", 12_000_000, 85, "brouillon"),
        )
        for i, (label, montant, avancement, cible) in enumerate(reversed(etapes)):
            situation = self._situation(affaire, label, montant, avancement, i)
            self._avancer(situation, "validee" if cible == "facturee" else cible)
            if cible == "facturee":
                self._facturer_encaisser(situation)

    def _facturer_encaisser(self, situation):
        situation.refresh_from_db()
        facture = FactureClient.objects.filter(situation=situation, nature="facture").first()
        if facture is None:
            data = self.call("finance@etls.local", "post", "/api/comptabilite/factures-clients/depuis-situation/",
                             {"situation": str(situation.pk)})
            facture = FactureClient.objects.get(pk=data["id"])
        if facture.statut == FactureClient.Statut.BROUILLON:
            self.call("finance@etls.local", "post", f"/api/comptabilite/factures-clients/{facture.pk}/emettre/")
            facture.refresh_from_db()
        paiement = Paiement.objects.filter(reference=f"Encaissement {facture.code}").first()
        if paiement is None:
            banque = CompteBancaire.objects.first()
            data = self.call("finance@etls.local", "post", "/api/comptabilite/paiements/", {
                "sens": "entree", "mode": "virement", "montant": str(facture.montant_ttc), "date": str(self.today),
                "compte_bancaire": str(banque.pk), "tiers": str(facture.client_id), "reference": f"Encaissement {facture.code}",
            })
            paiement = Paiement.objects.get(pk=data["id"])
        if paiement.statut == Paiement.Statut.BROUILLON:
            self.call("finance@etls.local", "post", f"/api/comptabilite/paiements/{paiement.pk}/comptabiliser/")
            paiement.refresh_from_db()
        self._lettrer(facture, paiement)

    def _lettrer(self, facture, paiement):
        compte = Account.objects.get(code="411000")
        lignes = AccountMoveLine.objects.filter(account=compte, partner=facture.client).filter(
            move__in=[facture.move, paiement.move]
        )
        if lignes.count() != 2 or lignes.filter(lettrage_actif__isnull=False).exists():
            return
        self.call("finance@etls.local", "post", "/api/comptabilite/lettrages/", {"lignes": [str(l.pk) for l in lignes]})

    # -- M2 : achats -> reception -> facture comptabilisee -> paiement ; litiges ------------------------------
    def _agreer(self, fournisseur):
        """Agrément qualité + HSE de démonstration (un BC vers un fournisseur non agréé est refusé, M2 §5.8)."""
        fin = self.today + timedelta(days=365)
        Partner.objects.filter(pk=fournisseur.pk).update(agree_qualite_jusqu=fin, agree_hse_jusqu=fin)

    def _chaine_achat(self, tag, fournisseur, article, quantite, prix, gr, depot):
        """BC -> confirmation -> réception (contrôle qualité M6) -> facture -> 3-way -> comptabilisation. Retourne le BC."""
        note = f"{NOTE}{tag}"
        bc = PurchaseOrder.objects.filter(notes=note).first()
        if bc is not None:
            return bc
        email = "logistique@etls.local"
        bc = PurchaseOrder.objects.get(pk=self.call(email, "post", "/api/achats/orders/", {
            "supplier": str(fournisseur.pk), "order_date": str(self.today - timedelta(days=20)),
            "expected_date": str(self.today - timedelta(days=5)), "is_global_rental": gr, "notes": note,
        })["id"])
        ligne = self.call(email, "post", "/api/achats/order-lines/", {
            "purchase_order": str(bc.pk), "article": str(article.pk), "label": article.label,
            "quantity": quantite, "unit_price": str(prix),
        })
        self.call(email, "post", f"/api/achats/orders/{bc.pk}/confirmer/")
        br = self.call(email, "post", "/api/achats/receipts/", {"purchase_order": str(bc.pk)})
        self.call(email, "post", "/api/achats/receipt-lines/", {
            "receipt": br["id"], "purchase_order_line": ligne["id"], "quantity": quantite,
        })
        # Le contrôle qualité à réception est créé par la réception ; M6 le valide conforme avant l'entrée en stock.
        ctrl = ControleQualite.objects.get(reception_id=br["id"])
        self.call("qaqc@etls.local", "patch", f"/api/qualite/controles/{ctrl.pk}/", {"statut": "valide", "resultat": "conforme"})
        self.call(email, "post", f"/api/achats/receipts/{br['id']}/valider/", {"depot": str(depot.pk)})
        inv = self.call(email, "post", "/api/achats/invoices/", {
            "purchase_order": str(bc.pk), "supplier": str(fournisseur.pk), "invoice_ref": f"FAC-{tag}-DEMO",
            "invoice_date": str(self.today - timedelta(days=3)),
        })
        self.call(email, "post", "/api/achats/invoice-lines/", {
            "invoice": inv["id"], "purchase_order_line": ligne["id"], "quantity": quantite, "unit_price": str(prix),
        })
        self.call("finance@etls.local", "post", f"/api/achats/invoices/{inv['id']}/rapprocher/")
        self.call("finance@etls.local", "post", f"/api/achats/invoices/{inv['id']}/comptabiliser/")
        return bc

    def _payer_facture(self, bc):
        facture = bc.invoices.first()
        if facture is None or facture.paiements.exists():
            return
        banque = CompteBancaire.objects.first()
        data = self.call("finance@etls.local", "post", "/api/comptabilite/paiements/", {
            "sens": "sortie", "mode": "virement", "montant": str(facture.total_ttc), "date": str(self.today),
            "compte_bancaire": str(banque.pk), "tiers": str(facture.supplier_id), "facture": str(facture.pk),
        })
        self.call("finance@etls.local", "post", f"/api/comptabilite/paiements/{data['id']}/comptabiliser/")

    def _litige(self, bc, type_, description, montant, suite):
        if LitigeFournisseur.objects.filter(purchase_order=bc, description=description).exists():
            return
        email = "logistique@etls.local"
        litige = self.call(email, "post", "/api/achats/litiges/", {
            "purchase_order": str(bc.pk), "type": type_, "description": description, "montant_en_jeu": montant,
        })
        base = f"/api/achats/litiges/{litige['id']}"
        if suite == "escalade":
            self.call(email, "post", f"{base}/relancer/")
            self.call(email, "post", f"{base}/escalader/")
        elif suite == "resolu":
            self.call(email, "post", f"{base}/resoudre/", {"resolution": "Avoir fournisseur obtenu"})
        else:
            self.call(email, "post", f"{base}/relancer/")

    def parcours_achats(self):
        depot = StockQuant.objects.select_related("depot").first().depot
        # TUBE-01 et non « le premier article stockable » : PR-JOINT-VERIN sert de pièce de rechange au seuil de réappro M8 (E2E).
        article = Article.objects.get(code="TUBE-01")
        service = Article.objects.filter(is_stockable=False).order_by("code").first() or article
        standard = Partner.objects.get(code="FOU-001")
        gr = Partner.objects.get(code="GR-0001")
        self._agreer(standard)
        bc_std = self._chaine_achat("Achat matiere", standard, article, 40, Decimal("85000"), False, depot)
        bc_gr = self._chaine_achat("Location GR 618", gr, service, 1, Decimal("12500000"), True, depot)
        self._payer_facture(bc_std)  # la facture GR reste a payer : dette 401100 ouverte
        self._litige(bc_std, "qualite", "Certificats matière non conformes sur 4 pièces", 340000, "escalade")
        self._litige(bc_std, "quantite", "Livraison partielle constatée à la réception", 120000, "ouvert")
        self._litige(bc_gr, "prix", "Écart de tarif de location facturé", 500000, "resolu")

    # -- M5 : inventaire tournant -----------------------------------------------------------------------------
    def parcours_inventaire(self):
        email = "logistique@etls.local"
        depot = StockQuant.objects.select_related("depot").order_by("depot__label").first().depot
        plan = PlanInventaireTournant.objects.filter(depot=depot, actif=True).first()
        if plan is None:
            plan = PlanInventaireTournant.objects.get(pk=self.call(email, "post", "/api/stocks/plans-inventaire/", {
                "depot": str(depot.pk), "periodicite_jours": 30, "articles_par_passage": 5,
                "prochaine_date": str(self.today),
            })["id"])
        if plan.inventaires.exists():
            return
        inv = self.call(email, "post", f"/api/stocks/plans-inventaire/{plan.pk}/generer/")
        for i, ligne in enumerate(InventaireLigne.objects.filter(inventaire_id=inv["id"]).order_by("article__code")):
            # première ligne : écart (-1) constaté au comptage ; les autres conformes au système.
            reel = ligne.quantite_systeme - (1 if i == 0 and ligne.quantite_systeme >= 1 else 0)
            self.call(email, "patch", f"/api/stocks/inventaire-lignes/{ligne.pk}/", {"quantite_reelle": str(reel), "comptee": True})
        self.call(email, "post", f"/api/stocks/inventaires/{inv['id']}/cloturer/")
