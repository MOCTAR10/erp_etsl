"""Lot « outillage d'import » (CDC §10 reprise de données, plan ETSL-ERP-MIG §4.3 / §6.3).

Gabarits idempotents CSV / XML (clé métier, à blanc, transaction atomique par fichier, rapport d'anomalies),
droits par cercle (compta / RH / paie / QA-QC), GED en masse (ZIP + manifeste, SHA-256), rapprochements C1-C10,
paramètres provisoires, connecteur « table générique » retiré.
"""

import hashlib
import io
import zipfile
from datetime import date
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from rest_framework.test import APITestCase

from accounting_kernel.models import AccountMove
from referentiels.models import Account, Article, Partner
from users.models import User

from .importers_migration import executer_lot
from .models_migration import HistoriquePaie, LotReprise, ParametreReprise

URL = "/api/integrations/migration/"


def user(email, role, **kw):
    return User.objects.create_user(email=email, password="x-Import-2026", role=role, first_name=email[:3], **kw)


def fichier(nom, contenu):
    return SimpleUploadedFile(nom, contenu.encode("utf-8") if isinstance(contenu, str) else contenu)


ARTICLES = "code,libelle,type,prix_achat,stockable\nMAT-1,Tube acier,matiere,1000,oui\nMAT-2,Bride,matiere,250,oui\n"


class GabaritsIdempotentsTests(APITestCase):
    def setUp(self):
        self.compta = user("compta@etls.ga", User.Role.COMPTABLE)
        self.client.force_authenticate(self.compta)

    def charger(self, gabarit, nom, contenu, mode="reel", **extra):
        data = {"gabarit": gabarit, "mode": mode, "file": fichier(nom, contenu)}
        data.update(extra)
        return self.client.post(URL + "import/", data, format="multipart")

    def test_a_blanc_valide_sans_rien_ecrire(self):
        r = self.charger("articles", "a.csv", ARTICLES, mode="blanc")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["statut"], "valide")
        self.assertEqual(r.data["creees"], 2)
        self.assertFalse(Article.objects.exists())

    def test_reel_puis_rejeu_puis_force_sans_doublon(self):
        r = self.charger("articles", "a.csv", ARTICLES)
        self.assertEqual((r.status_code, r.data["statut"], r.data["creees"]), (201, "succes", 2))
        rejeu = self.charger("articles", "a.csv", ARTICLES)
        self.assertEqual(rejeu.status_code, 200)
        self.assertTrue(rejeu.data["rejeu"])
        force = self.charger("articles", "a.csv", ARTICLES, force="true")
        self.assertEqual((force.data["creees"], force.data["mises_a_jour"]), (0, 2))
        self.assertEqual(Article.objects.count(), 2)
        self.assertEqual(Article.objects.get(code="MAT-1").purchase_price, Decimal("1000"))

    def test_seuil_depasse_rien_n_est_ecrit_puis_seuil_releve(self):
        contenu = ARTICLES + "MAT-3,,matiere,1,oui\n"
        r = self.charger("articles", "a.csv", contenu)
        self.assertEqual(r.data["statut"], "rejete")
        self.assertFalse(Article.objects.exists())  # transaction atomique par fichier
        lot = LotReprise.objects.get(pk=r.data["id"])
        anomalie = lot.lignes_rapport.get(statut="erreur")
        self.assertEqual(anomalie.numero, 3)
        self.assertIn("libelle obligatoire", anomalie.erreur)
        rapport = self.client.get(f"{URL}lots/{lot.pk}/rapport/")
        self.assertEqual(rapport.status_code, 200)
        self.assertIn("libelle obligatoire", rapport.content.decode("utf-8"))
        ParametreReprise.objects.filter(code="TAUX_ERREUR_MAX").update(valeur=50)
        r = self.charger("articles", "a.csv", contenu)
        self.assertEqual((r.data["statut"], r.data["creees"], r.data["erreurs"]), ("partiel", 2, 1))
        self.assertEqual(Article.objects.count(), 2)

    def test_tiers_en_xml_et_dtd_refusee(self):
        xml = ('<?xml version="1.0" encoding="UTF-8"?><lignes><ligne><code>CLI-9</code><name>Client XML</name>'
               '<kind>client</kind></ligne><ligne code="GR-1" name="Global Rental" is_global_rental="1"/></lignes>')
        r = self.charger("tiers", "t.xml", xml)
        self.assertEqual((r.data["format"], r.data["creees"]), ("xml", 2), r.data)
        self.assertTrue(Partner.objects.get(code="GR-1").is_global_rental)
        bombe = '<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "x">]><lignes><ligne><code>&a;</code></ligne></lignes>'
        r = self.charger("tiers", "b.xml", bombe)
        self.assertEqual(r.data["statut"], "echec")
        self.assertIn("DTD", r.data["message"])

    def test_colonnes_manquantes_echec(self):
        r = self.charger("articles", "a.csv", "code\nX\n")
        self.assertEqual(r.data["statut"], "echec")
        self.assertIn("libelle", r.data["message"])

    def test_modele_vide_csv_et_xml(self):
        r = self.client.get(URL + "modele/", {"gabarit": "salaries", "type": "csv"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.content.decode("utf-8-sig").startswith("matricule,nom,prenom"))
        r = self.client.get(URL + "modele/", {"gabarit": "wps_wpqr", "type": "xml"})
        self.assertIn(b"<numero>WPQR-012</numero>", r.content)

    def test_affaires_et_contrats_en_cours(self):
        from commercial.models import Affaire, Contract

        Partner.objects.create(code="CLI-1", name="Client", kind="client")
        r = self.charger("affaires", "af.csv",
                         "code,intitule,client,statut,montant_contractuel\nAFF-M1,Pipeline,CLI-1,en_cours,5000000\n")
        self.assertEqual(r.data["statut"], "succes", r.data)
        affaire = Affaire.objects.get(code="AFF-M1")
        self.assertIsNotNone(affaire.analytic_id)  # axe projet M10 / M11
        r = self.charger("contrats", "ct.csv", "code,profil,debut,affaire,client\nCTT-M1,maintenance,2025-01-01,AFF-M1,CLI-1\n")
        self.assertEqual(r.data["statut"], "succes", r.data)
        contrat = Contract.objects.get(code="CTT-M1")
        self.assertEqual(contrat.status, Contract.Status.BROUILLON)
        Contract.objects.filter(pk=contrat.pk).update(status=Contract.Status.ACTIF)
        ParametreReprise.objects.get_or_create(code="TAUX_ERREUR_MAX", defaults={"label": "t", "valeur": 100})
        ParametreReprise.objects.filter(code="TAUX_ERREUR_MAX").update(valeur=100)
        r = self.charger("contrats", "ct2.csv", "code,profil,debut\nCTT-M1,maintenance,2025-02-01\n")
        self.assertIn("avenant", LotReprise.objects.get(pk=r.data["id"]).lignes_rapport.get().erreur)

    def test_affaire_global_rental_exige_tiers_gr(self):
        Partner.objects.create(code="CLI-1", name="Client", kind="client")
        r = self.charger("affaires", "af.csv", "code,intitule,client,global_rental\nAFF-GR,Loc,CLI-1,oui\n")
        self.assertEqual(r.data["statut"], "rejete")
        self.assertIn("618", LotReprise.objects.get(pk=r.data["id"]).lignes_rapport.get().erreur)

    def test_stocks_d_ouverture_idempotents(self):
        from stocks.models import StockQuant

        Article.objects.create(code="MAT-1", label="Tube", article_type="matiere", is_stockable=True)
        csv = "depot,depot_libelle,article,quantite,prix_unitaire,numero_lot,date\nMAG,Magasin,MAT-1,10,100,L-1,2026-01-01\n"
        r = self.charger("stocks_ouverture", "s.csv", csv)
        self.assertEqual(r.data["statut"], "succes", r.data)
        quant = StockQuant.objects.get()
        self.assertEqual((quant.quantity, quant.stock_value), (Decimal("10"), Decimal("1000")))
        r = self.charger("stocks_ouverture", "s.csv", csv, force="true")
        self.assertEqual(r.data["doublons"], 1)
        self.assertEqual(StockQuant.objects.get().quantity, Decimal("10"))

    def test_connecteur_table_generique_retire(self):
        r = self.client.post("/api/integrations/import/", {"connector": "generic", "file": fichier("g.csv", "a\n1\n")},
                             format="multipart")
        self.assertEqual(r.status_code, 400)


class BalanceOuvertureXmlTests(APITestCase):
    def setUp(self):
        call_command("seed_accounting", year=2026)
        for code, cls, t in (("512000", 5, "asset"), ("101000", 1, "equity")):
            Account.objects.get_or_create(code=code, defaults=dict(label=code, account_class=cls, account_type=t))
        self.compta = user("compta@etls.ga", User.Role.COMPTABLE)
        self.client.force_authenticate(self.compta)

    def test_balance_xml_a_blanc_puis_reelle_et_c1(self):
        xml = ("<lignes><ligne><compte>512000</compte><debit>1000</debit><credit>0</credit></ligne>"
               "<ligne><compte>101000</compte><debit>0</debit><credit>1000</credit></ligne></lignes>")
        data = {"gabarit": "balance_ouverture", "date": "2026-01-01", "total_controle": "1000"}
        r = self.client.post(URL + "import/", {**data, "mode": "blanc", "file": fichier("b.xml", xml)}, format="multipart")
        self.assertEqual(r.data["statut"], "valide", r.data)
        self.assertFalse(AccountMove.objects.filter(reference="AN-2026").exists())
        r = self.client.post(URL + "import/", {**data, "mode": "reel", "file": fichier("b.xml", xml)}, format="multipart")
        self.assertEqual(r.data["statut"], "succes", r.data)
        self.assertEqual(AccountMove.objects.get(reference="AN-2026").status, AccountMove.Status.POSTED)
        r = self.client.get(URL + "rapprochements/", {"source_c1": "1000"})
        c1 = next(c for c in r.data["controles"] if c["code"] == "C1")
        self.assertEqual((c1["statut"], Decimal(c1["ecart"])), ("conforme", Decimal("0")))
        self.assertEqual(len(r.data["controles"]), 10)
        export = self.client.get(URL + "rapprochements/", {"source_c1": "900", "export": "csv"})
        self.assertIn("Écart", export.content.decode("utf-8-sig"))

    def test_balance_desequilibree_rejetee(self):
        xml = "<lignes><ligne><compte>512000</compte><debit>1000</debit><credit>0</credit></ligne></lignes>"
        r = self.client.post(URL + "import/", {"gabarit": "balance_ouverture", "date": "2026-01-01", "mode": "reel",
                                               "file": fichier("b.xml", xml)}, format="multipart")
        self.assertEqual(r.data["statut"], "rejete")
        self.assertFalse(AccountMove.objects.filter(reference="AN-2026").exists())


SALARIES = (
    "matricule,nom,prenom,civilite,categorie,date_embauche,rib_compte,contrat_numero,contrat_type,contrat_debut,salaire_base\n"
    "EMP-901,MOUSSAVOU,Jean,M,ouvrier,2019-01-07,12345678901,CTR-R-1,cdi,2019-01-07,450000\n"
)


class RhPaieQualiteTests(APITestCase):
    def setUp(self):
        self.rh = user("rh@etls.ga", User.Role.RH)
        self.qaqc = user("qa@etls.ga", User.Role.QAQC)
        self.compta = user("compta@etls.ga", User.Role.COMPTABLE)
        self.service = user("service@etls.ga", User.Role.CHEF_SERVICE)

    def charger(self, qui, gabarit, contenu, nom="f.csv"):
        self.client.force_authenticate(qui)
        return self.client.post(URL + "import/", {"gabarit": gabarit, "mode": "reel", "file": fichier(nom, contenu)},
                                format="multipart")

    def test_salaries_contrat_et_donnees_sensibles_masquees(self):
        from rh_paie.models import ContratTravail, Employe

        r = self.charger(self.rh, "salaries", SALARIES)
        self.assertEqual(r.data["statut"], "succes", r.data)
        employe = Employe.objects.get(code="EMP-901")
        self.assertEqual(employe.rib_compte, "12345678901")
        self.assertEqual(ContratTravail.objects.get(code="CTR-R-1").salaire_base, Decimal("450000"))
        ligne = LotReprise.objects.get(pk=r.data["id"]).lignes_rapport.get()
        self.assertEqual((ligne.donnees["rib_compte"], ligne.donnees["salaire_base"]), ("•••", "•••"))
        self.assertEqual(self.charger(self.qaqc, "salaries", SALARIES).status_code, 403)

    def test_historique_paie_cercle_paie_et_lecture_seule(self):
        self.charger(self.rh, "salaries", SALARIES)
        mois = "".join(f"EMP-901,2025-{m:02d},BRUT,Salaire brut,cumul,,450000\n" for m in range(1, 13))
        contenu = "matricule,periode,rubrique,libelle,nature,base,montant\n" + mois
        self.assertEqual(self.charger(self.compta, "paie_historique", contenu).status_code, 403)
        r = self.charger(self.rh, "paie_historique", contenu)
        self.assertEqual((r.data["statut"], r.data["creees"]), ("succes", 12), r.data)
        self.assertEqual(HistoriquePaie.objects.filter(lot_id=r.data["id"]).count(), 12)
        liste = self.client.get(URL + "historique-paie/", {"matricule": "EMP-901", "periode": "2025-03"})
        self.assertEqual(liste.status_code, 200)
        self.assertEqual(liste.data["count"], 1)
        self.assertEqual(self.client.patch(f"{URL}historique-paie/{HistoriquePaie.objects.first().pk}/", {}).status_code, 405)
        self.client.force_authenticate(self.compta)
        self.assertEqual(self.client.get(URL + "historique-paie/").status_code, 403)
        c6 = next(c for c in self.client.get(URL + "rapprochements/", {"source_c6": "12"}).data["controles"]
                  if c["code"] == "C6")
        self.assertEqual(c6["statut"], "conforme")

    def test_reprise_qualite_wps_wpqr_soudeurs(self):
        from qualite.models import QualificationSoudeur, Soudeur, WpsWpqr

        wps = ("numero,type,procede,norme,statut,wpqr_support\nWPQR-1,wpqr,141,ISO 9606,valide,\n"
               "WPS-1,wps,gtaw,iso9606,valide,WPQR-1\n")
        r = self.charger(self.qaqc, "wps_wpqr", wps)
        self.assertEqual(r.data["statut"], "succes", r.data)
        self.assertEqual(WpsWpqr.objects.get(code="WPS-1").wpqr.code, "WPQR-1")
        self.assertEqual(WpsWpqr.objects.get(code="WPQR-1").procede, "gtaw")
        soud = ("soudeur_code,nom,qualification_numero,procede,date_qualification,date_validite\n"
                "SOU-R1,NDONG,Q-1,smaw,2024-01-01,2030-01-01\nSOU-R1,NDONG,Q-2,gtaw,2020-01-01,2022-01-01\n")
        r = self.charger(self.qaqc, "soudeurs", soud)
        self.assertEqual(r.data["statut"], "succes", r.data)
        self.assertEqual(Soudeur.objects.count(), 1)
        self.assertEqual(QualificationSoudeur.objects.get(code="Q-2").statut, "expiree")
        self.assertEqual(self.charger(self.rh, "wps_wpqr", wps).status_code, 403)

    def test_catalogue_filtre_par_cercle_et_chef_service_refuse(self):
        self.client.force_authenticate(self.qaqc)
        codes = {g["code"] for g in self.client.get(URL + "catalogue/").data}
        self.assertEqual(codes, {"wps_wpqr", "soudeurs"})
        self.client.force_authenticate(self.rh)
        self.assertEqual({g["code"] for g in self.client.get(URL + "catalogue/").data},
                         {"salaries", "paie_historique", "habilitations_hse"})
        self.client.force_authenticate(self.service)
        self.assertEqual(self.client.get(URL + "catalogue/").status_code, 403)
        self.assertEqual(self.client.get(URL + "lots/").status_code, 403)
        self.client.force_authenticate(self.rh)
        self.assertEqual(self.client.get(URL + "rapprochements/").status_code, 403)


class GedEnMasseTests(APITestCase):
    def setUp(self):
        self.compta = user("compta@etls.ga", User.Role.COMPTABLE)
        self.client.force_authenticate(self.compta)

    def lot(self, manifeste, fichiers):
        tampon = io.BytesIO()
        with zipfile.ZipFile(tampon, "w") as z:
            z.writestr("manifeste.csv", manifeste)
            for nom, contenu in fichiers.items():
                z.writestr(nom, contenu)
        return tampon.getvalue()

    def charger(self, contenu, mode="reel"):
        return self.client.post(URL + "import/", {"gabarit": "ged", "mode": mode, "file": fichier("lot.zip", contenu)},
                                format="multipart")

    def test_lot_ged_sha256_doublon_et_a_blanc(self):
        from documents.models import Document

        pdf = b"%PDF-1.4 contrat signe"
        sha = hashlib.sha256(pdf).hexdigest()
        manifeste = ("fichier,titre,type,type_libelle,retention_annees,date,dossier,sha256\n"
                     f"contrats/c1.pdf,Contrat 1,contrat-rep,Contrat repris,10,2025-01-01,Contrats / 2025,{sha}\n")
        contenu = self.lot(manifeste, {"contrats/c1.pdf": pdf})
        r = self.charger(contenu, mode="blanc")
        self.assertEqual(r.data["statut"], "valide", r.data)
        self.assertFalse(Document.objects.exists())
        r = self.charger(contenu)
        self.assertEqual(r.data["statut"], "succes", r.data)
        doc = Document.objects.get()
        self.assertEqual((doc.sha256, doc.current_version.sha256, doc.dossier.path), (sha, sha, "Contrats / 2025"))
        self.assertEqual(doc.document_date, date(2025, 1, 1))
        r = self.client.post(URL + "import/", {"gabarit": "ged", "mode": "reel", "force": "1",
                                               "file": fichier("lot.zip", contenu)}, format="multipart")
        self.assertEqual(r.data["doublons"], 1)
        self.assertEqual(Document.objects.count(), 1)
        c9 = next(c for c in self.client.get(URL + "rapprochements/", {"source_c9": "1"}).data["controles"]
                  if c["code"] == "C9")
        self.assertEqual(c9["statut"], "conforme")

    def test_empreinte_differente_rejetee(self):
        from documents.models import Document

        manifeste = "fichier,sha256\na.pdf," + "0" * 64 + "\n"
        r = self.charger(self.lot(manifeste, {"a.pdf": b"x"}))
        self.assertEqual(r.data["statut"], "rejete")
        self.assertFalse(Document.objects.exists())

    def test_zip_sans_manifeste(self):
        r = self.charger(self.lot("", {}).replace(b"manifeste.csv", b"autre_nom.csv"))
        self.assertEqual(r.data["statut"], "echec")


class ParametresRepriseTests(APITestCase):
    def test_parametres_provisoires_modifiables_puis_confirmes(self):
        compta = user("compta@etls.ga", User.Role.COMPTABLE)
        finance = user("fin@etls.ga", User.Role.FINANCE)
        self.client.force_authenticate(compta)
        r = self.client.get(URL + "parametres/")
        codes = {p["code"]: p for p in r.data["results"]} if isinstance(r.data, dict) else {p["code"]: p for p in r.data}
        self.assertTrue(codes["TAUX_ERREUR_MAX"]["est_provisoire"])
        pk = codes["ECHANTILLON_C10"]["id"]
        self.assertEqual(self.client.patch(f"{URL}parametres/{pk}/", {"valeur": "30"}).status_code, 200)
        self.assertEqual(self.client.post(f"{URL}parametres/{pk}/confirmer/").status_code, 403)
        self.client.force_authenticate(finance)
        r = self.client.post(f"{URL}parametres/{pk}/confirmer/")
        self.assertEqual((r.status_code, r.data["statut_valeur"]), (200, "confirme"))

    def test_moteur_direct_sans_api(self):
        compta = user("compta@etls.ga", User.Role.COMPTABLE)
        lot, rejeu = executer_lot("articles", "a.csv", ARTICLES.encode(), compta, mode="reel")
        self.assertEqual((lot.statut, rejeu), ("succes", False))
