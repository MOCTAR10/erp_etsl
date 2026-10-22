"""D25 / écart E6 de ETSL-ERP-INT : échanges GLOBAL RENTAL récurrents par fichiers (lectures de compteur, BL,
factures) — mêmes règles que l'API GR et les écrans, idempotence (clé métier + empreinte de fichier), fil rouge 618."""

from datetime import date, timedelta
from decimal import Decimal

from logistique.models import LectureCompteur, LigneLocationGR, LocationGR, ReceptionBLGR
from referentiels.models import Partner
from users.models import User

from .test_ecarts_a7 import RepriseA7Base
from .test_ecarts_import import URL, user
from .test_gr_api import make_location


class GabaritsGrTests(RepriseA7Base):
    def setUp(self):
        self.logistique = user("log@etls.ga", User.Role.LOGISTIQUE)
        self.admin = user("adm@etls.ga", User.Role.ADMIN, is_staff=True)
        self.client.force_authenticate(self.logistique)
        self.tolerer(50)

    def test_catalogue_par_cercle(self):
        codes = {g["code"] for g in self.client.get(URL + "catalogue/").data}
        self.assertTrue({"gr_lectures_compteurs", "gr_bl"} <= codes)
        self.assertNotIn("gr_factures", codes)  # factures GR = cercle comptable
        self.client.force_authenticate(self.admin)
        codes = {g["code"] for g in self.client.get(URL + "catalogue/").data}
        self.assertTrue({"gr_lectures_compteurs", "gr_bl", "gr_factures"} <= codes)
        r = self.client.get(URL + "modele/?gabarit=gr_factures&type=csv")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"location,numero,date,montant_ht", r.content)

    def test_lectures_jamais_en_baisse_et_sans_doublon(self):
        loc = make_location()
        hier = date.today() - timedelta(days=1)
        contenu = (f"location,date,valeur\n{loc.code},{hier - timedelta(days=1):%Y-%m-%d},150\n"
                   f"{loc.code},{hier:%Y-%m-%d},120\n")  # 120 < 150 : refusé
        r = self.charger("gr_lectures_compteurs", contenu, mode="blanc")
        self.assertEqual((r.data["statut"], r.data["creees"], r.data["erreurs"]), ("valide", 1, 1), r.data)
        self.assertFalse(LectureCompteur.objects.exists())
        r = self.charger("gr_lectures_compteurs", contenu)
        self.assertEqual((r.data["statut"], r.data["creees"], r.data["erreurs"]), ("partiel", 1, 1), r.data)
        lecture = LectureCompteur.objects.get()
        self.assertEqual((lecture.valeur, lecture.source), (Decimal("150"), LectureCompteur.Source.GR))
        loc.equipement.refresh_from_db()
        self.assertEqual(loc.equipement.compteur_value, Decimal("150"))  # compteur du parc reporté
        # Même fichier : rejeu refusé (empreinte) ; forcé : la ligne déjà chargée est un doublon.
        r = self.charger("gr_lectures_compteurs", contenu)
        self.assertTrue(r.data.get("rejeu"), r.data)
        r = self.charger("gr_lectures_compteurs", contenu, force="true")
        self.assertEqual((r.data["doublons"], r.data["creees"]), (1, 0), r.data)
        self.assertEqual(LectureCompteur.objects.count(), 1)

    def test_lecture_refusee_hors_global_rental_ou_prestation_inactive(self):
        loc = make_location()
        Partner.objects.filter(pk=loc.partenaire_id).update(is_global_rental=False)
        inactive = make_location(statut=LocationGR.Statut.BROUILLON)
        contenu = (f"location,date,valeur\n{loc.code},{date.today():%Y-%m-%d},200\n"
                   f"{inactive.code},{date.today():%Y-%m-%d},200\n")
        self.tolerer(100)
        r = self.charger("gr_lectures_compteurs", contenu)
        self.assertEqual(r.data["erreurs"], 2, r.data)
        self.assertFalse(LectureCompteur.objects.exists())

    def test_bl_multiligne_une_reception_et_escalade(self):
        loc = make_location()
        LigneLocationGR.objects.create(location=loc, designation="Grue 25 t", quantite=1, prix_unitaire=1000)
        LigneLocationGR.objects.create(location=loc, designation="Élingues", quantite=10, prix_unitaire=10)
        contenu = ("location,reference_bl,date_reception,ligne,quantite_livree\n"
                   f"{loc.code},BL-GR-1,{date.today():%Y-%m-%d},Grue 25 t,1\n"
                   f"{loc.code},BL-GR-1,{date.today():%Y-%m-%d},élingues,6\n")
        r = self.charger("gr_bl", contenu)
        self.assertEqual((r.data["statut"], r.data["creees"], r.data["mises_a_jour"]), ("succes", 1, 1), r.data)
        reception = ReceptionBLGR.objects.get()
        self.assertEqual((reception.reference_bl, reception.ecart_pct), ("BL-GR-1", Decimal("36.36")))
        self.assertTrue(reception.litige)  # 36 % > seuil paramétré : escalade M12
        self.assertIsNotNone(reception.contentieux_id)
        loc.refresh_from_db()
        self.assertEqual(loc.reference_bl, "BL-GR-1")
        r = self.charger("gr_bl", contenu, force="true")
        self.assertEqual((r.data["doublons"], r.data["creees"]), (2, 0), r.data)
        self.assertEqual(ReceptionBLGR.objects.count(), 1)

    def test_bl_ligne_ambigue_refusee(self):
        loc = make_location()
        LigneLocationGR.objects.create(location=loc, designation="A", quantite=1)
        LigneLocationGR.objects.create(location=loc, designation="B", quantite=1)
        r = self.charger("gr_bl", f"location,reference_bl,date_reception\n{loc.code},BL-2,{date.today():%Y-%m-%d}\n")
        self.assertEqual(r.data["statut"], "rejete", r.data)
        self.assertFalse(ReceptionBLGR.objects.exists())

    def test_facture_gr_sur_bc_618_rapprochee(self):
        from achats.ecarts import bc_depuis_location_gr
        from achats.models import PurchaseInvoice

        loc = make_location()
        LigneLocationGR.objects.create(location=loc, designation="Grue 25 t", quantite=1, prix_unitaire=4500)
        self.client.force_authenticate(self.admin)
        contenu = f"location,numero,date,montant_ht\n{loc.code},FGR-1,{date.today():%Y-%m-%d},4500\n"
        r = self.charger("gr_factures", contenu)
        self.assertEqual(r.data["erreurs"], 1, r.data)  # pas encore de BC GR lié
        bc = bc_depuis_location_gr(loc, self.admin)
        self.assertTrue(bc.is_global_rental)
        r = self.charger("gr_factures", contenu, force="true")
        self.assertEqual((r.data["statut"], r.data["creees"]), ("succes", 1), r.data)
        facture = PurchaseInvoice.objects.get(invoice_ref="FGR-1")
        self.assertEqual((facture.purchase_order_id, facture.supplier_id, facture.total), (bc.pk, loc.partenaire_id, Decimal("4500")))
        loc.refresh_from_db()
        self.assertEqual((loc.facture_achat_id, loc.facture_conforme, loc.facture_ecart), (facture.pk, True, Decimal("0")))
        r = self.charger("gr_factures", contenu, force="true")
        self.assertEqual(r.data["doublons"], 1, r.data)
        self.assertEqual(PurchaseInvoice.objects.filter(invoice_ref="FGR-1").count(), 1)

    def test_api_gr_et_fichier_appliquent_la_meme_regle(self):
        """L'API `/gr/compteurs/` délègue à `logistique.services.enregistrer_lecture_gr` (règle partagée)."""
        from integrations.models import ApiClient
        from rest_framework.test import APIClient

        loc = make_location()
        _, key = ApiClient.issue(name="GR", scopes=["gr:write"], user=self.admin)
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f"Api-Key {key}")
        r = api.post("/api/integrations/gr/compteurs/", {"location": loc.code, "date": str(date.today()), "valeur": "90"},
                     format="json", HTTP_IDEMPOTENCY_KEY="k-1")
        self.assertEqual(r.status_code, 400)  # 90 < lecture initiale 100
        r = api.post("/api/integrations/gr/compteurs/", {"location": loc.code, "date": str(date.today()), "valeur": "130"},
                     format="json", HTTP_IDEMPOTENCY_KEY="k-2")
        self.assertEqual(r.status_code, 201, r.content)
