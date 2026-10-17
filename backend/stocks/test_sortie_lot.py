"""Lot 12 (2026-10-17) — aucune sortie sur un lot bloqué, périmé ou à certificat non validé (CDC M5 §7.8 / §7.11).

« Blocage de sortie si certificat MTC/CoC non validé ou périmé » ; « Aucune sortie n'est possible sur un lot en
quarantaine ou à certificat non validé ». Sorties contrôlées : consommation (OF / chantier) et transfert.
Le retour fournisseur reste possible (c'est le traitement normal d'un lot non conforme).
"""

from datetime import date, timedelta

from rest_framework.test import APITestCase

from referentiels.models import Article, UnitOfMeasure
from users.models import User

from .models import ArticleStock, CertificatMatiere, Depot, LotMatiere, MouvementStock
from .services import apply_move


class SortieLotTests(APITestCase):
    def setUp(self):
        unit, _ = UnitOfMeasure.objects.get_or_create(code="U", defaults={"label": "Unité"})
        self.article = Article.objects.create(code="ART-TUBE", label="Tube API 5L", article_type=Article.ArticleType.MATIERE, unit=unit)
        self.user = User.objects.create_user(email="mag@etls.ga", password="x-Audit-2026", role=User.Role.LOGISTIQUE)
        self.depot = Depot.objects.create(code="DEP-A", label="Magasin")
        self.autre = Depot.objects.create(code="DEP-B", label="Chantier")

    def lot(self, **kw):
        lot = LotMatiere.objects.create(article=self.article, numero_lot=kw.pop("numero", "HEAT-1"),
                                        date_reception=date.today(), quantite_initiale=100, quantite_restante=0, **kw)
        apply_move(MouvementStock.objects.create(type_mouvement=MouvementStock.Type.RECEPTION, article=self.article, quantite=100,
                                                 prix_unitaire=10, destination=self.depot, lot=lot, date=date.today(), created_by=self.user))
        lot.refresh_from_db()
        return lot

    def certificat(self, lot, conforme=True, valide=True):
        return CertificatMatiere.objects.create(lot=lot, type="mtc", numero_certificat=f"MTC-{lot.numero_lot}",
                                                conforme=conforme, date_validation=date.today() if valide else None)

    def sortie(self, lot, type_mouvement=MouvementStock.Type.CONSOMMATION, destination=None):
        return MouvementStock.objects.create(type_mouvement=type_mouvement, article=self.article, quantite=10, source=self.depot,
                                             destination=destination, lot=lot, date=date.today(), created_by=self.user)

    def assert_bloque(self, lot, motif, **kw):
        with self.assertRaises(ValueError) as ctx:
            apply_move(self.sortie(lot, **kw))
        self.assertIn(motif, str(ctx.exception).lower())

    def test_lot_en_quarantaine_ni_consomme_ni_transfere(self):
        lot = self.lot()
        self.certificat(lot)
        LotMatiere.objects.filter(pk=lot.pk).update(statut=LotMatiere.Statut.BLOQUE)
        lot.refresh_from_db()
        self.assert_bloque(lot, "quarantaine")
        self.assert_bloque(lot, "quarantaine", type_mouvement=MouvementStock.Type.TRANSFERT, destination=self.autre)

    def test_lot_bloque_peut_etre_retourne_au_fournisseur(self):
        lot = self.lot()
        LotMatiere.objects.filter(pk=lot.pk).update(statut=LotMatiere.Statut.BLOQUE)
        lot.refresh_from_db()
        apply_move(self.sortie(lot, type_mouvement=MouvementStock.Type.RETOUR))  # pas d'exception

    def test_lot_perime_bloque(self):
        lot = self.lot(date_peremption=date.today() - timedelta(days=1))
        self.certificat(lot)
        self.assert_bloque(lot, "périmé")

    def test_certificat_non_valide_ou_non_conforme_bloque(self):
        lot = self.lot()
        self.certificat(lot, valide=False)
        self.assert_bloque(lot, "certificat")
        lot2 = self.lot(numero="HEAT-2")
        self.certificat(lot2, conforme=False)
        self.assert_bloque(lot2, "certificat")

    def test_certificat_exige_pour_les_articles_tracabilite_petroliere(self):
        ArticleStock.objects.create(article=self.article, gestion_lots=True, certificat_requis=True)
        lot = self.lot()
        self.assert_bloque(lot, "certificat")
        self.certificat(lot)
        apply_move(self.sortie(lot))  # certificat validé et conforme : sortie autorisée

    def test_refus_via_api_en_400(self):
        lot = self.lot()
        self.certificat(lot, valide=False)
        self.client.force_authenticate(self.user)
        r = self.client.post("/api/stocks/mouvements/", {"type_mouvement": "consommation", "article": self.article.pk, "quantite": "5",
                                                         "source": str(self.depot.pk), "lot": str(lot.pk), "date": str(date.today())}, format="json")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("certificat", str(r.data).lower())
