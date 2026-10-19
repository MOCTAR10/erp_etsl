"""Écarts M5 (2026-10-19) — tests de recette (matrice CDC × code, §7.4, §7.5, §7.6, §7.8, §7.10, §7.11).

- Quarantaine : mise en quarantaine / levée par QA-QC (motif, auteur, date) ; une NC M6 sur un contrôle de lot met
  le lot en quarantaine, la levée attend la clôture de la NC (CAPA).
- Certificats MTC / CoC : validation attestée par QA-QC, certificat validé scellé, numérisé en GED (10 ans).
- Traçabilité client pétrolier : lot obligatoire paramétrable par article ; n° de coulée.
- Alertes : seuil minimal, péremption (délai paramétrable, provisoire), fournisseur non agréé ; notifiées.
- Bon de sortie PDF ; pièce de mouvement en GED ; lot mouvementé non supprimable.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from qualite.models import ControleQualite, NonConformite
from referentiels.models import Article, Partner, UnitOfMeasure
from users.models import User
from workflow.models import Notification

from .models import ArticleStock, CertificatMatiere, Depot, LotMatiere, MouvementStock, ParametreStock
from .services import alertes_stock, apply_move, notifier_alertes_stock


class _Base(APITestCase):
    def setUp(self):
        unit, _ = UnitOfMeasure.objects.get_or_create(code="U", defaults={"label": "Unité"})
        self.article = Article.objects.create(code="ART-TUBE", label="Tube API 5L", article_type=Article.ArticleType.MATIERE, unit=unit)
        self.mag = User.objects.create_user(email="mag@etls.ga", password="x-Audit-2026", role=User.Role.LOGISTIQUE)
        self.qa = User.objects.create_user(email="qa@etls.ga", password="x-Audit-2026", role=User.Role.QAQC)
        self.depot = Depot.objects.create(code="DEP-A", label="Magasin")
        self.client.force_authenticate(self.mag)

    def lot(self, quantite=100, **kw):
        lot = LotMatiere.objects.create(article=self.article, numero_lot=kw.pop("numero", "HEAT-1"),
                                        date_reception=date.today(), quantite_initiale=quantite, quantite_restante=0, **kw)
        apply_move(MouvementStock.objects.create(type_mouvement=MouvementStock.Type.RECEPTION, article=self.article,
                                                 quantite=quantite, prix_unitaire=10, destination=self.depot, lot=lot,
                                                 date=date.today(), created_by=self.mag))
        lot.refresh_from_db()
        return lot

    def consommer(self, lot=None, quantite="5"):
        return self.client.post("/api/stocks/mouvements/", {
            "type_mouvement": "consommation", "article": str(self.article.pk), "quantite": quantite,
            "source": str(self.depot.pk), "lot": str(lot.pk) if lot else None, "date": str(date.today()),
        }, format="json")


class QuarantaineTests(_Base):
    def test_quarantaine_par_qaqc_attestee_puis_levee(self):
        lot = self.lot()
        r = self.client.post(f"/api/stocks/lots/{lot.pk}/bloquer/", {"motif": "Doute sur la coulée"}, format="json")
        self.assertEqual(r.status_code, 403, r.content)  # magasinier : pas de quarantaine
        self.client.force_authenticate(self.qa)
        self.assertEqual(self.client.post(f"/api/stocks/lots/{lot.pk}/bloquer/", {}, format="json").status_code, 400)
        r = self.client.post(f"/api/stocks/lots/{lot.pk}/bloquer/", {"motif": "Doute sur la coulée"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.data["statut"], r.data["bloque_par"], r.data["motif_blocage"]), ("bloque", self.qa.pk, "Doute sur la coulée"))
        self.client.force_authenticate(self.mag)
        self.assertEqual(self.consommer(lot).status_code, 400)
        self.client.force_authenticate(self.qa)
        r = self.client.post(f"/api/stocks/lots/{lot.pk}/lever-quarantaine/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["statut"], "disponible")
        self.client.force_authenticate(self.mag)
        self.assertEqual(self.consommer(lot).status_code, 201)

    def test_nc_matiere_met_le_lot_en_quarantaine_jusqu_a_sa_cloture(self):
        lot = self.lot()
        # NC de fabrication (soudure) citant le lot : la matière n'est pas bloquée.
        cnd = ControleQualite.objects.create(type_controle="cnd", lot=lot, point_controle="Joint 4")
        NonConformite.objects.create(controle=cnd, description="Porosité joint 4")
        lot.refresh_from_db()
        self.assertNotEqual(lot.statut, "bloque")
        controle = ControleQualite.objects.create(type_controle="reception", lot=lot, point_controle="Réception tubes")
        nc = NonConformite.objects.create(controle=controle, description="Piqûres de corrosion")
        lot.refresh_from_db()
        self.assertEqual((lot.statut, lot.nc_blocage_id), ("bloque", nc.pk))
        self.client.force_authenticate(self.qa)
        r = self.client.post(f"/api/stocks/lots/{lot.pk}/lever-quarantaine/")
        self.assertEqual(r.status_code, 400, r.content)  # NC ouverte : CAPA d'abord
        nc.statut = NonConformite.Statut.CLOTUREE
        nc.save()
        lot.refresh_from_db()
        self.assertEqual(lot.statut, "disponible")

    def test_statut_bloque_survit_aux_mouvements(self):
        lot = self.lot()
        lot.mettre_en_quarantaine("test", user=self.qa)
        apply_move(MouvementStock.objects.create(type_mouvement=MouvementStock.Type.RETOUR, article=self.article, quantite=10,
                                                 source=self.depot, lot=lot, date=date.today(), created_by=self.mag))
        lot.refresh_from_db()
        self.assertEqual(lot.statut, "bloque")


class CertificatTests(_Base):
    def test_validation_attestee_par_qaqc_et_certificat_scelle(self):
        lot = self.lot()
        r = self.client.post("/api/stocks/certificats/", {
            "lot": str(lot.pk), "type": "mtc", "numero_certificat": "MTC-1", "date_validation": str(date.today()),
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertIsNone(r.data["date_validation"])  # jamais posée par la saisie
        cert_id = r.data["id"]
        self.assertEqual(self.client.post(f"/api/stocks/certificats/{cert_id}/valider/").status_code, 403)
        self.client.force_authenticate(self.qa)
        r = self.client.post(f"/api/stocks/certificats/{cert_id}/valider/", {"conforme": "False"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.data["conforme"], r.data["valide_par"]), (False, self.qa.pk))
        self.client.force_authenticate(self.mag)
        self.assertEqual(self.client.patch(f"/api/stocks/certificats/{cert_id}/", {"notes": "x"}, format="json").status_code, 400)
        self.assertEqual(self.client.delete(f"/api/stocks/certificats/{cert_id}/").status_code, 400)
        self.assertEqual(self.consommer(lot).status_code, 400)  # certificat non conforme : sortie interdite

    def test_certificat_numerise_scelle_en_ged(self):
        lot = self.lot()
        cert = CertificatMatiere.objects.create(lot=lot, type="coc", numero_certificat="COC-9")
        fichier = SimpleUploadedFile("coc.pdf", b"%PDF-1.4 certificat", content_type="application/pdf")
        r = self.client.post(f"/api/stocks/certificats/{cert.pk}/joindre/", {"fichier": fichier}, format="multipart")
        self.assertEqual(r.status_code, 200, r.content)
        cert.refresh_from_db()
        self.assertEqual(cert.document.type.retention_years, 10)
        self.assertIn("COC-9", r.data["document_titre"])


class TracabiliteTests(_Base):
    def test_lot_obligatoire_parametrable_et_numero_de_coulee(self):
        ArticleStock.objects.create(article=self.article, lot_obligatoire=True)
        lot = self.lot(numero_coulee="C-2026-114")
        self.assertEqual(self.client.get(f"/api/stocks/lots/{lot.pk}/").data["numero_coulee"], "C-2026-114")
        r = self.consommer(lot=None)
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("Lot obligatoire", str(r.data))
        self.assertEqual(self.consommer(lot).status_code, 201)

    def test_lot_mouvemente_non_supprimable(self):
        lot = self.lot()
        self.assertEqual(self.client.delete(f"/api/stocks/lots/{lot.pk}/").status_code, 400)


class AlertesTests(_Base):
    def test_seuil_peremption_et_fournisseur_non_agree(self):
        ArticleStock.objects.create(article=self.article, seuil_minimal=Decimal("500"))
        lot = self.lot(date_peremption=date.today() + timedelta(days=10))
        fournisseur = Partner.objects.create(code="FOU-X", name="Aciers X", kind="supplier")
        CertificatMatiere.objects.create(lot=lot, numero_certificat="MTC-2", fournisseur=fournisseur)
        types = {a["type"] for a in alertes_stock()["rows"]}
        self.assertEqual(types, {"stock_mini", "peremption", "fournisseur_non_agree"})
        # Délai de péremption réglé par ETSL : le lot sort de la fenêtre.
        alertes_stock()
        ParametreStock.objects.filter(code="PEREMPTION_ALERTE_JOURS").update(valeur=Decimal("5"))
        self.assertNotIn("peremption", {a["type"] for a in alertes_stock()["rows"]})

    def test_alertes_notifiees_une_fois_par_jour_et_endpoint(self):
        ArticleStock.objects.create(article=self.article, seuil_minimal=Decimal("500"))
        self.lot()
        notifier_alertes_stock()
        notifier_alertes_stock()
        self.assertEqual(Notification.objects.filter(user=self.mag, subject__contains="ART-TUBE").count(), 1)
        r = self.client.get("/api/stocks/mouvements/alertes/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data["provisoire"])

    def test_parametres_provisoires_confirmes_par_la_direction(self):
        rows = self.client.get("/api/stocks/parametres/").data
        rows = rows["results"] if isinstance(rows, dict) else rows
        pid = next(p["id"] for p in rows if p["code"] == "PEREMPTION_ALERTE_JOURS")
        self.assertEqual(self.client.post(f"/api/stocks/parametres/{pid}/confirmer/").status_code, 403)
        dop = User.objects.create_user(email="dop@etls.ga", password="x-Audit-2026", role=User.Role.DIRECTEUR_OPERATIONS)
        self.client.force_authenticate(dop)
        r = self.client.post(f"/api/stocks/parametres/{pid}/confirmer/")
        self.assertEqual((r.status_code, r.data["est_provisoire"]), (200, False))


class PiecesTests(_Base):
    def test_bon_de_sortie_pdf_et_piece_jointe_en_ged(self):
        lot = self.lot()
        r = self.consommer(lot)
        self.assertEqual(r.status_code, 201, r.content)
        mid = r.data["id"]
        r = self.client.get(f"/api/stocks/mouvements/{mid}/bon-de-sortie/")
        self.assertEqual((r.status_code, r["Content-Type"]), (200, "application/pdf"))
        self.assertTrue(r.content.startswith(b"%PDF"))
        fichier = SimpleUploadedFile("bs-signe.pdf", b"%PDF-1.4 signe", content_type="application/pdf")
        r = self.client.post(f"/api/stocks/mouvements/{mid}/joindre/", {"fichier": fichier}, format="multipart")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNotNone(r.data["document"])
        reception = MouvementStock.objects.filter(type_mouvement="reception").first()
        self.assertEqual(self.client.get(f"/api/stocks/mouvements/{reception.pk}/bon-de-sortie/").status_code, 400)
