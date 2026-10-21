"""Écarts M4 Logistique & GLOBAL RENTAL — tests de recette par ligne de la matrice.

M4.1 plafond + historique kilométrage / heures · M4.2 lignes BC / BL + facture GR liée (618) · M4.3 relevés,
formule glissante, archive GR · validation M2 / DR · réception BL avec écarts et escalade M12 · reporting
(rentabilité, utilisation, économies) · audit photo + historique + conservation · flux M3 · plan de charge →
demandes · BC achats ↔ location GR · rapprochement facture ↔ location.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APITestCase

from achats.models import PurchaseInvoice, PurchaseInvoiceLine, PurchaseOrder, PurchaseOrderLine
from commercial.models import Affaire
from juridique.models import Contentieux, DossierGlobalRental
from operations.models import OrdreFabrication
from referentiels.models import UnitOfMeasure
from users.models import User
from workflow.models import Notification

from .models import (
    ArchiveCompteurGR,
    AuditEquipement,
    DemandeMobilisation,
    EquipementParc,
    HistoriqueEquipement,
    LigneLocationGR,
    LocationGR,
    ParametreLogistique,
    ReleveCompteurParc,
)
from .tests import _gr_partner, _non_gr_partner

API = "/api/logistique"


def _user(email, role):
    return User.objects.create_user(email=email, password="x-Audit-2026", role=role)


class _Base(APITestCase):
    def setUp(self):
        self.logi = _user("logi@etls.ga", User.Role.LOGISTIQUE)
        self.fin = _user("fin@etls.ga", User.Role.FINANCE)
        self.pdg = _user("pdg@etls.ga", User.Role.PDG)
        self.sg = _user("sg@etls.ga", User.Role.SECRETAIRE_GENERAL)
        self.partner = _gr_partner()
        self.grue = EquipementParc.objects.create(label="Grue 25t", categorie="levage", is_global_rental=True)
        self.camion = EquipementParc.objects.create(label="Camion", categorie="transport", compteur_type="km")
        self.client.force_authenticate(self.logi)

    def location(self, **kw):
        body = {"partenaire": self.partner, "equipement": self.grue, "periodicite": "jour",
                "tarif": Decimal("1000"), "date_debut": date(2026, 9, 1), "date_fin": date(2026, 9, 10)}
        body.update(kw)
        return LocationGR.objects.create(**body)


class PlafondHistoriqueTests(_Base):
    """M4.1 : plafond paramétrable, historique kilométrage / heures jamais à la baisse, alerte au seuil."""

    def test_releve_historise_et_alerte_plafond(self):
        r = self.client.patch(f"{API}/equipements/{self.camion.pk}/", {"plafond_compteur": "1000"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        r = self.client.post(f"{API}/releves-parc/", {"equipement": str(self.camion.pk), "date": "2026-09-01", "valeur": "500"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(Notification.objects.filter(subject__startswith="Plafond").count(), 0)
        r = self.client.post(f"{API}/releves-parc/", {"equipement": str(self.camion.pk), "date": "2026-09-05", "valeur": "950"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(ReleveCompteurParc.objects.filter(equipement=self.camion).count(), 2)
        self.camion.refresh_from_db()
        self.assertEqual(self.camion.compteur_value, Decimal("950"))
        self.assertTrue(Notification.objects.filter(subject__startswith="Plafond", user=self.logi).exists())
        r = self.client.get(f"{API}/equipements/{self.camion.pk}/")
        self.assertEqual(r.data["plafond_pct"], "95.00")

    def test_compteur_ne_baisse_pas(self):
        self.client.post(f"{API}/releves-parc/", {"equipement": str(self.camion.pk), "date": "2026-09-01", "valeur": "500"}, format="json")
        r = self.client.post(f"{API}/releves-parc/", {"equipement": str(self.camion.pk), "date": "2026-09-02", "valeur": "400"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_plafond_negatif_refuse(self):
        r = self.client.patch(f"{API}/equipements/{self.camion.pk}/", {"plafond_compteur": "-1"}, format="json")
        self.assertEqual(r.status_code, 400)


class ValidationCommandeTests(_Base):
    """Commande GR : validation Achats (M2) puis Direction (DR) au-delà des seuils paramétrés."""

    def test_seuils_bloquent_emission_jusqu_aux_validations(self):
        loc = self.location(montant_estime=Decimal("60000000"))
        r = self.client.post(f"{API}/locations/{loc.pk}/emettre/", {}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("M2", str(r.data))
        # Logistique n'est pas habilitée à valider.
        self.assertEqual(self.client.post(f"{API}/locations/{loc.pk}/valider-m2/").status_code, 403)
        self.client.force_authenticate(self.pdg)
        self.assertEqual(self.client.post(f"{API}/locations/{loc.pk}/valider-dr/").status_code, 400)  # M2 d'abord
        self.client.force_authenticate(self.fin)
        self.assertEqual(self.client.post(f"{API}/locations/{loc.pk}/valider-m2/").status_code, 200)
        self.assertEqual(self.client.post(f"{API}/locations/{loc.pk}/valider-dr/").status_code, 403)
        self.client.force_authenticate(self.pdg)
        r = self.client.post(f"{API}/locations/{loc.pk}/valider-dr/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["validations"], {"m2": True, "dr": True, "m2_ok": True, "dr_ok": True})
        self.client.force_authenticate(self.logi)
        self.assertEqual(self.client.post(f"{API}/locations/{loc.pk}/emettre/", {}, format="json").status_code, 200)

    def test_petite_commande_sans_validation(self):
        loc = self.location(montant_estime=Decimal("1000000"))
        self.assertEqual(self.client.post(f"{API}/locations/{loc.pk}/emettre/", {}, format="json").status_code, 200)

    def test_seuil_parametrable(self):
        ParametreLogistique.objects.filter(code="SEUIL_VALIDATION_M2").delete()
        from .services import get_param_logistique

        get_param_logistique("SEUIL_VALIDATION_M2")
        ParametreLogistique.objects.filter(code="SEUIL_VALIDATION_M2").update(valeur=Decimal("500"))
        loc = self.location(montant_estime=Decimal("1000"))
        self.assertEqual(self.client.post(f"{API}/locations/{loc.pk}/emettre/", {}, format="json").status_code, 400)


class LignesEtBlTests(_Base):
    """M4.2 lignes BC / BL ; réception du BL avec écarts ; escalade automatique M12 au-delà du seuil."""

    def test_lignes_bc_puis_reception_sans_ecart(self):
        loc = self.location()
        r = self.client.post(f"{API}/lignes-gr/", {"location": str(loc.pk), "designation": "Grue 25t", "quantite": "10", "unite": "j", "prix_unitaire": "1000"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertIsNone(r.data["montant"])  # logistique hors cercle des montants (RF-59)
        self.assertEqual(LigneLocationGR.objects.get().montant, Decimal("10000.00"))
        self.client.post(f"{API}/locations/{loc.pk}/emettre/", {}, format="json")
        # Lignes figées après émission
        r = self.client.post(f"{API}/lignes-gr/", {"location": str(loc.pk), "designation": "X", "quantite": "1"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post(f"{API}/locations/{loc.pk}/receptionner-bl/", {"reference_bl": "BL-1"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["ecart_pct"], "0.00")
        self.assertFalse(r.data["litige"])
        self.assertEqual(Contentieux.objects.count(), 0)

    def test_ecart_au_dela_du_seuil_escalade_m12(self):
        loc = self.location()
        ligne = LigneLocationGR.objects.create(location=loc, designation="Élingues", quantite=Decimal("10"))
        r = self.client.post(f"{API}/lignes-gr/{ligne.pk}/livrer/", {"quantite_livree": "8"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        r = self.client.post(f"{API}/locations/{loc.pk}/receptionner-bl/", {"reference_bl": "BL-2", "reserves": "2 élingues manquantes"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["ecart_pct"], "20.00")
        self.assertTrue(r.data["litige"])
        self.assertIsNotNone(r.data["contentieux_code"])
        c = Contentieux.objects.get()
        self.assertEqual(c.nature, "fournisseur")
        dossier = DossierGlobalRental.objects.get()
        self.assertEqual(dossier.statut, "ouvert")
        self.assertIn(loc.code, dossier.references_documents)
        self.assertIn("BL-2", dossier.references_documents)
        self.assertTrue(Notification.objects.filter(user=self.sg, subject__startswith="Litige").exists())

    def test_escalade_manuelle_reutilise_le_dossier(self):
        loc = self.location()
        self.client.post(f"{API}/locations/{loc.pk}/escalader/", {"motif": "Retour endommagé"}, format="json")
        r = self.client.post(f"{API}/locations/{loc.pk}/escalader/", {"motif": "Pénalité contestée"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Contentieux.objects.count(), 2)
        self.assertEqual(DossierGlobalRental.objects.count(), 1)
        self.assertEqual(self.client.post(f"{API}/locations/{loc.pk}/escalader/", {}, format="json").status_code, 400)


class AchatsEt618Tests(_Base):
    """BC achats ↔ location GR et rapprochement facture ↔ location (fil rouge 618)."""

    def setUp(self):
        super().setUp()
        self.unit, _ = UnitOfMeasure.objects.get_or_create(code="U")
        self.bc = PurchaseOrder.objects.create(supplier=self.partner, is_global_rental=True)
        self.bc_line = PurchaseOrderLine.objects.create(
            purchase_order=self.bc, label="Location grue", quantity=10, unit_price=1000, unit=self.unit
        )

    def facture(self, prix, bc=None):
        bc = bc or self.bc
        f = PurchaseInvoice.objects.create(purchase_order=bc, supplier=bc.supplier)
        line = bc.lines.first() if bc != self.bc else self.bc_line
        PurchaseInvoiceLine.objects.create(invoice=f, purchase_order_line=line, quantity=10, unit_price=prix)
        return f

    def test_lien_bc_refuse_hors_gr(self):
        loc = self.location()
        autre = PurchaseOrder.objects.create(supplier=_non_gr_partner())
        r = self.client.post(f"{API}/locations/{loc.pk}/lier-bc-achat/", {"bon_commande_achat": str(autre.pk)}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post(f"{API}/locations/{loc.pk}/lier-bc-achat/", {"bon_commande_achat": str(self.bc.pk)}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["bon_commande_code"], self.bc.code)

    def test_rapprochement_facture_dans_et_hors_tolerance(self):
        loc = self.location(date_debut=date(2026, 9, 1), date_fin=date(2026, 9, 10))  # 10 j × 1000 = 10 000
        f = self.facture(1000)
        r = self.client.post(f"{API}/locations/{loc.pk}/rapprocher-facture/", {"facture_achat": str(f.pk)}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data["facture_conforme"])
        self.assertIsNone(r.data["facture_ecart"])  # masqué pour la logistique
        loc.refresh_from_db()
        self.assertEqual(loc.facture_ecart, Decimal("0.00"))
        self.assertEqual(r.data["bon_commande_code"], self.bc.code)
        loc2 = self.location(equipement=self.camion)
        r = self.client.post(f"{API}/locations/{loc2.pk}/rapprocher-facture/", {"facture_achat": str(f.pk)}, format="json")
        self.assertEqual(r.status_code, 400)  # déjà rapprochée
        bc2 = PurchaseOrder.objects.create(supplier=self.partner, is_global_rental=True)
        PurchaseOrderLine.objects.create(purchase_order=bc2, label="L", quantity=10, unit_price=1500, unit=self.unit)
        f2 = self.facture(1500, bc=bc2)
        r = self.client.post(f"{API}/locations/{loc2.pk}/rapprocher-facture/", {"facture_achat": str(f2.pk)}, format="json")
        self.assertFalse(r.data["facture_conforme"])
        loc2.refresh_from_db()
        self.assertEqual(loc2.facture_ecart, Decimal("5000.00"))

    def test_donnees_618_pour_m10_et_masquage(self):
        loc = self.location()
        loc.statut = LocationGR.Statut.ACTIVE
        loc.save()
        r = self.client.get(f"{API}/locations/donnees-618/")
        self.assertEqual(r.status_code, 200)
        row = r.data["rows"][0]
        self.assertEqual(row["compte"], "618000")
        self.assertTrue(row["partenaire_gr"])
        self.assertIsNone(row["montant_attendu"])  # logistique hors cercle des montants
        self.client.force_authenticate(self.fin)
        self.assertEqual(self.client.get(f"{API}/locations/donnees-618/").data["rows"][0]["montant_attendu"], "10000.00")


class CompteursArchiveTests(_Base):
    """M4.3 : relevés saisis, report au parc historisé, archive scellée à la clôture."""

    def test_cloture_archive_les_compteurs(self):
        loc = self.location(periodicite="heure")
        self.client.post(f"{API}/locations/{loc.pk}/demarrer/", {"lecture_initiale": "100"}, format="json")
        r = self.client.post(f"{API}/lectures/", {"location": str(loc.pk), "date": "2026-09-05", "valeur": "140"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        r = self.client.post(f"{API}/locations/{loc.pk}/cloturer/", {"lecture_finale": "180", "date_retour": "2026-09-10"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        archive = ArchiveCompteurGR.objects.get(location=loc)
        self.assertEqual(archive.contenu["consommation"], "80.00")
        self.assertEqual(len(archive.contenu["releves"]), 1)
        self.assertEqual(archive.conserver_jusqu_au.year, timezone.localdate().year + 10)
        r = self.client.get(f"{API}/archives-gr/")
        self.assertTrue(r.data["results"][0]["integre"] if "results" in r.data else r.data[0]["integre"])
        self.assertEqual(ReleveCompteurParc.objects.filter(equipement=self.grue, source="location").count(), 2)
        with self.assertRaises(Exception):
            archive.delete()


class AuditPhotoTests(_Base):
    """Audit avec photo (SHA-256, conservation 10 ans) et historique des modifications de l'équipement."""

    def test_audit_photo_et_historique(self):
        photo = SimpleUploadedFile("grue.jpg", b"\xff\xd8\xff photo", content_type="image/jpeg")
        r = self.client.post(f"{API}/audits/", {"equipement": str(self.grue.pk), "date_audit": "2026-09-01", "etat": "bon", "photo": photo}, format="multipart")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(len(r.data["photo_sha256"]), 64)
        audit = AuditEquipement.objects.get()
        self.assertEqual(audit.conserver_jusqu_au.year, timezone.localdate().year + 10)
        self.assertEqual(self.client.delete(f"{API}/audits/{audit.pk}/").status_code, 405)
        r = self.client.post(f"{API}/audits/", {"equipement": str(self.grue.pk), "date_audit": "2026-09-01", "photo": SimpleUploadedFile("x.exe", b"MZ")}, format="multipart")
        self.assertEqual(r.status_code, 400)
        self.client.patch(f"{API}/equipements/{self.grue.pk}/", {"site": "Port-Gentil"}, format="json")
        h = HistoriqueEquipement.objects.get(equipement=self.grue)
        self.assertEqual((h.champ, h.nouvelle_valeur, h.modifie_par), ("site", "Port-Gentil", self.logi))
        r = self.client.get(f"{API}/historique-equipements/?equipement={self.grue.pk}")
        self.assertEqual(r.status_code, 200)


class ReportingTests(_Base):
    """Reporting : utilisation, économies (coût GR évité) et rentabilité du parc (formules provisoires)."""

    def test_trois_indicateurs(self):
        from .models import AffectationParc

        AffectationParc.objects.create(equipement=self.camion, date_debut=date(2026, 9, 1), date_fin=date(2026, 9, 15))
        self.client.force_authenticate(self.fin)
        r = self.client.get(f"{API}/equipements/reporting/?periode=2026-09")
        self.assertEqual(r.status_code, 200)
        row = next(x for x in r.data["rows"] if x["equipement"] == self.camion.code)
        self.assertEqual(row["jours_mobilises"], 15)
        self.assertEqual(row["utilisation_pct"], "50.00")
        self.assertEqual(row["economie"], "1500000.00")  # 15 j × tarif de référence 100 000
        self.assertEqual(r.data["rentabilite_pct"], "100.00")
        self.assertTrue(r.data["provisoire"])
        self.client.force_authenticate(self.logi)
        self.assertIsNone(self.client.get(f"{API}/equipements/reporting/?periode=2026-09").data["economies"])


class PlanDeChargeFluxTests(_Base):
    """Plan de charge M3 → demandes de mobilisation ; flux compteurs / BL vers M3."""

    def test_propositions_idempotentes(self):
        aujourdhui = timezone.localdate()
        affaire = Affaire.objects.create(title="Affaire GR")
        of = OrdreFabrication.objects.create(label="Spool", scope="chantier", affaire=affaire,
                                             planned_start=aujourdhui + timedelta(days=5), planned_end=aujourdhui + timedelta(days=20))
        OrdreFabrication.objects.create(label="Lointain", scope="atelier", planned_start=aujourdhui + timedelta(days=90))
        r = self.client.post(f"{API}/demandes/proposer/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["creees"], 1)
        d = DemandeMobilisation.objects.get()
        self.assertEqual((d.ordre, d.affaire, d.statut), (of, affaire, "brouillon"))
        self.assertEqual(self.client.post(f"{API}/demandes/proposer/").data["creees"], 0)

    def test_flux_operations_par_affaire(self):
        affaire = Affaire.objects.create(title="Affaire flux")
        loc = self.location(affaire=affaire, lecture_initiale=Decimal("10"), lecture_finale=Decimal("30"), statut="terminee")
        self.client.post(f"{API}/locations/{loc.pk}/escalader/", {"motif": "x"}, format="json")
        r = self.client.get(f"{API}/locations/flux-operations/?affaire={affaire.pk}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["rows"][0]["affaire"], affaire.code)
        self.assertEqual(r.data["rows"][0]["consommation_gr"], "20.00")
        self.assertEqual(r.data["rows"][0]["machines"][0]["source"], "gr")
