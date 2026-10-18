"""Recette M9 (clôture) — barèmes de paie paramétrables, taux provisoires, historique inaltérable.

PR 1/3 : barèmes + taux. Les taux de test sont arbitraires ; les valeurs Gabon 2026 chargées par
`seed_baremes_legaux_provisoires` sont PROVISOIRES (à confirmer par ETSL / le cabinet de paie).
"""

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management import call_command
from rest_framework import status

from users.models import User

from .models import BaremeCotisation, BaremeImpot, BulletinLigne, BulletinPaie, HistoriqueBareme, ParametrePaie, RubriquePaie
from .services import calculer_bulletin
from .tests import BASE, BaseRHTest, _auth


class M9Base(BaseRHTest):
    def setUp(self):
        super().setUp()
        self.sal = RubriquePaie.objects.create(code="SAL", label="Salaire", nature=RubriquePaie.Nature.GAIN)
        self.finance = User.objects.create_user(
            email="finance@etls.local", password="Etls#Demo2026", role=User.Role.FINANCE
        )
        self.logistique = User.objects.create_user(
            email="logistique@etls.local", password="Etls#Demo2026", role=User.Role.LOGISTIQUE
        )

    def bulletin(self, periode=date(2026, 3, 1)):
        b = BulletinPaie.objects.create(employe=self.employe, periode=periode, salaire_base=Decimal("1000000"))
        BulletinLigne.objects.create(bulletin=b, rubrique=self.sal, libelle="Salaire", montant=Decimal("1000000"))
        return b

    def bareme(self, taux="5", **kw):
        return BaremeCotisation.objects.create(
            code="T-S", label="Test", nature="salariale", taux=Decimal(taux), date_effet=kw.pop("date_effet", date(2026, 1, 1)), **kw
        )


class TauxProvisoiresTests(M9Base):
    def test_seed_charge_valeurs_provisoires_idempotent(self):
        call_command("seed_baremes_legaux_provisoires")
        call_command("seed_baremes_legaux_provisoires")
        n = BaremeCotisation.objects.count()
        self.assertGreaterEqual(n, 6)
        self.assertFalse(BaremeCotisation.objects.exclude(statut_valeur="provisoire").exists())
        self.assertFalse(BaremeCotisation.objects.filter(source="").exists())  # chaque valeur est sourcée
        cnss = BaremeCotisation.objects.get(code="CNSS-VIEIL-P")
        self.assertEqual((cnss.taux, cnss.plafond), (Decimal("11"), Decimal("1500000")))
        self.assertTrue(BaremeImpot.objects.get(code="IRPP").est_provisoire)
        self.assertEqual(ParametrePaie.objects.get(code="DUREE_LEGALE_HEBDO").valeur, Decimal("40"))

    def test_seed_ne_remplace_pas_une_valeur_confirmee(self):
        call_command("seed_baremes_legaux_provisoires")
        BaremeCotisation.objects.filter(code="CNSS-VIEIL-P").update(taux=Decimal("12"), statut_valeur="confirme")
        call_command("seed_baremes_legaux_provisoires")
        self.assertEqual(BaremeCotisation.objects.get(code="CNSS-VIEIL-P").taux, Decimal("12"))

    def test_bulletin_avertit_tant_qu_un_bareme_est_provisoire(self):
        self.bareme()
        b = calculer_bulletin(self.bulletin())
        _auth(self.client, "finance@etls.local")
        data = self.client.get(f"{BASE}bulletins/{b.pk}/").json()
        self.assertEqual(data["baremes_provisoires"], ["T-S"])
        self.assertIn("provisoires", data["avertissement"])
        self.assertIn("T-S", data["avertissement"])

    def test_avertissement_disparait_apres_confirmation_et_recalcul(self):
        bar = self.bareme()
        b = self.bulletin()
        _auth(self.client, "finance@etls.local")
        r = self.client.post(f"{BASE}baremes/{bar.pk}/confirmer/")
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.content)
        self.client.post(f"{BASE}bulletins/{b.pk}/calculer/")
        data = self.client.get(f"{BASE}bulletins/{b.pk}/").json()
        self.assertEqual(data["baremes_provisoires"], [])
        self.assertEqual(data["avertissement"], "")

    def test_le_salarie_voit_aussi_l_avertissement(self):
        self.bareme()
        b = calculer_bulletin(self.bulletin())
        BulletinPaie.objects.filter(pk=b.pk).update(statut="valide")
        _auth(self.client, "admin@etls.local")
        self.client.post(f"{BASE}bulletins/{b.pk}/diffuser/")
        from .models import Employe

        Employe.objects.filter(pk=self.employe.pk).update(user=self.ouvrier)
        _auth(self.client, self.ouvrier.email)
        data = self.client.get(f"{BASE}mon-espace/bulletins/{b.pk}/").json()
        self.assertIn("provisoires", data["avertissement"])


class ParametrageDroitsTests(M9Base):
    def test_confirmation_posee_cote_serveur_par_le_cercle_paie(self):
        bar = self.bareme()
        _auth(self.client, "finance@etls.local")
        r = self.client.post(f"{BASE}baremes/{bar.pk}/confirmer/", {"confirme_par": self.admin.pk}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        bar.refresh_from_db()
        self.assertEqual(bar.statut_valeur, "confirme")
        self.assertEqual(bar.confirme_par, self.finance)  # jamais le client
        self.assertIsNotNone(bar.confirme_le)

    def test_statut_non_modifiable_par_patch(self):
        bar = self.bareme()
        _auth(self.client, "finance@etls.local")
        self.client.patch(f"{BASE}baremes/{bar.pk}/", {"statut_valeur": "confirme"}, format="json")
        bar.refresh_from_db()
        self.assertEqual(bar.statut_valeur, "provisoire")

    def test_hors_cercle_paie_aucun_acces(self):
        bar = self.bareme()
        _auth(self.client, "logistique@etls.local")
        for url in ("baremes/", "baremes-impot/", "parametres-paie/", "historique-baremes/"):
            self.assertIn(self.client.get(f"{BASE}{url}").status_code, (401, 403), url)
        self.assertEqual(self.client.post(f"{BASE}baremes/{bar.pk}/confirmer/").status_code, 403)
        self.assertEqual(
            self.client.post(f"{BASE}parametres-paie/", {"code": "X", "label": "x", "valeur": "1", "date_effet": "2026-01-01"},
                             format="json").status_code, 403)

    def test_modifier_une_valeur_confirmee_la_repasse_en_provisoire(self):
        bar = self.bareme()
        _auth(self.client, "finance@etls.local")
        self.client.post(f"{BASE}baremes/{bar.pk}/confirmer/")
        r = self.client.patch(f"{BASE}baremes/{bar.pk}/", {"taux": "6"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        bar.refresh_from_db()
        self.assertEqual((bar.taux, bar.statut_valeur, bar.confirme_par), (Decimal("6"), "provisoire", None))

    def test_parametre_paie_cree_par_api(self):
        _auth(self.client, "rh@etls.local")
        r = self.client.post(
            f"{BASE}parametres-paie/",
            {"code": "SMIG", "label": "SMIG", "valeur": "80000", "unite": "FCFA", "date_effet": "2026-01-01",
             "source": "test"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["statut_valeur"], "provisoire")


class HistoriqueTests(M9Base):
    def test_creation_modification_confirmation_tracees(self):
        _auth(self.client, "finance@etls.local")
        r = self.client.post(
            f"{BASE}baremes/",
            {"code": "H1", "label": "H", "nature": "salariale", "base": "brut", "taux": "1", "date_effet": "2026-01-01"},
            format="json")
        pk = r.json()["id"]
        self.client.patch(f"{BASE}baremes/{pk}/", {"taux": "2"}, format="json")
        self.client.post(f"{BASE}baremes/{pk}/confirmer/")
        actions = list(HistoriqueBareme.objects.filter(code="H1").order_by("le").values_list("action", flat=True))
        self.assertEqual(actions, ["creation", "modification", "confirmation"])
        modif = HistoriqueBareme.objects.get(code="H1", action="modification")
        self.assertEqual(modif.avant["taux"], "1.000")
        self.assertEqual(modif.apres["taux"], "2.000")
        self.assertEqual(modif.par, self.finance)
        hist = self.client.get(f"{BASE}baremes/{pk}/historique/").json()
        self.assertEqual(len(hist), 3)

    def test_historique_inalterable(self):
        bar = self.bareme()
        from .services import tracer_changement

        h = tracer_changement(bar, "cotisation", "creation", self.admin)
        h.action = "autre"
        with self.assertRaises(ValidationError):
            h.save()
        with self.assertRaises(ValidationError):
            h.delete()
        _auth(self.client, "admin@etls.local")
        self.assertEqual(self.client.delete(f"{BASE}historique-baremes/{h.pk}/").status_code, 405)
        self.assertEqual(self.client.patch(f"{BASE}historique-baremes/{h.pk}/", {"code": "x"}, format="json").status_code, 405)


class VersionsEtRecalculTests(M9Base):
    def test_revision_conserve_l_ancien_bareme_pour_les_bulletins_passes(self):
        bar = self.bareme("5", plafond=None)
        _auth(self.client, "finance@etls.local")
        r = self.client.post(f"{BASE}baremes/{bar.pk}/reviser/", {"date_effet": "2026-07-01", "taux": "8"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["statut_valeur"], "provisoire")
        bar.refresh_from_db()
        self.assertEqual(bar.date_fin, date(2026, 6, 30))
        self.assertEqual(BaremeCotisation.objects.filter(code="T-S").count(), 2)
        mars = calculer_bulletin(self.bulletin(date(2026, 3, 1)))
        aout = calculer_bulletin(self.bulletin(date(2026, 8, 1)))
        self.assertEqual(mars.lignes.get(rubrique__code="COT-T-S").montant, Decimal("50000.00"))  # 5 %
        self.assertEqual(aout.lignes.get(rubrique__code="COT-T-S").montant, Decimal("80000.00"))  # 8 %
        self.assertEqual(mars.baremes_utilises[0]["taux"], "5.000")  # instantané rejouable

    def test_revision_date_anterieure_refusee(self):
        bar = self.bareme()
        _auth(self.client, "finance@etls.local")
        r = self.client.post(f"{BASE}baremes/{bar.pk}/reviser/", {"date_effet": "2025-01-01", "taux": "8"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_valeur_utilisee_par_un_bulletin_valide_ni_modifiable_ni_supprimable(self):
        bar = self.bareme()
        b = calculer_bulletin(self.bulletin())
        BulletinPaie.objects.filter(pk=b.pk).update(statut="valide")
        _auth(self.client, "finance@etls.local")
        self.assertEqual(self.client.patch(f"{BASE}baremes/{bar.pk}/", {"taux": "9"}, format="json").status_code, 400)
        self.assertEqual(self.client.delete(f"{BASE}baremes/{bar.pk}/").status_code, 400)
        bar.refresh_from_db()
        self.assertEqual(bar.taux, Decimal("5"))
        # une simple annotation (source) reste permise
        self.assertEqual(self.client.patch(f"{BASE}baremes/{bar.pk}/", {"source": "JO"}, format="json").status_code, 200)

    def test_bareme_impot_revisable(self):
        imp = BaremeImpot.objects.create(
            code="IR", label="IR", tranches=[{"plafond": 100000, "taux": 0}, {"plafond": None, "taux": 10}],
            date_effet=date(2026, 1, 1),
        )
        _auth(self.client, "finance@etls.local")
        r = self.client.post(
            f"{BASE}baremes-impot/{imp.pk}/reviser/",
            {"date_effet": "2027-01-01", "tranches": [{"plafond": None, "taux": 5}]}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(BaremeImpot.objects.filter(code="IR").count(), 2)


class ModificationParEtslTests(M9Base):
    """ETSL modifie lui-même taux, plafonds, tranches et paramètres (sans développeur)."""

    def test_modifier_taux_plafond_tranches_et_parametre(self):
        call_command("seed_baremes_legaux_provisoires")
        _auth(self.client, "rh@etls.local")
        bar = BaremeCotisation.objects.get(code="CNSS-VIEIL-P")
        r = self.client.patch(f"{BASE}baremes/{bar.pk}/", {"taux": "10.5", "plafond": "1600000"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        bar.refresh_from_db()
        self.assertEqual((bar.taux, bar.plafond), (Decimal("10.5"), Decimal("1600000")))

        imp = BaremeImpot.objects.get(code="IRPP")
        tranches = [{"plafond": 150000, "taux": 0}, {"plafond": None, "taux": 12}]
        r = self.client.patch(f"{BASE}baremes-impot/{imp.pk}/", {"tranches": tranches, "abattement_pct": "15"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        imp.refresh_from_db()
        self.assertEqual((imp.tranches, imp.abattement_pct), (tranches, Decimal("15")))
        # tranches incohérentes refusées
        r = self.client.patch(f"{BASE}baremes-impot/{imp.pk}/", {"tranches": [{"plafond": 1, "taux": 1}]}, format="json")
        self.assertEqual(r.status_code, 400)

        param = ParametrePaie.objects.get(code="HS_MAJ_1")
        r = self.client.patch(f"{BASE}parametres-paie/{param.pk}/", {"valeur": "15"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        param.refresh_from_db()
        self.assertEqual(param.valeur, Decimal("15"))
        self.assertEqual(HistoriqueBareme.objects.filter(action="modification").count(), 3)


class BulletinArchiveTests(M9Base):
    """PR 2/3 : bulletin PDF scellé en GED (≥ 10 ans) et virement CFONB des salaires."""

    def valide(self, periode=date(2026, 3, 1)):
        self.bareme()
        b = calculer_bulletin(self.bulletin(periode))
        BulletinPaie.objects.filter(pk=b.pk).update(statut="valide")
        b.refresh_from_db()
        return b

    def test_archivage_pdf_ged_dix_ans_restreint(self):
        b = self.valide()
        _auth(self.client, "finance@etls.local")
        r = self.client.post(f"{BASE}bulletins/{b.pk}/archiver/")
        self.assertEqual(r.status_code, 200, r.content)
        b.refresh_from_db()
        doc = b.document
        self.assertGreaterEqual(doc.type.retention_years, 10)
        self.assertTrue(doc.type.is_restricted_rh)
        self.assertEqual(doc.status, "archived")
        with doc.current_version.file.open("rb") as f:
            contenu = f.read()
        self.assertTrue(contenu.startswith(b"%PDF"))
        import hashlib

        self.assertEqual(hashlib.sha256(contenu).hexdigest(), doc.sha256)
        # scellé : pas de second archivage
        self.assertEqual(self.client.post(f"{BASE}bulletins/{b.pk}/archiver/").status_code, 400)

    def test_brouillon_non_archivable(self):
        self.bareme()
        b = calculer_bulletin(self.bulletin())
        _auth(self.client, "finance@etls.local")
        self.assertEqual(self.client.post(f"{BASE}bulletins/{b.pk}/archiver/").status_code, 400)

    def test_diffusion_archive_et_le_salarie_telecharge_son_pdf(self):
        from .models import Employe

        b = self.valide()
        Employe.objects.filter(pk=self.employe.pk).update(user=self.ouvrier)
        _auth(self.client, "admin@etls.local")
        self.assertEqual(self.client.post(f"{BASE}bulletins/{b.pk}/diffuser/").status_code, 200)
        b.refresh_from_db()
        self.assertIsNotNone(b.document_id)
        _auth(self.client, self.ouvrier.email)
        r = self.client.get(f"{BASE}mon-espace/bulletins/{b.pk}/pdf/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.content.startswith(b"%PDF"))
        # le bulletin d'un autre salarié reste introuvable
        autre = BulletinPaie.objects.create(employe=self.employe2, periode=date(2026, 3, 1), disponible_le=b.disponible_le)
        self.assertEqual(self.client.get(f"{BASE}mon-espace/bulletins/{autre.pk}/pdf/").status_code, 404)

    def test_pdf_hors_cercle_paie_refuse(self):
        b = self.valide()
        _auth(self.client, "logistique@etls.local")
        self.assertIn(self.client.get(f"{BASE}bulletins/{b.pk}/pdf/").status_code, (403, 404))


class VirementCfonbTests(M9Base):
    def setUp(self):
        super().setUp()
        from .models import CompteEmetteur

        self.compte = CompteEmetteur.objects.create(
            raison_sociale="ETSL", numero_emetteur="123456", code_banque="30001", code_guichet="00123",
            numero_compte="12345678901", cle_rib="45",
        )
        self.bareme()
        b = calculer_bulletin(self.bulletin())
        BulletinPaie.objects.filter(pk=b.pk).update(statut="valide")
        self.b = BulletinPaie.objects.get(pk=b.pk)
        self.payload = {"periode": "2026-03-01", "compte": str(self.compte.pk), "date_execution": "2026-03-28"}

    def rib(self):
        from .models import Employe

        Employe.objects.filter(pk=self.employe.pk).update(
            rib_banque="30002", rib_guichet="00456", rib_compte="98765432101", rib_cle="12", banque_nom="BGFI")

    def test_rib_incomplet_refuse(self):
        _auth(self.client, "finance@etls.local")
        r = self.client.post(f"{BASE}ordres-virement/generer/", self.payload, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("RIB incomplet", str(r.json()))

    def test_fichier_cfonb_160_et_pas_de_doublon(self):
        self.rib()
        _auth(self.client, "finance@etls.local")
        r = self.client.post(f"{BASE}ordres-virement/generer/", self.payload, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        ordre = r.json()
        self.assertEqual((ordre["nb_virements"], Decimal(ordre["total"])), (1, self.b.net))
        self.assertEqual(ordre["par_email"], "finance@etls.local")
        fichier = self.client.get(f"{BASE}ordres-virement/{ordre['id']}/fichier/").content.decode()
        lignes = fichier.splitlines()
        self.assertEqual([l[:2] for l in lignes], ["03", "06", "08"])
        self.assertTrue(all(len(l) == 160 for l in lignes))
        self.assertEqual(int(lignes[1][102:118]), int(self.b.net * 100))
        self.assertEqual(int(lignes[2][102:118]), int(self.b.net * 100))
        self.b.refresh_from_db()
        self.assertEqual(str(self.b.ordre_virement_id), ordre["id"])
        # un bulletin déjà viré n'est jamais viré deux fois
        r = self.client.post(f"{BASE}ordres-virement/generer/", self.payload, format="json")
        self.assertEqual(r.status_code, 400)

    def test_ordre_scelle(self):
        self.rib()
        from .services import generer_virement

        ordre = generer_virement(date(2026, 3, 1), self.compte, date(2026, 3, 28))
        ordre.nb_virements = 9
        with self.assertRaises(ValidationError):
            ordre.save()
        with self.assertRaises(ValidationError):
            ordre.delete()

    def test_hors_cercle_paie_aucun_acces(self):
        _auth(self.client, "logistique@etls.local")
        self.assertEqual(self.client.post(f"{BASE}ordres-virement/generer/", self.payload, format="json").status_code, 403)
        self.assertEqual(self.client.get(f"{BASE}comptes-emetteurs/").status_code, 403)

    def test_rib_masque_et_non_modifiable_hors_cercle_paie(self):
        self.rib()
        chef = User.objects.create_user(email="chef@etls.local", password="Etls#Demo2026", role=User.Role.CHEF_ATELIER)
        _auth(self.client, "chef@etls.local")
        data = self.client.get(f"{BASE}employes/{self.employe.pk}/").json()
        self.assertNotIn("rib_compte", data)
        r = self.client.patch(f"{BASE}employes/{self.employe.pk}/", {"rib_compte": "1"}, format="json")
        self.assertEqual(r.status_code, 403)
        _auth(self.client, "finance@etls.local")
        self.assertEqual(self.client.get(f"{BASE}employes/{self.employe.pk}/").json()["rib_compte"], "98765432101")
        self.assertIsNotNone(chef)


class PiiChiffreesTests(M9Base):
    def test_rib_et_n_cnss_chiffres_en_base_clairs_dans_l_orm(self):
        from django.db import connection

        from .models import Employe

        e = Employe.objects.get(pk=self.employe.pk)
        e.numero_securite_sociale, e.rib_compte = "CNSS0001234", "12345678901"
        e.save()
        e = Employe.objects.get(pk=self.employe.pk)
        self.assertEqual((e.numero_securite_sociale, e.rib_compte), ("CNSS0001234", "12345678901"))
        with connection.cursor() as cur:
            cur.execute("select numero_securite_sociale, rib_compte from rh_paie_employe where id = %s", [str(e.pk)])
            brut = cur.fetchone()
        self.assertTrue(all(v.startswith("enc1:") for v in brut))
        self.assertNotIn("CNSS0001234", brut[0])

    def test_valeur_historique_en_clair_restee_lisible(self):
        from django.db import connection

        from .models import Employe

        with connection.cursor() as cur:
            cur.execute("update rh_paie_employe set matricule_cnps = 'ANCIEN-CLAIR' where id = %s", [str(self.employe.pk)])
        self.assertEqual(Employe.objects.get(pk=self.employe.pk).matricule_cnps, "ANCIEN-CLAIR")


class HeuresSupTests(M9Base):
    def pointer(self, jour, heures, employe=None):
        from .models import SaisieTemps

        SaisieTemps.objects.create(employe=employe or self.employe, date=jour, heures=Decimal(heures))

    def setUp(self):
        super().setUp()
        call_command("seed_baremes_legaux_provisoires")

    def test_heures_sup_par_semaine_selon_parametres(self):
        # semaine du 02/03/2026 : 50 h => 8 h a +25 % (41e-48e) et 2 h a +50 %
        for jour in (2, 3, 4, 5, 6):
            self.pointer(date(2026, 3, jour), 10)
        b = self.bulletin()
        b.lignes.all().delete()
        _auth(self.client, "finance@etls.local")
        r = self.client.post(f"{BASE}bulletins/{b.pk}/integrer-temps/")
        self.assertEqual(r.status_code, 200, r.content)
        ligne = BulletinLigne.objects.get(bulletin=b, rubrique__code="HS-TEMPS")
        self.assertEqual(ligne.montant, Decimal("75000.00"))
        # idempotent
        self.client.post(f"{BASE}bulletins/{b.pk}/integrer-temps/")
        self.assertEqual(BulletinLigne.objects.filter(bulletin=b, rubrique__code="HS-TEMPS").count(), 1)
        # les parametres sont des donnees : changer la majoration change le montant
        ParametrePaie.objects.filter(code="HS_MAJ_1").update(valeur=Decimal("50"))
        self.client.post(f"{BASE}bulletins/{b.pk}/integrer-temps/")
        self.assertEqual(BulletinLigne.objects.get(bulletin=b, rubrique__code="HS-TEMPS").montant, Decimal("86538.46"))

    def test_bulletin_avertit_que_les_parametres_sont_provisoires(self):
        self.pointer(date(2026, 3, 2), "45")
        b = self.bulletin()
        _auth(self.client, "finance@etls.local")
        data = self.client.post(f"{BASE}bulletins/{b.pk}/integrer-temps/").json()
        self.assertIn("HS_MAJ_1", data["baremes_provisoires"])
        self.assertIn("provisoires", data["avertissement"])

    def test_aucune_heure_sup_sous_la_duree_legale(self):
        self.pointer(date(2026, 3, 2), "8")
        b = self.bulletin()
        _auth(self.client, "finance@etls.local")
        self.client.post(f"{BASE}bulletins/{b.pk}/integrer-temps/")
        self.assertFalse(BulletinLigne.objects.filter(bulletin=b, rubrique__code="HS-TEMPS").exists())

    def test_parametre_absent_refuse_et_bulletin_valide_intouchable(self):
        ParametrePaie.objects.all().delete()
        b = self.bulletin()
        _auth(self.client, "finance@etls.local")
        r = self.client.post(f"{BASE}bulletins/{b.pk}/integrer-temps/")
        self.assertEqual(r.status_code, 400)
        self.assertIn("absent", str(r.json()))
        BulletinPaie.objects.filter(pk=b.pk).update(statut="valide")
        self.assertEqual(self.client.post(f"{BASE}bulletins/{b.pk}/integrer-temps/").status_code, 400)


class DeclarationsTests(M9Base):
    def setUp(self):
        super().setUp()
        call_command("seed_baremes_legaux_provisoires")
        from .models import Employe

        e = Employe.objects.get(pk=self.employe.pk)
        e.numero_securite_sociale, e.matricule_cnps = "CNSS0001234", "AM-77"
        e.save()
        for mois in (3, 4):
            b = calculer_bulletin(self.bulletin(date(2026, mois, 1)))
            BulletinPaie.objects.filter(pk=b.pk).update(statut="valide")
        self.payload = {"type": "cnss", "periode_debut": "2026-03-01", "periode_fin": "2026-04-01"}

    def generer(self, **kw):
        _auth(self.client, "finance@etls.local")
        return self.client.post(f"{BASE}declarations/generer/", {**self.payload, **kw}, format="json")

    def test_cnss_sans_ressaisie_avec_avertissement_provisoire(self):
        r = self.generer()
        self.assertEqual(r.status_code, 201, r.content)
        d = r.json()
        self.assertEqual(d["nb_salaries"], 1)
        # 2 mois x brut 1 000 000 : salarial 5 % (50 000) ; patronal 11 + 5 + 2 = 18 % (180 000)
        self.assertEqual(Decimal(d["total_salarial"]), Decimal("100000.00"))
        self.assertEqual(Decimal(d["total_patronal"]), Decimal("360000.00"))
        self.assertTrue(d["provisoire"])
        self.assertIn("provisoires", d["avertissement"])
        lignes = self.client.get(f"{BASE}declarations/{d['id']}/fichier/").content.decode().splitlines()
        self.assertTrue(lignes[0].startswith("# Taux provisoires"))
        self.assertIn("CNSS0001234", lignes[-1])
        self.assertTrue(lignes[-1].endswith(";2000000.00;2000000.00;100000.00;360000.00"), lignes[-1])

    def test_declaration_confirmee_sans_avertissement(self):
        BaremeCotisation.objects.update(statut_valeur="confirme")
        BaremeImpot.objects.update(statut_valeur="confirme")
        for b in BulletinPaie.objects.all():
            BulletinPaie.objects.filter(pk=b.pk).update(statut="brouillon")
            calculer_bulletin(BulletinPaie.objects.get(pk=b.pk))
            BulletinPaie.objects.filter(pk=b.pk).update(statut="valide")
        d = self.generer().json()
        self.assertFalse(d["provisoire"])
        self.assertEqual(d["avertissement"], "")

    def test_cnamgs_irpp_et_dads(self):
        for type_ in ("cnamgs", "irpp", "dads"):
            r = self.generer(type=type_)
            self.assertEqual(r.status_code, 201, (type_, r.content))
        dads = self.client.get(f"{BASE}declarations/{r.json()['id']}/fichier/").content.decode()
        self.assertIn("n_cnss", dads)
        self.assertIn("CNSS0001234", dads)

    def test_scellee_et_sans_bulletin_refusee(self):
        from .models import DeclarationSociale

        d = DeclarationSociale.objects.get(pk=self.generer().json()["id"])
        d.nb_salaries = 9
        with self.assertRaises(ValidationError):
            d.save()
        with self.assertRaises(ValidationError):
            d.delete()
        r = self.generer(periode_debut="2027-01-01", periode_fin="2027-02-01")
        self.assertEqual(r.status_code, 400)

    def test_hors_cercle_paie_refuse(self):
        _auth(self.client, "logistique@etls.local")
        self.assertEqual(self.client.post(f"{BASE}declarations/generer/", self.payload, format="json").status_code, 403)
        self.assertEqual(self.client.get(f"{BASE}declarations/").status_code, 403)


class ReportingRhTests(M9Base):
    def test_turnover_et_absenteisme(self):
        from .models import DemandesConge, Employe

        Employe.objects.filter(pk=self.employe.pk).update(date_embauche=date(2020, 1, 1))
        Employe.objects.filter(pk=self.employe2.pk).update(date_embauche=date(2020, 1, 1), date_sortie=date(2026, 6, 30))
        DemandesConge.objects.create(
            employe=self.employe, type="maladie", date_debut=date(2026, 2, 2), date_fin=date(2026, 2, 6), nb_jours=5,
            statut="valide",
        )
        _auth(self.client, "rh@etls.local")
        d = self.client.get(f"{BASE}reporting/?annee=2026").json()
        self.assertEqual((d["sorties"], d["jours_absence"]), (1, 5))
        self.assertEqual(d["effectif_debut"], d["effectif_fin"] + 1)
        self.assertIsNotNone(d["turnover_pct"])
        self.assertIsNotNone(d["absenteisme_pct"])
        _auth(self.client, "logistique@etls.local")
        self.assertEqual(self.client.get(f"{BASE}reporting/?annee=2026").status_code, 403)
