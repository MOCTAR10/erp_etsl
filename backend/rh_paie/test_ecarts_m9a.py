"""Écarts M9-A : bulletin préparé depuis le contrat (grille, primes, prorata, absences), expatrié, plafond
d'abattement IRPP, déclarations FNH / CFP, carrière inaltérable, calendrier des déclarations et alertes."""

from datetime import date, timedelta
from decimal import Decimal

from django.core.management import call_command

from users.models import User

from .models import (
    Absence, BaremeCotisation, BaremeImpot, BulletinPaie, ContratTravail, DeclarationSociale, DemandesConge,
    EcheanceDeclaration, ElementFixe, EvenementCarriere, GrilleSalaire, ParametrePaie, RubriquePaie,
)
from .paie_m9a import calendrier_declarations, date_limite, preparer_bulletin
from .services import generer_declaration
from .tests import BASE, BaseRHTest, _auth

MOIS = date(2026, 3, 1)


class M9aBase(BaseRHTest):
    def setUp(self):
        super().setUp()
        self.contrat = ContratTravail.objects.create(
            employe=self.employe, type=ContratTravail.Type.CDI, date_debut=date(2025, 1, 1),
            salaire_base=Decimal("300000"),
        )

    def bulletin(self, employe=None, periode=MOIS):
        return BulletinPaie.objects.create(employe=employe or self.employe, periode=periode)

    def lignes(self, bulletin):
        return {l.rubrique.code: l.montant for l in bulletin.lignes.select_related("rubrique")}

    def param(self, code, valeur):
        ParametrePaie.objects.create(code=code, label=code, valeur=Decimal(valeur), date_effet=date(2020, 1, 1))


class PreparationBulletinTests(M9aBase):
    def test_brut_construit_depuis_contrat_et_primes_recurrentes(self):
        transport = RubriquePaie.objects.create(code="PRIME-TR", label="Prime de transport")
        logement = RubriquePaie.objects.create(code="IND-LOG", label="Indemnité de logement")
        ElementFixe.objects.create(contrat=self.contrat, rubrique=transport, montant=Decimal("20000"), date_debut=date(2025, 1, 1))
        ElementFixe.objects.create(contrat=self.contrat, rubrique=logement, taux=Decimal("10"), date_debut=date(2025, 1, 1))
        ElementFixe.objects.create(  # échu : non repris
            contrat=self.contrat, rubrique=transport, montant=Decimal("5000"), date_debut=date(2024, 1, 1),
            date_fin=date(2024, 12, 31),
        )
        b = preparer_bulletin(self.bulletin())
        b.refresh_from_db()
        self.assertEqual(self.lignes(b), {"SAL-BASE": Decimal("300000"), "PRIME-TR": Decimal("20000"), "IND-LOG": Decimal("30000")})
        self.assertEqual((b.salaire_base, b.brut), (Decimal("300000"), Decimal("350000")))
        preparer_bulletin(b)  # idempotent
        b.refresh_from_db()
        self.assertEqual(b.brut, Decimal("350000"))

    def test_salaire_de_la_grille_en_vigueur_a_la_periode(self):
        g1 = GrilleSalaire.objects.create(categorie="cadre", classe="C1", echelon=2, salaire_base=Decimal("400000"), date_effet=date(2025, 1, 1))
        GrilleSalaire.objects.create(categorie="cadre", classe="C1", echelon=2, salaire_base=Decimal("420000"), date_effet=date(2026, 3, 1))
        self.contrat.grille = g1
        self.contrat.save()
        b = preparer_bulletin(self.bulletin(periode=date(2026, 2, 1)))
        self.assertEqual(BulletinPaie.objects.get(pk=b.pk).brut, Decimal("400000"))
        b = preparer_bulletin(self.bulletin())
        b.refresh_from_db()
        self.assertEqual(b.brut, Decimal("420000"))
        self.assertIn("grille cadre-C1-E2", b.lignes.get(rubrique__code="SAL-BASE").libelle)

    def test_prorata_entree_en_cours_de_mois(self):
        self.contrat.date_debut = date(2026, 3, 17)  # 15 jours sur 31
        self.contrat.save()
        b = preparer_bulletin(self.bulletin())
        self.assertEqual(BulletinPaie.objects.get(pk=b.pk).brut, Decimal("145161.29"))

    def test_absences_non_remunerees_et_conge_sans_solde_deduits(self):
        self.param("JOURS_PAIE_MOIS", "30")
        Absence.objects.create(employe=self.employe, type="injustifiee", date_debut=date(2026, 3, 2), date_fin=date(2026, 3, 3), statut="validee")
        Absence.objects.create(employe=self.employe, type="injustifiee", date_debut=date(2026, 3, 9), date_fin=date(2026, 3, 9))  # saisie : ignorée
        Absence.objects.create(employe=self.employe, type="maladie", date_debut=date(2026, 3, 10), date_fin=date(2026, 3, 12), statut="validee")  # payée
        DemandesConge.objects.create(
            employe=self.employe, type=DemandesConge.Type.SANS_SOLDE, date_debut=date(2026, 2, 27),
            date_fin=date(2026, 3, 2), nb_jours=4, statut=DemandesConge.Statut.VALIDE_RH,
        )  # 2 jours sur mars
        b = preparer_bulletin(self.bulletin())
        b.refresh_from_db()
        self.assertEqual(self.lignes(b)["ABS-NP"], Decimal("-40000.00"))  # 4 j x 300 000 / 30
        self.assertEqual(b.brut, Decimal("260000"))
        self.assertIn("JOURS_PAIE_MOIS", [s["code"] for s in b.baremes_utilises])

    def test_absence_sans_diviseur_parametre_refusee(self):
        Absence.objects.create(employe=self.employe, type="injustifiee", date_debut=MOIS, date_fin=MOIS, statut="validee")
        with self.assertRaisesMessage(Exception, "JOURS_PAIE_MOIS"):
            preparer_bulletin(self.bulletin())

    def test_sans_contrat_en_vigueur_erreur_explicite(self):
        _auth(self.client, "rh@etls.local")
        b = self.bulletin(employe=self.employe2)
        r = self.client.post(f"{BASE}bulletins/{b.pk}/preparer/")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Aucun contrat actif", str(r.json()))

    def test_api_preparer(self):
        _auth(self.client, "rh@etls.local")
        b = self.bulletin()
        r = self.client.post(f"{BASE}bulletins/{b.pk}/preparer/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(Decimal(r.json()["brut"]), Decimal("300000"))
        _auth(self.client, "ouvrier@etls.local")  # hors cercle paie
        self.assertEqual(self.client.post(f"{BASE}bulletins/{b.pk}/preparer/").status_code, 403)


class ExpatrieEtImpotTests(M9aBase):
    def test_cotisation_exclue_pour_un_expatrie(self):
        BaremeCotisation.objects.create(code="CNSS-S", label="CNSS", organisme="CNSS", nature="salariale", taux=Decimal("5"), date_effet=date(2020, 1, 1), exclure_expatries=True)
        BaremeCotisation.objects.create(code="CNAMGS-S", label="CNAMGS", organisme="CNAMGS", nature="salariale", taux=Decimal("2"), date_effet=date(2020, 1, 1))
        self.contrat.type = ContratTravail.Type.EXPATRIE
        self.contrat.save()
        b = preparer_bulletin(self.bulletin())
        b.refresh_from_db()
        codes = self.lignes(b)
        self.assertNotIn("COT-CNSS-S", codes)
        self.assertEqual(codes["COT-CNAMGS-S"], Decimal("6000"))

    def test_abattement_plafonne_au_forfait_annuel(self):
        BaremeImpot.objects.create(
            code="IRPP", label="IRPP", tranches=[{"plafond": None, "taux": 10}], abattement_pct=Decimal("20"),
            abattement_plafond_annuel=Decimal("833333"), date_effet=date(2020, 1, 1),
        )
        self.contrat.salaire_base = Decimal("1000000")
        self.contrat.save()
        b = preparer_bulletin(self.bulletin())
        b.refresh_from_db()
        # 20 % de 1 000 000 = 200 000 > 833 333 / 12 = 69 444,42 : base 930 555,58, impôt 10 %
        self.assertEqual(self.lignes(b)["IMP-IRPP"], Decimal("93055.56"))


class DeclarationsFnhCfpTests(M9aBase):
    def test_declaration_fnh_ne_reprend_que_le_fnh(self):
        for code, org in (("FNH-P", "CNSS/DGI"), ("CFP-P", "DGI"), ("CNSS-P", "CNSS")):
            BaremeCotisation.objects.create(code=code, label=code, organisme=org, nature="patronale", taux=Decimal("2"), date_effet=date(2020, 1, 1))
        b = preparer_bulletin(self.bulletin())
        BulletinPaie.objects.filter(pk=b.pk).update(statut="valide")
        decl = generer_declaration("fnh", MOIS, MOIS)
        self.assertEqual(decl.total_patronal, Decimal("6000"))
        self.assertIn("contribution_patronale", decl.contenu)
        self.assertEqual(generer_declaration("cfp", MOIS, MOIS).total_patronal, Decimal("6000"))


class CarriereTests(M9aBase):
    def test_promotion_applique_la_grille_et_trace_avant_apres(self):
        g = GrilleSalaire.objects.create(categorie="cadre", classe="C2", echelon=1, salaire_base=Decimal("500000"), date_effet=date(2025, 1, 1))
        self.employe.categorie = "technicien"
        self.employe.save()
        _auth(self.client, "rh@etls.local")
        r = self.client.post(f"{BASE}carriere/", {
            "employe": str(self.employe.pk), "type": "promotion", "date_effet": "2026-03-01", "grille": str(g.pk),
            "fonction": "Chef de projet", "motif": "Décision DG",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        d = r.json()
        self.assertEqual((d["categorie_avant"], d["categorie_apres"]), ("technicien", "cadre"))
        self.assertEqual((Decimal(d["salaire_avant"]), Decimal(d["salaire_apres"])), (Decimal("300000"), Decimal("500000")))
        self.assertEqual(d["cree_par_email"], "rh@etls.local")
        self.contrat.refresh_from_db()
        self.assertEqual((self.contrat.grille_id, self.contrat.salaire_base), (g.pk, Decimal("500000")))
        ev = EvenementCarriere.objects.get()
        self.assertEqual(self.client.patch(f"{BASE}carriere/{ev.pk}/", {"motif": "x"}, format="json").status_code, 405)
        with self.assertRaises(Exception):
            ev.save()


class AbsencesApiTests(M9aBase):
    def test_saisie_validation_annulation(self):
        _auth(self.client, "rh@etls.local")
        r = self.client.post(f"{BASE}absences/", {
            "employe": str(self.employe.pk), "type": "autorisee_np", "date_debut": "2026-03-05", "date_fin": "2026-03-06",
            "statut": "validee", "valide_par": str(self.admin.pk),
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        a = r.json()
        self.assertEqual((a["statut"], a["valide_par"], a["remuneree"], a["nb_jours"]), ("saisie", None, False, 2))
        r = self.client.post(f"{BASE}absences/{a['id']}/valider/")
        self.assertEqual((r.status_code, r.json()["statut"]), (200, "validee"))
        self.assertEqual(str(r.json()["valide_par"]), str(self.rh.pk))
        self.assertEqual(self.client.post(f"{BASE}absences/{a['id']}/valider/").status_code, 400)
        BulletinPaie.objects.create(employe=self.employe, periode=MOIS, statut="valide")
        self.assertEqual(self.client.post(f"{BASE}absences/{a['id']}/annuler/").status_code, 400)

    def test_dates_incoherentes_400(self):
        _auth(self.client, "rh@etls.local")
        r = self.client.post(f"{BASE}absences/", {
            "employe": str(self.employe.pk), "type": "injustifiee", "date_debut": "2026-03-05", "date_fin": "2026-03-01",
        }, format="json")
        self.assertEqual(r.status_code, 400)

    def test_grille_reservee_au_cercle_paie_et_confirmable(self):
        _auth(self.client, "ouvrier@etls.local")
        self.assertEqual(self.client.get(f"{BASE}grilles-salaire/").status_code, 403)
        _auth(self.client, "rh@etls.local")
        r = self.client.post(f"{BASE}grilles-salaire/", {
            "categorie": "ouvrier", "classe": "O1", "echelon": 1, "salaire_base": "150000", "date_effet": "2026-01-01",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        gid = r.json()["id"]
        self.assertEqual(self.client.post(f"{BASE}grilles-salaire/{gid}/confirmer/").json()["statut_valeur"], "confirme")
        self.assertEqual(self.client.patch(f"{BASE}grilles-salaire/{gid}/", {"salaire_base": "1"}, format="json").status_code, 400)


class EcheancesDeclarationsTests(M9aBase):
    def test_seed_et_dates_limites(self):
        call_command("seed_baremes_legaux_provisoires")
        call_command("seed_baremes_legaux_provisoires")
        self.assertEqual(EcheanceDeclaration.objects.count(), 6)
        self.assertEqual(BaremeImpot.objects.get(code="IRPP").abattement_plafond_annuel, Decimal("833333"))
        dads = EcheanceDeclaration.objects.get(code="ECH-DADS")
        self.assertEqual(date_limite(dads, date(2025, 12, 1)), date(2026, 3, 31))
        cnamgs = EcheanceDeclaration.objects.get(code="ECH-CNAMGS")
        self.assertEqual(date_limite(cnamgs, date(2026, 9, 1)), date(2026, 10, 15))

    def test_calendrier_retard_depot_et_alertes(self):
        EcheanceDeclaration.objects.create(code="ECH-CNSS", libelle="CNSS", type_declaration="cnss", periodicite="mensuelle", jour=15)
        aujourdhui = date.today()
        mois_prec = (aujourdhui.replace(day=1) - timedelta(days=1)).replace(day=1)
        items = {i["periode_debut"]: i for i in calendrier_declarations()}
        self.assertIn(mois_prec, items)
        self.assertFalse(items[mois_prec]["deposee"])
        DeclarationSociale.objects.create(type="cnss", periode_debut=mois_prec, periode_fin=mois_prec, contenu="x", sha256="0")
        items = {i["periode_debut"]: i for i in calendrier_declarations()}
        self.assertTrue(items[mois_prec]["deposee"])

        from analytics.services import alertes_agregees

        codes = [a for a in alertes_agregees()["rh"] if a["type"] == "declaration_paie"]
        self.assertTrue(codes)
        self.assertFalse([a for a in codes if a["libelle"].endswith(f"période {mois_prec:%m/%Y}")])
        chef = User.objects.create_user(email="chefat@etls.local", password="Etls#Demo2026", role=User.Role.CHEF_ATELIER)
        self.assertFalse([a for a in alertes_agregees(chef)["rh"] if a["type"] == "declaration_paie"])
        _auth(self.client, "rh@etls.local")
        r = self.client.get(f"{BASE}echeances-declarations/calendrier/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json())
