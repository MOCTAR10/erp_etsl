"""Clôture M2 Achats (2026-10-17) — tests de recette des critères CDC (cahier détaillé §5.4 à §5.11).

1. « Les réceptions partielles (multi-PV) déclenchent le contrôle qualité M6 » : chaque réception crée son contrôle
   « à réception » ; la réception n'est validée qu'avec un contrôle validé conforme (ou accepté sous réserve).
2. Consultation multi-fournisseurs : statut par actions, clôture avec une offre retenue.
3. Litiges fournisseurs : relance, escalade vers le contentieux M12 (pré-contentieux), résolution motivée.
4. Pilotage : notation fournisseur (taux de service, conformité qualité, litiges), délais, prix moyen par article,
   engagements par axe analytique exposés à M11 (montants masqués hors rôles autorisés).
"""

from datetime import date, timedelta
from decimal import Decimal

from rest_framework.test import APITestCase

from juridique.models import Contentieux
from qualite.models import ControleQualite
from referentiels.models import AnalyticAccount, AnalyticAxis, Article, Partner, UnitOfMeasure
from users.models import User

from .models import (
    ConsultationOffer,
    ConsultationRequest,
    GoodsReceipt,
    GoodsReceiptLine,
    LitigeFournisseur,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseRequest,
)

PWD = "x-Audit-2026"


class BaseM2(APITestCase):
    def setUp(self):
        self.achat = User.objects.create_user(email="logi@etls.ga", password=PWD, role=User.Role.LOGISTIQUE)
        self.daf = User.objects.create_user(email="daf@etls.ga", password=PWD, role=User.Role.FINANCE)
        self.sg = User.objects.create_user(email="sg@etls.ga", password=PWD, role=User.Role.SECRETAIRE_GENERAL)  # lit, sans montants
        self.client.force_authenticate(self.daf)
        self.fournisseur = Partner.objects.create(code="FRN-1", name="Acier Gabon", kind=Partner.Kind.FOURNISSEUR)
        self.autre = Partner.objects.create(code="FRN-2", name="Tubes Express", kind=Partner.Kind.FOURNISSEUR)
        unite, _ = UnitOfMeasure.objects.get_or_create(code="U", defaults={"label": "Unité"})
        self.tube = Article.objects.create(code="TUBE-6", label="Tube 6 pouces", article_type=Article.ArticleType.MATIERE, unit=unite)

    def commande(self, fournisseur=None, attendu=None, statut=PurchaseOrder.Status.CONFIRMEE, analytic=None, qty=10, prix="100"):
        bc = PurchaseOrder.objects.create(supplier=fournisseur or self.fournisseur, status=statut, analytic=analytic,
                                          expected_date=attendu or date.today() + timedelta(days=10))
        ligne = PurchaseOrderLine.objects.create(purchase_order=bc, article=self.tube, label="Tube", quantity=qty, unit_price=Decimal(prix))
        return bc, ligne

    def recevoir(self, bc, ligne, qty, quand=None):
        br = GoodsReceipt.objects.create(purchase_order=bc)
        if quand:
            GoodsReceipt.objects.filter(pk=br.pk).update(received_at=quand)
        GoodsReceiptLine.objects.create(receipt=br, purchase_order_line=ligne, quantity=qty)
        return br


class ReceptionControleQualiteTests(BaseM2):
    def test_chaque_reception_partielle_declenche_un_controle_m6(self):
        bc, ligne = self.commande()
        br1, br2 = self.recevoir(bc, ligne, 4), self.recevoir(bc, ligne, 6)
        for br in (br1, br2):
            ctrl = ControleQualite.objects.get(reception=br)
            self.assertEqual((ctrl.type_controle, ctrl.statut), ("reception", ControleQualite.Statut.EN_ATTENTE))

    def test_statut_reception_non_modifiable_par_patch(self):
        bc, ligne = self.commande()
        br = self.recevoir(bc, ligne, 4)
        self.client.patch(f"/api/achats/receipts/{br.pk}/", {"status": "valide"}, format="json")
        br.refresh_from_db()
        self.assertEqual(br.status, GoodsReceipt.Status.EN_ATTENTE)

    def test_validation_exige_un_controle_qualite_conforme(self):
        bc, ligne = self.commande()
        br = self.recevoir(bc, ligne, 4)
        url = f"/api/achats/receipts/{br.pk}/valider/"
        r = self.client.post(url)
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("qualit", str(r.data).lower())
        ctrl = ControleQualite.objects.get(reception=br)
        ControleQualite.objects.filter(pk=ctrl.pk).update(statut="valide", resultat="non_conforme")
        self.assertEqual(self.client.post(url).status_code, 400)
        ControleQualite.objects.filter(pk=ctrl.pk).update(resultat="conforme")
        r = self.client.post(url)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["status"], GoodsReceipt.Status.VALIDE)


class ConsultationTests(BaseM2):
    def test_cycle_consultation_avec_offre_retenue(self):
        da = PurchaseRequest.objects.create(title="Tubes", requester=self.achat, status=PurchaseRequest.Status.APPROUVEE)
        consult = ConsultationRequest.objects.create(request=da, subject="Tubes 6 pouces")
        base = f"/api/achats/consultations/{consult.pk}"
        self.client.patch(f"{base}/", {"status": "cloturee"}, format="json")
        consult.refresh_from_db()
        self.assertEqual(consult.status, ConsultationRequest.Status.BROUILLON)
        self.assertEqual(self.client.post(f"{base}/ouvrir/").data["status"], ConsultationRequest.Status.OUVERTE)
        ConsultationOffer.objects.create(consultation=consult, supplier=self.fournisseur, amount=Decimal("1000"), delivery_days=10)
        self.assertEqual(self.client.post(f"{base}/cloturer/").status_code, 400)  # aucune offre retenue
        ConsultationOffer.objects.create(consultation=consult, supplier=self.autre, amount=Decimal("900"), delivery_days=12, is_selected=True)
        self.assertEqual(self.client.post(f"{base}/cloturer/").data["status"], ConsultationRequest.Status.CLOTUREE)


class LitigeTests(BaseM2):
    def test_relance_escalade_vers_le_contentieux_puis_resolution(self):
        bc, ligne = self.commande()
        r = self.client.post("/api/achats/litiges/", {"purchase_order": str(bc.pk), "type": "qualite",
                                                    "description": "Tubes ovalisés", "montant_en_jeu": "250000"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        litige = r.data["id"]
        self.assertEqual(r.data["fournisseur_name"], "Acier Gabon")
        r = self.client.post(f"/api/achats/litiges/{litige}/relancer/")
        self.assertEqual((r.data["statut"], r.data["nb_relances"]), ("relance", 1))
        r = self.client.post(f"/api/achats/litiges/{litige}/escalader/")
        self.assertEqual(r.status_code, 200, r.content)
        contentieux = Contentieux.objects.get(pk=r.data["contentieux"])
        self.assertEqual((contentieux.nature, contentieux.partie_adverse), ("fournisseur", "Acier Gabon"))
        self.assertEqual(self.client.post(f"/api/achats/litiges/{litige}/resoudre/").status_code, 400)  # résolution motivée
        r = self.client.post(f"/api/achats/litiges/{litige}/resoudre/", {"resolution": "Avoir de 250 000 F"}, format="json")
        self.assertEqual(r.data["statut"], "resolu")

    def test_statut_litige_non_modifiable_par_patch(self):
        bc, _ = self.commande()
        litige = LitigeFournisseur.objects.create(purchase_order=bc, type="delai", description="Retard")
        self.client.patch(f"/api/achats/litiges/{litige.pk}/", {"statut": "resolu"}, format="json")
        litige.refresh_from_db()
        self.assertEqual(litige.statut, "ouvert")


class PilotageAchatsTests(BaseM2):
    def test_notation_fournisseur(self):
        aujourd_hui = date.today()
        bc1, l1 = self.commande(attendu=aujourd_hui - timedelta(days=5))
        self.recevoir(bc1, l1, 10, quand=aujourd_hui - timedelta(days=6))  # complet, à l'heure
        bc2, l2 = self.commande(attendu=aujourd_hui - timedelta(days=10))
        self.recevoir(bc2, l2, 10, quand=aujourd_hui - timedelta(days=4))  # complet, 6 jours de retard
        ControleQualite.objects.filter(reception__purchase_order__supplier=self.fournisseur).update(statut="valide", resultat="conforme")
        LitigeFournisseur.objects.create(purchase_order=bc2, type="delai", description="Retard")
        r = self.client.get("/api/achats/orders/performance-fournisseurs/")
        self.assertEqual(r.status_code, 200, r.content)
        f = {x["fournisseur"]: x for x in r.data}["Acier Gabon"]
        self.assertEqual((f["commandes"], f["taux_service"], f["retard_moyen_jours"], f["taux_conformite"], f["litiges_ouverts"]),
                         (2, 0.5, 6.0, 1.0, 1))
        self.assertEqual(f["note"], 70)  # 50 × 0,5 + 30 × 1 + 20 × 0,75

    def test_reporting_prix_moyen_et_engagements_par_axe(self):
        axe = AnalyticAxis.objects.create(code="AX-P", label="Projets", axis_type="projet")
        affaire = AnalyticAccount.objects.create(axis=axe, code="AFF-01", label="Pipelines")
        self.commande(qty=10, prix="100", analytic=affaire)
        self.commande(qty=30, prix="200", analytic=affaire)
        self.commande(qty=5, prix="999", statut=PurchaseOrder.Status.BROUILLON)  # non engagé
        r = self.client.get("/api/achats/orders/reporting/")
        self.assertEqual(r.status_code, 200, r.content)
        prix = {x["article"]: x for x in r.data["prix_moyens"]}["TUBE-6"]
        self.assertEqual((prix["quantite"], prix["prix_moyen"]), ("40.00", "175.00"))
        engagement = {x["axe"]: x for x in r.data["engagements"]}["AFF-01"]
        self.assertEqual(engagement["engage"], "7000.00")
        self.client.force_authenticate(self.sg)
        r = self.client.get("/api/achats/orders/reporting/")
        self.assertIsNone(r.data["engagements"][0]["engage"])
