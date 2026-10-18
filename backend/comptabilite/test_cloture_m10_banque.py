"""Recette M10 (clôture) — PR 2/3 : import MT940 / CFONB 120 et rapprochement bancaire automatique.

Fichiers FABRIQUÉS d'après les gabarits standard : ETSL fournira ses relevés réels plus tard (réserve de clôture).
"""

from datetime import date
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from .bancaire import FichierBancaireInvalide, parse, parse_cfonb120, parse_mt940
from .models import LigneReleve, Paiement, ParametreCompta, RapprochementBancaire, ReleveBancaire
from .tests import BASE, BaseComptaTest, _auth

MT940 = """:20:REL001
:25:00012345678
:28C:1/1
:60F:C260601XAF1000000,00
:61:2606020602C500000,00NTRFNONREF//B1
:86:VIREMENT CLIENT UN FAC-1
:61:2606050605D200000,00NTRFCHQ0042//B2
:86:CHEQUE 0042 FOURNISSEUR
:62F:C260630XAF1300000,00
-
"""


def _signe(montant):
    """Montant entier -> 14 caractères, dernier chiffre signé (CFONB)."""
    chiffres = str(abs(montant)).zfill(14)
    table = "{ABCDEFGHI" if montant >= 0 else "}JKLMNOPQR"
    return chiffres[:-1] + table[int(chiffres[-1])]


def rec(code, jjmmaa, montant=0, libelle="", ref="", compte="12345678901", dec=0):
    ligne = [" "] * 120
    def put(a, b, v):
        ligne[a:b] = list(str(v).ljust(b - a)[: b - a])
    put(0, 2, code); put(2, 7, "30001"); put(11, 16, "00001"); put(16, 19, "XAF"); put(19, 20, dec)
    put(21, 32, compte); put(34, 40, jjmmaa); put(48, 79, libelle); put(81, 87, "000001")
    put(90, 104, _signe(montant)); put(104, 120, ref)
    return "".join(ligne)


def cfonb(final=1300000):
    return "\n".join([
        rec("01", "010626", 1000000),
        rec("04", "020626", 500000, "VIREMENT CLIENT UN", "FAC-1"),
        rec("04", "050626", -200000, "CHEQUE 0042", "CHQ0042"),
        rec("07", "300626", final),
    ])


class ParseursTests(SimpleTestCase):
    def test_mt940(self):
        r = parse_mt940(MT940)
        self.assertEqual((r["solde_initial"], r["solde_final"]), (Decimal("1000000"), Decimal("1300000")))
        self.assertEqual((r["date_debut"], r["date_fin"]), (date(2026, 6, 1), date(2026, 6, 30)))
        self.assertEqual(r["compte"], "00012345678")
        self.assertEqual(len(r["lignes"]), 2)
        entree, sortie = r["lignes"]
        self.assertEqual((entree["credit"], entree["debit"], entree["reference"]), (Decimal("500000"), 0, "B1"))
        self.assertEqual((sortie["debit"], sortie["reference"]), (Decimal("200000"), "CHQ0042"))
        self.assertIn("CLIENT UN", entree["libelle"])
        self.assertEqual(r["anomalies"], [])

    def test_cfonb120(self):
        r = parse_cfonb120(cfonb())
        self.assertEqual((r["solde_initial"], r["solde_final"]), (Decimal("1000000"), Decimal("1300000")))
        self.assertEqual(len(r["lignes"]), 2)
        self.assertEqual(r["lignes"][0]["credit"], Decimal("500000"))
        self.assertEqual((r["lignes"][1]["debit"], r["lignes"][1]["reference"]), (Decimal("200000"), "CHQ0042"))
        self.assertEqual(r["lignes"][0]["libelle"], "VIREMENT CLIENT UN")
        self.assertEqual(r["anomalies"], [])

    def test_cfonb_decimales_et_solde_negatif(self):
        r = parse_cfonb120("\n".join([rec("01", "010626", -12345, dec=2), rec("07", "300626", -12345, dec=2)]))
        self.assertEqual(r["solde_initial"], Decimal("-123.45"))

    def test_solde_incoherent_signale_sans_bloquer(self):
        r = parse_cfonb120(cfonb(final=1400000))
        self.assertEqual([a["type"] for a in r["anomalies"]], ["solde_incoherent"])
        self.assertEqual(len(r["lignes"]), 2)

    def test_doublon_et_date_hors_periode(self):
        texte = MT940.replace(":62F:", ":61:2606020602C500000,00NTRFNONREF//B1\n:86:VIREMENT CLIENT UN FAC-1\n:61:2607010701C1,00NTRFX//B3\n:86:HORS\n:62F:")
        types = {a["type"] for a in parse_mt940(texte)["anomalies"]}
        self.assertTrue({"doublon", "date_hors_periode", "solde_incoherent"} <= types)

    def test_ligne_illisible_signalee(self):
        texte = MT940.replace("2606050605D200000,00NTRFCHQ0042//B2", "n'importe quoi")
        r = parse_mt940(texte)
        self.assertIn("ligne_illisible", [a["type"] for a in r["anomalies"]])
        self.assertEqual(len(r["lignes"]), 1)

    def test_fichier_invalide(self):
        for contenu in ("", "bonjour", "99 abc"):
            with self.assertRaises(FichierBancaireInvalide):
                parse(contenu)

    def test_detection_automatique(self):
        self.assertEqual(parse(MT940)["format"], "mt940")
        self.assertEqual(parse(cfonb())["format"], "cfonb120")


class ImportTests(BaseComptaTest):
    def setUp(self):
        super().setUp()
        self.banque = self._banque()
        _auth(self.client, "compta@etls.local")

    def importer(self, contenu, fmt="auto", **kw):
        return self.client.post(
            f"{BASE}releves/importer/",
            {"compte_bancaire": str(self.banque.id), "format": fmt, "contenu": contenu, **kw},
            format="json",
        )

    def test_import_mt940(self):
        r = self.importer(MT940)
        self.assertEqual(r.status_code, 201, r.content)
        b = r.json()
        self.assertEqual((b["source"], b["statut"]), ("mt940", "importe"))
        self.assertEqual((b["date_debut"], b["date_fin"]), ("2026-06-01", "2026-06-30"))
        self.assertEqual(len(b["lignes"]), 2)
        self.assertEqual(b["anomalies"], [])
        self.assertEqual(Decimal(b["solde_final"]), Decimal("1300000"))

    def test_import_cfonb_par_fichier_televerse(self):
        f = SimpleUploadedFile("rel.txt", cfonb().encode("latin-1"), content_type="text/plain")
        r = self.client.post(
            f"{BASE}releves/importer/", {"compte_bancaire": str(self.banque.id), "format": "cfonb120", "fichier": f}
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["source"], "cfonb")
        self.assertEqual(ReleveBancaire.objects.get().lignes.count(), 2)

    def test_reimport_du_meme_fichier_refuse(self):
        self.assertEqual(self.importer(MT940).status_code, 201)
        r = self.importer(MT940)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(ReleveBancaire.objects.count(), 1)

    def test_anomalies_enregistrees_sur_le_releve(self):
        r = self.importer(cfonb(final=1400000))
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual([a["type"] for a in r.json()["anomalies"]], ["solde_incoherent"])

    def test_compte_different_signale(self):
        self.banque.numero = "99999999999"
        self.banque.save()
        r = self.importer(MT940)
        self.assertIn("compte_different", [a["type"] for a in r.json()["anomalies"]])

    def test_fichier_illisible_refuse(self):
        self.assertEqual(self.importer("n'importe quoi").status_code, 400)
        self.assertEqual(ReleveBancaire.objects.count(), 0)

    def test_compte_bancaire_inconnu_refuse(self):
        r = self.client.post(
            f"{BASE}releves/importer/",
            {"compte_bancaire": "00000000-0000-0000-0000-000000000000", "contenu": MT940}, format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_logistique_ne_peut_pas_importer(self):
        _auth(self.client, "logi@etls.local")
        self.assertIn(self.importer(MT940).status_code, (401, 403))


class RapprochementAutoTests(BaseComptaTest):
    def setUp(self):
        super().setUp()
        self.banque = self._banque()
        _auth(self.client, "compta@etls.local")
        r = self.client.post(
            f"{BASE}releves/importer/",
            {"compte_bancaire": str(self.banque.id), "contenu": MT940}, format="json",
        )
        self.assertEqual(r.status_code, 201, r.content)

    def pay(self, sens, montant, d, reference="", statut="valide"):
        return Paiement.objects.create(
            sens=sens, mode="virement", montant=Decimal(montant), date=d,
            compte_bancaire=self.banque, reference=reference, statut=statut,
        )

    def rapprocher(self):
        return self.client.post(
            f"{BASE}rapprochements/rapprocher-auto/", {"compte_bancaire": str(self.banque.id)}, format="json"
        )

    def test_rapprochement_par_montant_sens_et_date(self):
        entree = self.pay("entree", "500000", date(2026, 6, 3))   # J+1 : dans la tolérance
        sortie = self.pay("sortie", "200000", date(2026, 6, 5), "CHQ0042")
        r = self.rapprocher()
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(body["rapprochees"], 2)
        self.assertEqual(body["lignes_sans_paiement"], [])
        self.assertEqual(body["paiements_sans_ligne"], [])
        self.assertEqual(LigneReleve.objects.filter(rapprochee=True).count(), 2)
        self.assertEqual(LigneReleve.objects.get(credit=Decimal("500000")).paiement_id, entree.id)
        self.assertEqual(LigneReleve.objects.get(debit=Decimal("200000")).paiement_id, sortie.id)
        rap = RapprochementBancaire.objects.get()
        self.assertEqual((rap.statut, rap.lignes.count()), ("brouillon", 2))

    def test_idempotent(self):
        self.pay("entree", "500000", date(2026, 6, 2))
        self.assertEqual(self.rapprocher().json()["rapprochees"], 1)
        self.assertEqual(self.rapprocher().json()["rapprochees"], 0)
        self.assertEqual(RapprochementBancaire.objects.count(), 1)

    def test_le_sens_est_respecte(self):
        self.pay("sortie", "500000", date(2026, 6, 2))
        self.assertEqual(self.rapprocher().json()["rapprochees"], 0)

    def test_ecarts_signales(self):
        self.pay("entree", "500000", date(2026, 6, 2))
        self.pay("entree", "123000", date(2026, 6, 10))
        body = self.rapprocher().json()
        self.assertEqual(body["rapprochees"], 1)
        self.assertEqual(len(body["lignes_sans_paiement"]), 1)       # le chèque de 200 000
        self.assertEqual(len(body["paiements_sans_ligne"]), 1)       # l'encaissement de 123 000

    def test_brouillon_ignore(self):
        self.pay("entree", "500000", date(2026, 6, 2), statut="brouillon")
        self.assertEqual(self.rapprocher().json()["rapprochees"], 0)

    def test_tolerance_de_jours_parametrable(self):
        self.client.get(f"{BASE}parametres/")  # crée les défauts
        ParametreCompta.objects.filter(code="RAPPRO_TOLERANCE_JOURS").update(valeur=Decimal("0"))
        self.pay("entree", "500000", date(2026, 6, 3))
        self.assertEqual(self.rapprocher().json()["rapprochees"], 0)
        ParametreCompta.objects.filter(code="RAPPRO_TOLERANCE_JOURS").update(valeur=Decimal("1"))
        self.assertEqual(self.rapprocher().json()["rapprochees"], 1)

    def test_ambiguite_non_rapprochee_sauf_reference(self):
        self.pay("entree", "500000", date(2026, 6, 2))
        self.pay("entree", "500000", date(2026, 6, 2))
        body = self.rapprocher().json()
        self.assertEqual(body["rapprochees"], 0)
        self.assertEqual(len(body["ambigues"]), 1)

    def test_reference_departage(self):
        self.pay("entree", "500000", date(2026, 6, 2))
        voulu = self.pay("entree", "500000", date(2026, 6, 2), "B1")
        self.assertEqual(self.rapprocher().json()["rapprochees"], 1)
        self.assertEqual(LigneReleve.objects.get(credit=Decimal("500000")).paiement_id, voulu.id)

    def test_logistique_ne_peut_pas_rapprocher(self):
        _auth(self.client, "logi@etls.local")
        self.assertIn(self.rapprocher().status_code, (401, 403))
