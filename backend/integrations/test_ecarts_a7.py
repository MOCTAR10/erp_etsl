"""Recette du lot a7 (reprise) : gabarits habilitations HSE, équipements / compteurs (parc, maintenance), commandes
d'achat ouvertes, factures ouvertes clients et fournisseurs — CSV / XML, clé métier, à blanc, rejeu sans doublon."""

from decimal import Decimal

from django.core.management import call_command
from django.db.models import Sum
from rest_framework.test import APITestCase

from accounting_kernel.models import AccountMoveLine
from referentiels.models import Partner
from users.models import User

from .models_migration import ParametreReprise
from .test_ecarts_import import URL, fichier, user


def solde(code, partner=None, sans_tiers=False):
    qs = AccountMoveLine.objects.filter(account__code=code, move__status__in=("posted", "reversed"))
    if partner is not None:
        qs = qs.filter(partner=partner)
    if sans_tiers:
        qs = qs.filter(partner__isnull=True)
    agg = qs.aggregate(d=Sum("debit"), c=Sum("credit"))
    return (agg["d"] or Decimal("0")) - (agg["c"] or Decimal("0"))


class RepriseA7Base(APITestCase):
    def charger(self, gabarit, contenu, mode="reel", nom="f.csv", **extra):
        data = {"gabarit": gabarit, "mode": mode, "file": fichier(nom, contenu), **extra}
        return self.client.post(URL + "import/", data, format="multipart")

    def tolerer(self, taux=50):
        ParametreReprise.objects.update_or_create(code="TAUX_ERREUR_MAX", defaults={"label": "x", "valeur": taux})


class HabilitationsHseTests(RepriseA7Base):
    def setUp(self):
        self.rh = user("rh@etls.ga", User.Role.RH)
        self.hse = user("hse@etls.ga", User.Role.HSE)
        self.client.force_authenticate(self.rh)
        r = self.charger("salaries", "matricule,nom,civilite\nEMP-1,NDONG,M\n")
        self.assertEqual(r.data["statut"], "succes", r.data)

    def test_habilitations_idempotentes_et_lues_par_le_controle_des_permis(self):
        from rh_paie.models import Qualification

        self.client.force_authenticate(self.hse)
        codes = {g["code"] for g in self.client.get(URL + "catalogue/").data}
        self.assertEqual(codes, {"habilitations_hse"})
        contenu = ("matricule,intitule,organisme,date_obtention,date_validite\n"
                   "EMP-1,Habilitation travail en hauteur,APAVE,2025-01-01,2099-01-01\n"
                   "EMP-9,Habilitation électrique,,,\n"
                   "EMP-1,Sauveteur secouriste,,2025-05-01,2025-01-01\n")
        r = self.charger("habilitations_hse", contenu)
        self.assertEqual(r.data["statut"], "rejete")  # 2 erreurs sur 3 : rien n'est écrit
        self.assertFalse(Qualification.objects.exists())
        self.tolerer(70)
        r = self.charger("habilitations_hse", contenu)
        self.assertEqual((r.data["statut"], r.data["creees"], r.data["erreurs"]), ("partiel", 1, 2), r.data)
        r = self.charger("habilitations_hse", contenu, force="true")
        self.assertEqual((r.data["creees"], r.data["mises_a_jour"]), (0, 1))
        q = Qualification.objects.get()
        self.assertEqual((q.type, q.organisme, q.employe.code), ("habilitation", "APAVE", "EMP-1"))
        self.assertTrue(q.notes.startswith("[Reprise migration]"))
        self.assertEqual(Qualification.objects.filter(employe=q.employe, intitule__icontains="hauteur").count(), 1)


class ParcMaintenanceTests(RepriseA7Base):
    def setUp(self):
        self.logistique = user("log@etls.ga", User.Role.LOGISTIQUE)
        self.client.force_authenticate(self.logistique)

    def test_equipements_compteur_historise_sans_doublon_puis_releves(self):
        from logistique.models import EquipementParc

        codes = {g["code"] for g in self.client.get(URL + "catalogue/").data}
        self.assertEqual(codes, {"equipements_parc", "releves_compteurs", "actifs_maintenance",
                                 "gr_lectures_compteurs", "gr_bl"})  # + échanges GR récurrents (D25)
        contenu = "code,libelle,categorie,compteur_type,compteur,date_releve\nPAR-1,Grue 50 t,levage,heures,1250,2026-01-31\n"
        r = self.charger("equipements_parc", contenu, mode="blanc")
        self.assertEqual((r.data["statut"], r.data["creees"]), ("valide", 1))
        self.assertFalse(EquipementParc.objects.exists())
        self.assertEqual(self.charger("equipements_parc", contenu).data["statut"], "succes")
        r = self.charger("equipements_parc", contenu, force="true")
        self.assertEqual(r.data["mises_a_jour"], 1)
        eq = EquipementParc.objects.get(code="PAR-1")
        self.assertEqual((eq.compteur_value, eq.releves.count(), eq.categorie), (Decimal("1250"), 1, "levage"))

        self.tolerer(50)
        releves = "equipement,date,valeur\nPAR-1,2026-02-28,1300\nPAR-1,2026-03-31,1200\n"
        r = self.charger("releves_compteurs", releves)
        self.assertEqual((r.data["creees"], r.data["erreurs"]), (1, 1), r.data)
        r = self.charger("releves_compteurs", releves, force="true")
        self.assertEqual((r.data["doublons"], r.data["creees"]), (1, 0))
        eq.refresh_from_db()
        self.assertEqual((eq.compteur_value, eq.releves.count()), (Decimal("1300"), 2))

    def test_equipement_gr_exige_proprietaire_gr_et_actif_compteur_jamais_a_la_baisse(self):
        from maintenance.models import Actif

        Partner.objects.create(code="FRS-X", name="Loueur", kind="fournisseur")
        r = self.charger("equipements_parc", "code,libelle,global_rental,proprietaire\nPAR-GR,Nacelle,oui,FRS-X\n")
        self.assertEqual(r.data["statut"], "rejete")
        self.assertIn("GLOBAL RENTAL", self.client.get(f"{URL}lots/{r.data['id']}/lignes/").content.decode())
        xml = ('<?xml version="1.0"?><lignes><ligne><code>EQ-1</code><designation>Poste TIG</designation>'
               '<compteur>830</compteur><compteur_type>forfait</compteur_type></ligne></lignes>')
        r = self.charger("actifs_maintenance", xml, nom="a.xml")
        self.assertEqual((r.data["format"], r.data["statut"]), ("xml", "succes"), r.data)
        actif = Actif.objects.get(code="EQ-1")
        self.assertEqual((actif.compteur_value, actif.compteur_type), (Decimal("830"), "aucun"))
        r = self.charger("actifs_maintenance", "code,designation,compteur\nEQ-1,Poste TIG,800\n")
        self.assertEqual(r.data["statut"], "rejete")


class CommandesFacturesOuvertesTests(RepriseA7Base):
    def setUp(self):
        call_command("seed_accounting", year=2026)
        self.compta = user("compta@etls.ga", User.Role.COMPTABLE)
        self.client.force_authenticate(self.compta)
        self.frs = Partner.objects.create(code="FRS-1", name="Tubes SA", kind="fournisseur")
        self.cli = Partner.objects.create(code="CLI-1", name="Pétrole SA", kind="client")
        self.gr = Partner.objects.create(code="GR-1", name="Global Rental", kind="both", is_global_rental=True)

    def test_commandes_ouvertes_lignes_reception_partielle_et_rejeu(self):
        from achats.models import PurchaseOrder

        contenu = ("numero,fournisseur,date,designation,quantite,prix_unitaire,quantite_recue\n"
                   "BC-S-1,FRS-1,2026-11-15,Tube 6 pouces,40,1000,10\n"
                   "BC-S-1,FRS-1,2026-11-15,Bride,5,200,0\n")
        r = self.charger("commandes_ouvertes", contenu)
        self.assertEqual((r.data["statut"], r.data["creees"]), ("succes", 2), r.data)
        r = self.charger("commandes_ouvertes", contenu, force="true")
        self.assertEqual(r.data["mises_a_jour"], 2)
        bc = PurchaseOrder.objects.get(code="BC-S-1")
        self.assertEqual((bc.status, bc.lines.count(), bc.total), ("partielle", 2, Decimal("41000")))
        PurchaseOrder.objects.create(code="BC-ERP", supplier=self.frs)
        self.tolerer(100)
        r = self.charger("commandes_ouvertes",
                         "numero,fournisseur,date,designation,quantite,global_rental\n"
                         "BC-ERP,FRS-1,2026-11-15,X,1,non\nBC-S-2,FRS-1,2026-11-15,Y,1,oui\nBC-S-3,FRS-1,2026-11-15,Z,2,non\n")
        self.assertEqual((r.data["creees"], r.data["erreurs"]), (1, 2), r.data)
        lignes = self.client.get(f"{URL}lots/{r.data['id']}/lignes/").content.decode()
        self.assertIn("déjà saisi dans l'ERP", lignes)
        self.assertIn("GLOBAL RENTAL", lignes)

    def test_factures_clients_ouvertes_ventilees_par_tiers_neutres_sur_le_411(self):
        from comptabilite.models import FactureClient

        contenu = ("numero,client,date,echeance,solde,montant_ttc\n"
                   "FA-1,CLI-1,2025-12-10,2026-01-09,2360000,2950000\nFA-2,GR-1,2025-12-20,,500000,\n")
        r = self.charger("factures_clients_ouvertes", contenu)
        self.assertEqual(r.data["statut"], "echec")  # date de bascule obligatoire
        r = self.charger("factures_clients_ouvertes", contenu, mode="blanc", date="2026-01-01")
        self.assertEqual((r.data["statut"], r.data["creees"]), ("valide", 2), r.data)
        self.assertFalse(FactureClient.objects.exists())
        r = self.charger("factures_clients_ouvertes", contenu, date="2026-01-01")
        self.assertEqual((r.data["statut"], r.data["creees"]), ("succes", 2), r.data)
        fa = FactureClient.objects.get(code="FA-1")
        self.assertEqual((fa.statut, fa.montant_ttc, fa.echeance.isoformat()), ("emise", Decimal("2360000"), "2026-01-09"))
        self.assertIn("2950000", fa.objet)
        self.assertEqual((solde("411000", self.cli), solde("411000", sans_tiers=True)), (Decimal("2360000"), Decimal("-2360000")))
        self.assertEqual(solde("411100", self.gr), Decimal("500000"))  # intra-groupe GLOBAL RENTAL
        r = self.charger("factures_clients_ouvertes", contenu, date="2026-01-01", force="true")
        self.assertEqual((r.data["doublons"], r.data["creees"]), (2, 0))
        self.assertEqual(solde("411000", self.cli), Decimal("2360000"))
        r = self.charger("factures_clients_ouvertes", "numero,client,date,solde\nFA-1,CLI-1,2025-12-10,100\n", date="2026-01-01")
        self.assertEqual(r.data["statut"], "rejete")

    def test_factures_fournisseurs_ouvertes_comptabilisees_pretes_au_paiement(self):
        from achats.models import PurchaseInvoice

        contenu = "numero,fournisseur,date,solde,commande\nF-88213,FRS-1,2025-12-01,1180000,BC-OLD-7\n"
        r = self.charger("factures_fournisseurs_ouvertes", contenu, nom="ff.csv", date="2026-01-01")
        self.assertEqual((r.data["statut"], r.data["creees"]), ("succes", 1), r.data)
        facture = PurchaseInvoice.objects.get(invoice_ref="F-88213")
        self.assertEqual((facture.status, facture.total_ttc), ("comptabilisee", Decimal("1180000")))
        self.assertEqual(facture.purchase_order.status, "cloturee")
        self.assertIn("BC-OLD-7", facture.purchase_order.notes)
        self.assertEqual((solde("401000", self.frs), solde("401000", sans_tiers=True)), (Decimal("-1180000"), Decimal("1180000")))
        r = self.charger("factures_fournisseurs_ouvertes", contenu, nom="ff.csv", date="2026-01-01", force="true")
        self.assertEqual(r.data["doublons"], 1)
        self.assertEqual(PurchaseInvoice.objects.count(), 1)
