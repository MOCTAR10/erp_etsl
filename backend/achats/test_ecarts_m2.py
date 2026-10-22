"""Écarts M2 (2026-10) — recette par ligne de la matrice CDC.

Agrément fournisseur M6 / M7 et catalogue ; circuit GR (BC ↔ location M4) ; DS et engagement (paramètres provisoires) ;
réception → lot + MTC / CoC (M5) ; ITP / CND à réception (M6) ; affaire → DA (M1) ; conservation GED ; avoirs.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting_kernel.models import AccountMove
from comptabilite.models import TauxTva
from commercial.models import Affaire, Estimate, EstimateLine, Opportunity
from logistique.models import EquipementParc, LocationGR
from qualite.models import ControleQualite
from referentiels.models import Account, Article, Partner, UnitOfMeasure
from stocks.models import ArticleStock, CertificatMatiere, Depot, LotMatiere, MouvementStock
from users.models import User

from .models import (
    AgrementFournisseur,
    AvoirFournisseur,
    GoodsReceipt,
    GoodsReceiptLine,
    LitigeFournisseur,
    ParametreAchats,
    PurchaseInvoice,
    PurchaseInvoiceLine,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseRequest,
    RegleInspectionReception,
)

PWD = "x-Audit-2026"


def creer(email, role):
    return User.objects.create_user(email=email, password=PWD, role=role)


class _Base(APITestCase):
    def setUp(self):
        self.finance = creer("fin@etls.ga", User.Role.FINANCE)
        self.logistique = creer("log@etls.ga", User.Role.LOGISTIQUE)
        self.qaqc = creer("qa@etls.ga", User.Role.QAQC)
        self.hse = creer("hse@etls.ga", User.Role.HSE)
        self.client.force_authenticate(self.finance)
        self.unite, _ = UnitOfMeasure.objects.get_or_create(code="U", defaults={"label": "Unité"})
        self.tube = Article.objects.create(code="TUBE-E", label="Tube", article_type="matiere", unit=self.unite, is_stockable=True)
        self.depot = Depot.objects.create(label="Magasin")
        fin = timezone.localdate() + timedelta(days=200)
        self.fournisseur = Partner.objects.create(
            code="F-E", name="Fournisseur E", kind=Partner.Kind.FOURNISSEUR, agree_qualite_jusqu=fin, agree_hse_jusqu=fin
        )

    def as_(self, user):
        self.client.force_authenticate(user)

    def bc(self, qte=10, prix="100", **kw):
        bc = PurchaseOrder.objects.create(supplier=self.fournisseur, status=PurchaseOrder.Status.CONFIRMEE, **kw)
        ligne = PurchaseOrderLine.objects.create(purchase_order=bc, article=self.tube, label="Tube", quantity=qte, unit_price=Decimal(prix))
        return bc, ligne


class ParametresTests(_Base):
    def test_parametres_provisoires_modifiables_et_confirmables(self):
        r = self.client.get("/api/achats/parametres/")
        self.assertEqual(r.status_code, 200)
        codes = {p["code"]: p for p in r.data["results"]}
        self.assertEqual(set(codes), {"ENGAGEMENT_MESURE", "DS_OBLIGATOIRE_GR", "RETENTION_PIECES_ACHAT_ANS",
                                      "AGREMENT_DUREE_MOIS", "AGREMENT_ALERTE_JOURS"})
        self.assertTrue(all(p["est_provisoire"] for p in codes.values()))
        pid = codes["ENGAGEMENT_MESURE"]["id"]
        self.assertEqual(self.client.patch(f"/api/achats/parametres/{pid}/", {"valeur": "3"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(f"/api/achats/parametres/{pid}/", {"valeur": "2"}, format="json").status_code, 200)
        self.as_(self.logistique)
        self.assertEqual(self.client.post(f"/api/achats/parametres/{pid}/confirmer/").status_code, 403)
        self.as_(self.finance)
        r = self.client.post(f"/api/achats/parametres/{pid}/confirmer/")
        self.assertEqual((r.status_code, r.data["statut_valeur"]), (200, "confirme"))
        self.client.patch(f"/api/achats/parametres/{pid}/", {"valeur": "1"}, format="json")
        self.assertEqual(ParametreAchats.objects.get(pk=pid).statut_valeur, "provisoire")

    def test_engagement_total_commande_ou_reste_a_facturer(self):
        bc, ligne = self.bc()
        PurchaseOrderLine.objects.filter(pk=ligne.pk).update(invoiced_qty=4)
        r = self.client.get("/api/achats/orders/reporting/")
        self.assertEqual((r.data["mesure_engagement"], r.data["engagements"][0]["engage"]), ("reste_a_facturer", "600.00"))
        self.client.get("/api/achats/parametres/")
        ParametreAchats.objects.filter(code="ENGAGEMENT_MESURE").update(valeur=2)
        r = self.client.get("/api/achats/orders/reporting/")
        self.assertEqual((r.data["mesure_engagement"], r.data["engagements"][0]["engage"]), ("total_commande", "1000.00"))
        self.assertTrue(r.data["mesure_provisoire"])


class AgrementTests(_Base):
    def test_agrement_qualite_valide_par_qaqc_reporte_sur_la_fiche(self):
        nouveau = Partner.objects.create(code="F-N", name="Nouveau", kind=Partner.Kind.FOURNISSEUR)
        self.as_(self.logistique)
        r = self.client.post("/api/achats/agrements/", {"fournisseur": nouveau.pk, "domaine": "qualite", "reference": "Audit 12"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        aid = r.data["id"]
        self.as_(self.hse)
        self.assertEqual(self.client.post(f"/api/achats/agrements/{aid}/valider/").status_code, 403)
        self.as_(self.qaqc)
        fin = (timezone.localdate() + timedelta(days=100)).isoformat()
        r = self.client.post(f"/api/achats/agrements/{aid}/valider/", {"date_fin": fin}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        nouveau.refresh_from_db()
        self.assertEqual(nouveau.agree_qualite_jusqu.isoformat(), fin)
        self.assertFalse(nouveau.agrement_valide(timezone.localdate()))  # HSE manquant
        # HSE : sans date de fin saisie, durée paramétrée (12 mois provisoire).
        self.as_(self.hse)
        r = self.client.post("/api/achats/agrements/", {"fournisseur": nouveau.pk, "domaine": "hse"}, format="json")
        r = self.client.post(f"/api/achats/agrements/{r.data['id']}/valider/")
        self.assertEqual(r.status_code, 200, r.content)
        nouveau.refresh_from_db()
        self.assertGreater(nouveau.agree_hse_jusqu, timezone.localdate() + timedelta(days=360))
        self.assertTrue(nouveau.agrement_valide(timezone.localdate()))
        # Décision scellée.
        self.assertEqual(self.client.patch(f"/api/achats/agrements/{aid}/", {"reference": "x"}, format="json").status_code, 400)
        cat = {row["code"]: row for row in self.client.get("/api/achats/agrements/catalogue/").data["rows"]}
        self.assertEqual(cat["F-N"]["etat"], "agree")

    def test_refus_retire_l_agrement_et_bloque_le_bc(self):
        agrement = AgrementFournisseur.objects.create(fournisseur=self.fournisseur, domaine="hse")
        self.as_(self.hse)
        self.assertEqual(self.client.post(f"/api/achats/agrements/{agrement.pk}/refuser/").status_code, 400)
        self.assertEqual(self.client.post(f"/api/achats/agrements/{agrement.pk}/refuser/", {"motif": "Audit HSE KO"}, format="json").status_code, 200)
        self.fournisseur.refresh_from_db()
        self.assertIsNone(self.fournisseur.agree_hse_jusqu)
        bc = PurchaseOrder.objects.create(supplier=self.fournisseur)
        PurchaseOrderLine.objects.create(purchase_order=bc, label="x", quantity=1, unit_price=1)
        self.as_(self.finance)
        self.assertEqual(self.client.post(f"/api/achats/orders/{bc.pk}/confirmer/").status_code, 400)
        cat = {row["code"]: row for row in self.client.get("/api/achats/agrements/catalogue/").data["rows"]}
        self.assertEqual(cat["F-E"]["etat"], "non_agree")


class ReceptionTests(_Base):
    def _reception(self, **ligne):
        bc, po_line = self.bc()
        br = GoodsReceipt.objects.create(purchase_order=bc)
        r = self.client.post("/api/achats/receipt-lines/", {"receipt": str(br.pk), "purchase_order_line": str(po_line.pk),
                                                            "quantity": "10", **ligne}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return br

    def _valider_controles(self, br):
        ControleQualite.objects.filter(reception=br).update(statut="valide", resultat="conforme")

    def _valider(self, br):
        return self.client.post(f"/api/achats/receipts/{br.pk}/valider/", {"depot": str(self.depot.pk)}, format="json")

    def test_regle_matiere_declenche_itp_et_cnd_bloquants(self):
        RegleInspectionReception.objects.create(article_type="matiere", exige_itp=True, exige_cnd=True, methode_cnd="UT")
        br = self._reception()
        types = set(ControleQualite.objects.filter(reception=br).values_list("type_controle", flat=True))
        self.assertEqual(types, {"reception", "itp", "cnd"})
        self.assertEqual(ControleQualite.objects.get(reception=br, type_controle="cnd").methode_cnd, "UT")
        ControleQualite.objects.filter(reception=br, type_controle="reception").update(statut="valide", resultat="conforme")
        r = self._valider(br)
        self.assertEqual(r.status_code, 400)
        self.assertIn("ITP", r.data["detail"])
        self._valider_controles(br)
        self.assertEqual(self._valider(br).status_code, 200)

    def test_sans_regle_pas_d_inspection_et_regle_ajoutee_apres_coup(self):
        br = self._reception()
        self.assertEqual(ControleQualite.objects.filter(reception=br).count(), 1)
        RegleInspectionReception.objects.create(article=self.tube, exige_itp=True)
        self._valider_controles(br)
        r = self._valider(br)
        self.assertEqual(r.status_code, 400)  # l'ITP manquant est créé à la validation
        self.assertTrue(ControleQualite.objects.filter(reception=br, type_controle="itp", statut="en_attente").exists())

    def test_lot_et_certificat_crees_a_la_validation(self):
        br = self._reception(numero_lot="H-778", numero_coulee="C1", certificat_type="mtc", numero_certificat="MTC-55",
                             organisme_certificat="Labo X")
        self._valider_controles(br)
        r = self._valider(br)
        self.assertEqual(r.status_code, 200, r.content)
        lot = LotMatiere.objects.get(numero_lot="H-778")
        self.assertEqual((lot.quantite_initiale, lot.quantite_restante), (Decimal("10"), Decimal("10")))
        cert = CertificatMatiere.objects.get(lot=lot)
        self.assertEqual((cert.type, cert.numero_certificat, cert.fournisseur_id), ("mtc", "MTC-55", self.fournisseur.pk))
        self.assertIsNone(cert.date_validation)  # validation QA/QC en M5
        self.assertEqual(MouvementStock.objects.get(document_reference=br.code).lot_id, lot.pk)
        self.assertEqual(GoodsReceiptLine.objects.get(receipt=br).lot_id, lot.pk)

    def test_certificat_sans_lot_refuse_et_lot_obligatoire(self):
        bc, po_line = self.bc()
        br = GoodsReceipt.objects.create(purchase_order=bc)
        r = self.client.post("/api/achats/receipt-lines/", {"receipt": str(br.pk), "purchase_order_line": str(po_line.pk),
                                                            "quantity": "10", "certificat_type": "coc", "numero_certificat": "C9"},
                             format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("numero_lot", r.data)
        ArticleStock.objects.create(article=self.tube, lot_obligatoire=True)
        br = self._reception()
        self._valider_controles(br)
        r = self._valider(br)
        self.assertEqual(r.status_code, 400)
        self.assertIn("numero_lot", r.data)
        self.assertFalse(MouvementStock.objects.filter(document_reference=br.code).exists())

    def test_reception_et_litige_archives_en_ged_10_ans(self):
        br = self._reception()
        self._valider_controles(br)
        self.assertEqual(self._valider(br).status_code, 200)
        br.refresh_from_db()
        self.assertIsNotNone(br.document_ged)
        self.assertEqual(br.document_ged.type.retention_years, 10)
        self.assertEqual(br.document_ged.status, "archived")
        litige = LitigeFournisseur.objects.create(purchase_order=br.purchase_order, type="qualite", description="Rayures")
        r = self.client.post(f"/api/achats/litiges/{litige.pk}/resoudre/", {"resolution": "Avoir"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        litige.refresh_from_db()
        self.assertIsNotNone(litige.document_ged)
        pieces = {p["piece"] for p in self.client.get("/api/achats/orders/pieces-archivees/").data["rows"]}
        self.assertTrue({br.code, litige.code} <= pieces)


class CircuitAmontTests(_Base):
    def test_bc_confirme_archive_en_ged(self):
        bc = PurchaseOrder.objects.create(supplier=self.fournisseur)
        PurchaseOrderLine.objects.create(purchase_order=bc, label="x", quantity=2, unit_price=50)
        self.assertEqual(self.client.post(f"/api/achats/orders/{bc.pk}/confirmer/").status_code, 200)
        bc.refresh_from_db()
        self.assertEqual(bc.document_ged.reference, bc.code)

    def test_affaire_validee_genere_une_da_preremplie(self):
        service = Article.objects.create(code="SRV-E", label="Prestation", article_type="service", unit=self.unite)
        opp = Opportunity.objects.create(subject="Pipeline")
        offre = Estimate.objects.create(title="Offre", opportunity=opp, status=Estimate.Status.GAGNEE)
        EstimateLine.objects.create(estimate=offre, article=self.tube, label="Tube 6", quantity=12, unit_price=500)
        EstimateLine.objects.create(estimate=offre, article=service, label="Main-d'oeuvre", quantity=1, unit_price=900)
        brouillon = Affaire.objects.create(title="Pas encore", opportunity=opp)
        self.as_(self.logistique)
        self.assertEqual(self.client.post("/api/achats/requests/depuis-affaire/", {"affaire": str(brouillon.pk)}, format="json").status_code, 400)
        affaire = Affaire.objects.create(title="Pipeline Cap Lopez", opportunity=opp, status=Affaire.Status.CONFIRMEE)
        r = self.client.post("/api/achats/requests/depuis-affaire/", {"affaire": str(affaire.pk)}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["lignes_derivees"], 1)
        da = PurchaseRequest.objects.get(pk=r.data["id"])
        affaire.refresh_from_db()
        self.assertEqual((da.affaire_id, da.analytic_id, da.status), (affaire.pk, affaire.analytic_id, "brouillon"))
        self.assertEqual(da.lines.get().article_id, self.tube.pk)
        self.assertEqual(self.client.post("/api/achats/requests/depuis-affaire/", {"affaire": str(affaire.pk)}, format="json").status_code, 400)
        # Le BC issu de la DA hérite de l'affaire.
        PurchaseRequest.objects.filter(pk=da.pk).update(status="approuvee")
        r = self.client.post("/api/achats/orders/", {"supplier": self.fournisseur.pk, "request": str(da.pk)}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["affaire"], affaire.pk)

    def test_regle_unique_affaire_da_m1_et_m2(self):
        """INT-02 / écart E2 : les deux points d'entrée appliquent la même règle (affaire liée, natures achetées)."""
        from achats.ecarts import da_depuis_affaire
        from commercial.ecarts_m1 import generer_besoins_achat

        service = Article.objects.create(code="SRV-U", label="Prestation", article_type="service", unit=self.unite)
        opp = Opportunity.objects.create(subject="Unique")
        offre = Estimate.objects.create(title="Offre", opportunity=opp, status=Estimate.Status.GAGNEE)
        EstimateLine.objects.create(estimate=offre, article=self.tube, label="Tube", quantity=4, unit_price=500)
        EstimateLine.objects.create(estimate=offre, article=service, label="Prestation", quantity=1, unit_price=900)
        EstimateLine.objects.create(estimate=offre, label="Sous-traitance peinture", quantity=1, cout_unitaire=300,
                                    unit_price=400, nature="sous_traitance")
        EstimateLine.objects.create(estimate=offre, label="Soudeurs", quantity=1, unit_price=800, nature="main_oeuvre")
        a1 = Affaire.objects.create(title="Depuis M1", opportunity=opp, status=Affaire.Status.CONFIRMEE)
        a2 = Affaire.objects.create(title="Depuis M2", opportunity=opp, status=Affaire.Status.CONFIRMEE)
        da1 = generer_besoins_achat(a1, self.logistique)
        da2, n = da_depuis_affaire(a2, self.logistique)
        self.assertEqual((da1.affaire_id, da2.affaire_id), (a1.pk, a2.pk))
        libelles = lambda da: sorted(da.lines.values_list("label", flat=True))  # noqa: E731
        self.assertEqual(libelles(da1), libelles(da2))
        self.assertEqual(libelles(da1), ["Sous-traitance peinture", "Tube"])
        self.assertEqual(n, 2)
        self.assertEqual(da1.lines.get(label="Sous-traitance peinture").estimated_price, 300)
        # Une seule DA brouillon par affaire, quel que soit le point d'entrée.
        self.as_(self.logistique)
        r = self.client.post("/api/achats/requests/depuis-affaire/", {"affaire": str(a1.pk)}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_location_gr_genere_le_bc_618_et_ds_parametrable(self):
        gr = Partner.objects.create(code="GR-E", name="Global Rental", kind=Partner.Kind.FOURNISSEUR, is_global_rental=True)
        eq = EquipementParc.objects.create(label="Grue 25 t", categorie="levage")
        loc = LocationGR.objects.create(partenaire=gr, equipement=eq, montant_estime=1_000_000)
        self.as_(self.logistique)
        r = self.client.post("/api/achats/orders/depuis-location-gr/", {"location": str(loc.pk)}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        bc = PurchaseOrder.objects.get(pk=r.data["id"])
        self.assertEqual((bc.is_global_rental, bc.location_gr_id, bc.supplier_id, bc.total), (True, loc.pk, gr.pk, Decimal("1000000")))
        self.assertEqual(self.client.post("/api/achats/orders/depuis-location-gr/", {"location": str(loc.pk)}, format="json").status_code, 400)
        # Un BC lié à la location doit rester GR, chez le partenaire de la location.
        r = self.client.patch(f"/api/achats/orders/{bc.pk}/", {"supplier": self.fournisseur.pk}, format="json")
        self.assertEqual(r.status_code, 400)
        # DS obligatoire si ETSL l'active.
        self.client.get("/api/achats/parametres/")
        ParametreAchats.objects.filter(code="DS_OBLIGATOIRE_GR").update(valeur=1)
        self.assertEqual(self.client.post(f"/api/achats/orders/{bc.pk}/confirmer/").status_code, 400)
        self.client.patch(f"/api/achats/orders/{bc.pk}/", {"reference_ds": "DS-001"}, format="json")
        self.assertEqual(self.client.post(f"/api/achats/orders/{bc.pk}/confirmer/").status_code, 200)


class AvoirTests(_Base):
    def setUp(self):
        super().setUp()
        call_command("seed_accounting", year=2026)
        for code, cls, typ in (("401000", 4, Account.AccountType.LIABILITY), ("445000", 4, Account.AccountType.ASSET),
                               ("601000", 6, Account.AccountType.EXPENSE)):
            Account.objects.get_or_create(code=code, defaults=dict(label=code, account_class=cls, account_type=typ))
        TauxTva.objects.create(code="TVA18", label="TVA 18", taux=Decimal("18.00"), compte_collecte=None,
                               compte_deductible=Account.objects.get(code="445000"), is_default=True)
        bc, ligne = self.bc()
        br = GoodsReceipt.objects.create(purchase_order=bc)
        GoodsReceiptLine.objects.create(receipt=br, purchase_order_line=ligne, quantity=10)
        self.facture = PurchaseInvoice.objects.create(purchase_order=bc, supplier=self.fournisseur, invoice_date=date(2026, 3, 10))
        PurchaseInvoiceLine.objects.create(invoice=self.facture, purchase_order_line=ligne, quantity=10, unit_price=Decimal("100"))

    def _comptabiliser_facture(self):
        self.assertEqual(self.client.post(f"/api/achats/invoices/{self.facture.pk}/rapprocher/").status_code, 200)
        self.assertEqual(self.client.post(f"/api/achats/invoices/{self.facture.pk}/comptabiliser/").status_code, 200)

    def _avoir(self, montant):
        return self.client.post("/api/achats/avoirs/", {"facture": str(self.facture.pk), "montant_ht": montant,
                                                         "motif": "Remise qualité", "date_avoir": "2026-03-20"}, format="json")

    def test_avoir_sur_facture_non_comptabilisee_refuse(self):
        self.assertEqual(self._avoir("100").status_code, 400)

    def test_avoir_contre_passe_au_prorata_et_plafonne(self):
        self._comptabiliser_facture()
        self.assertEqual(self._avoir("1200").status_code, 400)  # > HT facture (1 000)
        r = self._avoir("500")
        self.assertEqual(r.status_code, 201, r.content)
        self.as_(self.logistique)
        self.assertEqual(self.client.post(f"/api/achats/avoirs/{r.data['id']}/comptabiliser/").status_code, 403)
        self.as_(self.finance)
        r = self.client.post(f"/api/achats/avoirs/{r.data['id']}/comptabiliser/")
        self.assertEqual(r.status_code, 200, r.content)
        avoir = AvoirFournisseur.objects.get(pk=r.data["id"])
        lignes = {l.account.code: (l.debit, l.credit) for l in avoir.move.lines.select_related("account")}
        self.assertEqual(lignes["401000"], (Decimal("590.00"), Decimal("0")))
        self.assertEqual(lignes["601000"], (Decimal("0"), Decimal("500.00")))
        self.assertEqual(lignes["445000"], (Decimal("0"), Decimal("90.00")))
        self.assertEqual(avoir.move.status, AccountMove.Status.POSTED)
        self.assertIsNotNone(avoir.document_ged)
        self.assertEqual(self.client.post(f"/api/achats/avoirs/{avoir.pk}/comptabiliser/").status_code, 400)
        self.assertEqual(self.client.delete(f"/api/achats/avoirs/{avoir.pk}/").status_code, 400)
        self.assertEqual(self._avoir("600").status_code, 400)  # cumul 1 100 > 1 000
