"""Clôture M4 Logistique & GLOBAL RENTAL — tests de recette (CDC M4 §12.11).

Critères :
- BC / GR émis et validés automatiquement (contrôles bloquants, numérotation, attestation côté serveur) ;
- compteurs ventilés par affaire vers M11 (marge GR), compte 618 isolé, partenaire GLOBAL RENTAL obligatoire ;
- formule glissante des compteurs (fenêtre et horizon paramétrables, valeurs provisoires tant que non confirmées) ;
- seuil compteur → OT M8 et tarification versionnée + pénalités : déjà couverts (test_tarifs_gr.py, maintenance).
"""

from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from accounting_kernel.models import AccountMove, FiscalYear
from commercial.models import Affaire
from users.models import User

from .models import EquipementParc, LectureCompteur, LocationGR, ParametreLogistique
from .services import (
    PARAMETRES_DEFAUT,
    compteur_glissant,
    get_param_logistique,
    ventilation_gr,
)
from .tests import _gr_partner, _non_gr_partner


def _user(email, role):
    return User.objects.create_user(email=email, password="x-Audit-2026", role=role)


class _Base(APITestCase):
    def setUp(self):
        self.logi = _user("logi@etls.ga", User.Role.LOGISTIQUE)
        self.dop = _user("dop@etls.ga", User.Role.DIRECTEUR_OPERATIONS)
        self.rh = _user("rh@etls.ga", User.Role.RH)
        self.partner = _gr_partner()
        self.grue = EquipementParc.objects.create(label="Grue 25t", categorie="levage", is_global_rental=True)
        self.client.force_authenticate(self.logi)

    def location(self, equipement=None, **kw):
        body = {"partenaire": self.partner, "equipement": equipement or self.grue, "periodicite": "heure",
                "tarif": Decimal("1000"), "date_debut": date(2026, 9, 1), "date_fin": date(2026, 9, 30)}
        body.update(kw)
        return LocationGR.objects.create(**body)


class EmissionBcGrTests(_Base):
    def emettre(self, loc):
        return self.client.post(f"/api/logistique/locations/{loc.pk}/emettre/", {}, format="json")

    def test_emission_numerote_bc_et_gr_et_atteste_cote_serveur(self):
        loc = self.location()
        r = self.emettre(loc)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data["reference_bc"].startswith("BCG"))
        self.assertTrue(r.data["reference_gr"].startswith("GRG"))
        self.assertEqual(r.data["emis_par"], self.logi.pk)
        self.assertIsNotNone(r.data["emis_le"])

    def test_emission_garde_les_references_deja_recues_de_gr(self):
        loc = self.location(reference_bc="BCI-GR-77")
        r = self.emettre(loc)
        self.assertEqual(r.data["reference_bc"], "BCI-GR-77")

    def test_attestation_non_modifiable_par_patch(self):
        loc = self.location()
        r = self.client.patch(f"/api/logistique/locations/{loc.pk}/",
                              {"emis_par": self.dop.pk, "emis_le": "2020-01-01T00:00:00Z"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        loc.refresh_from_db()
        self.assertIsNone(loc.emis_par_id)
        self.assertIsNone(loc.emis_le)

    def test_double_emission_refusee(self):
        loc = self.location()
        self.assertEqual(self.emettre(loc).status_code, 200)
        self.assertEqual(self.emettre(loc).status_code, 400)

    def test_validation_auto_equipement_indisponible(self):
        self.grue.statut = EquipementParc.Statut.MAINTENANCE
        self.grue.save()
        r = self.emettre(self.location())
        self.assertEqual(r.status_code, 400)
        self.assertIn("maintenance", str(r.data).lower())

    def test_validation_auto_sans_tarif(self):
        r = self.emettre(self.location(tarif=Decimal("0")))
        self.assertEqual(r.status_code, 400)
        self.assertIn("tarif", str(r.data).lower())

    def test_validation_auto_sans_date_debut(self):
        r = self.emettre(self.location(date_debut=None))
        self.assertEqual(r.status_code, 400)

    def test_validation_auto_imputation_618_obligatoire(self):
        r = self.emettre(self.location(imputation_618=False))
        self.assertEqual(r.status_code, 400)
        self.assertIn("618", str(r.data))

    def test_validation_auto_deja_en_location_active(self):
        autre = self.location()
        autre.statut = LocationGR.Statut.ACTIVE
        autre.save()
        r = self.emettre(self.location())
        self.assertEqual(r.status_code, 400)
        self.assertIn("déjà", str(r.data).lower())

    def test_demarrer_emet_automatiquement(self):
        loc = self.location()
        r = self.client.post(f"/api/logistique/locations/{loc.pk}/demarrer/", {"lecture_initiale": 100}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        loc.refresh_from_db()
        self.assertTrue(loc.reference_bc.startswith("BCG"))
        self.assertEqual(loc.emis_par_id, self.logi.pk)

    def test_demarrer_bloque_si_validation_echoue(self):
        self.grue.statut = EquipementParc.Statut.HORS_SERVICE
        self.grue.save()
        loc = self.location()
        r = self.client.post(f"/api/logistique/locations/{loc.pk}/demarrer/", {"lecture_initiale": 100}, format="json")
        self.assertEqual(r.status_code, 400)
        loc.refresh_from_db()
        self.assertEqual(loc.statut, LocationGR.Statut.BROUILLON)

    def test_emission_reservee_aux_roles_logistique(self):
        self.client.force_authenticate(self.rh)
        self.assertEqual(self.emettre(self.location()).status_code, 403)

    def test_partenaire_non_gr_toujours_refuse(self):
        r = self.client.post("/api/logistique/locations/", {
            "partenaire": _non_gr_partner().pk, "equipement": str(self.grue.pk), "periodicite": "heure", "tarif": "10",
        }, format="json")
        self.assertEqual(r.status_code, 400)


class ParametresLogistiqueTests(_Base):
    def test_defauts_provisoires_crees_a_la_volee(self):
        r = self.client.get("/api/logistique/parametres/")
        self.assertEqual(r.status_code, 200)
        codes = {p["code"] for p in r.data["results"]} if "results" in r.data else {p["code"] for p in r.data}
        self.assertEqual(codes, set(PARAMETRES_DEFAUT))
        self.assertFalse(ParametreLogistique.objects.exclude(statut_valeur="provisoire").exists())

    def test_modifier_puis_confirmer(self):
        get_param_logistique("COMPTEUR_FENETRE_JOURS")
        p = ParametreLogistique.objects.get(code="COMPTEUR_FENETRE_JOURS")
        r = self.client.patch(f"/api/logistique/parametres/{p.pk}/", {"valeur": "14"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(get_param_logistique("COMPTEUR_FENETRE_JOURS"), Decimal("14"))
        # la confirmation est réservée à la direction des opérations / direction
        self.assertEqual(self.client.post(f"/api/logistique/parametres/{p.pk}/confirmer/").status_code, 403)
        self.client.force_authenticate(self.dop)
        r = self.client.post(f"/api/logistique/parametres/{p.pk}/confirmer/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["statut_valeur"], "confirme")
        self.assertEqual(r.data["confirme_par"], self.dop.pk)

    def test_valeur_modifiee_redevient_provisoire(self):
        get_param_logistique("COMPTEUR_HORIZON_JOURS")
        p = ParametreLogistique.objects.get(code="COMPTEUR_HORIZON_JOURS")
        self.client.force_authenticate(self.dop)
        self.client.post(f"/api/logistique/parametres/{p.pk}/confirmer/")
        self.client.patch(f"/api/logistique/parametres/{p.pk}/", {"valeur": "45"}, format="json")
        p.refresh_from_db()
        self.assertEqual(p.statut_valeur, "provisoire")

    def test_valeur_negative_ou_nulle_refusee(self):
        get_param_logistique("JOURS_PAR_MOIS")
        p = ParametreLogistique.objects.get(code="JOURS_PAR_MOIS")
        r = self.client.patch(f"/api/logistique/parametres/{p.pk}/", {"valeur": "0"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_creation_interdite_et_lecture_fermee_au_non_autorise(self):
        self.assertEqual(self.client.post("/api/logistique/parametres/", {"code": "X", "valeur": "1"}, format="json").status_code, 405)
        self.client.force_authenticate(None)
        self.assertIn(self.client.get("/api/logistique/parametres/").status_code, (401, 403))


class CompteurGlissantTests(_Base):
    def active(self):
        loc = self.location(lecture_initiale=Decimal("100"), statut=LocationGR.Statut.ACTIVE)
        for jour, valeur in ((15, "160"), (30, "220")):
            LectureCompteur.objects.create(location=loc, date=date(2026, 9, jour), valeur=Decimal(valeur))
        return loc

    def test_taux_et_projection_sur_la_fenetre(self):
        r = compteur_glissant(self.active(), aujourdhui=date(2026, 9, 30))
        self.assertEqual(r["fenetre_jours"], 30)
        self.assertEqual(r["consommation_fenetre"], Decimal("120.00"))
        self.assertEqual(r["taux_jour"], Decimal("4.14"))  # 120 j / 29 jours écoulés depuis le départ (1er → 30)
        self.assertEqual(r["horizon_jours"], 30)
        self.assertEqual(r["projection_valeur"], Decimal("220") + Decimal("4.14") * 30)
        self.assertTrue(r["provisoire"])

    def test_fenetre_parametrable_sans_developpeur(self):
        loc = self.active()
        p = ParametreLogistique.objects.get_or_create(code="COMPTEUR_FENETRE_JOURS", defaults={
            "label": "x", "valeur": 10, "unite": "jours"})[0]
        p.valeur = Decimal("15")
        p.save()
        r = compteur_glissant(loc, aujourdhui=date(2026, 9, 30))
        self.assertEqual(r["fenetre_jours"], 15)
        self.assertEqual(r["consommation_fenetre"], Decimal("60.00"))
        self.assertEqual(r["taux_jour"], Decimal("4.00"))

    def test_sans_releve_ni_depart_pas_de_projection(self):
        r = compteur_glissant(self.location(), aujourdhui=date(2026, 9, 30))
        self.assertIsNone(r["taux_jour"])
        self.assertIsNone(r["projection_valeur"])

    def test_confirme_quand_tous_les_parametres_sont_confirmes(self):
        for code in ("COMPTEUR_FENETRE_JOURS", "COMPTEUR_HORIZON_JOURS"):
            get_param_logistique(code)
        ParametreLogistique.objects.update(statut_valeur="confirme")
        self.assertFalse(compteur_glissant(self.active(), aujourdhui=date(2026, 9, 30))["provisoire"])

    def test_endpoint_glissant(self):
        loc = self.active()
        r = self.client.get(f"/api/logistique/locations/{loc.pk}/glissant/?date=2026-09-30")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(str(r.data["consommation_fenetre"]), "120.00")
        self.assertTrue(r.data["provisoire"])


class VentilationAffaireTests(_Base):
    def setUp(self):
        super().setUp()
        self.aff_a = Affaire.objects.create(title="Affaire A")
        self.aff_a.assurer_compte_analytique()
        self.aff_b = Affaire.objects.create(title="Affaire B")
        self.aff_b.assurer_compte_analytique()
        self.nacelle = EquipementParc.objects.create(label="Nacelle", categorie="levage", is_global_rental=True)

    def lecture(self, loc, jour, valeur):
        LectureCompteur.objects.create(location=loc, date=jour, valeur=Decimal(valeur))

    def test_cout_a_l_heure_ventile_par_affaire(self):
        a = self.location(affaire=self.aff_a, lecture_initiale=Decimal("100"), statut=LocationGR.Statut.ACTIVE)
        self.lecture(a, date(2026, 9, 30), "220")
        b = self.location(equipement=self.nacelle, affaire=self.aff_b, tarif=Decimal("500"),
                          lecture_initiale=Decimal("0"), statut=LocationGR.Statut.ACTIVE)
        self.lecture(b, date(2026, 9, 30), "40")
        rows = {r["affaire"]: r for r in ventilation_gr("2026-09")["rows"]}
        self.assertEqual(rows[self.aff_a.code]["cout_gr"], Decimal("120000.00"))  # 120 h × 1000
        self.assertEqual(rows[self.aff_b.code]["cout_gr"], Decimal("20000.00"))  # 40 h × 500
        self.assertEqual(rows[self.aff_a.code]["analytic"], self.aff_a.analytic_id)
        self.assertEqual(rows[self.aff_a.code]["compte"], "618000")

    def test_consommation_limitee_au_mois(self):
        loc = self.location(affaire=self.aff_a, lecture_initiale=Decimal("100"), statut=LocationGR.Statut.ACTIVE,
                            date_fin=date(2026, 10, 31))
        self.lecture(loc, date(2026, 9, 30), "220")
        self.lecture(loc, date(2026, 10, 31), "400")
        sept = {r["affaire"]: r for r in ventilation_gr("2026-09")["rows"]}
        octo = {r["affaire"]: r for r in ventilation_gr("2026-10")["rows"]}
        self.assertEqual(sept[self.aff_a.code]["consommation"], Decimal("120.00"))
        self.assertEqual(octo[self.aff_a.code]["consommation"], Decimal("180.00"))

    def test_jour_et_mois_et_forfait(self):
        j = self.location(affaire=self.aff_a, periodicite="jour", tarif=Decimal("100"),
                          date_debut=date(2026, 9, 1), date_fin=date(2026, 9, 10), statut=LocationGR.Statut.ACTIVE)
        m = self.location(equipement=self.nacelle, affaire=self.aff_b, periodicite="mois", tarif=Decimal("3000"),
                          date_debut=date(2026, 9, 1), date_fin=date(2026, 9, 15), statut=LocationGR.Statut.ACTIVE)
        rows = {r["affaire"]: r for r in ventilation_gr("2026-09")["rows"]}
        self.assertEqual(rows[self.aff_a.code]["cout_gr"], Decimal("1000.00"))  # 10 jours
        self.assertEqual(rows[self.aff_b.code]["cout_gr"], Decimal("1500.00"))  # 15 j / 30 j par mois
        self.assertIsNotNone(j) and self.assertIsNotNone(m)

    def test_jours_par_mois_parametrable(self):
        self.location(affaire=self.aff_b, periodicite="mois", tarif=Decimal("3000"), date_debut=date(2026, 9, 1),
                      date_fin=date(2026, 9, 15), statut=LocationGR.Statut.ACTIVE)
        get_param_logistique("JOURS_PAR_MOIS")
        ParametreLogistique.objects.filter(code="JOURS_PAR_MOIS").update(valeur=Decimal("25"))
        rows = {r["affaire"]: r for r in ventilation_gr("2026-09")["rows"]}
        self.assertEqual(rows[self.aff_b.code]["cout_gr"], Decimal("1800.00"))  # 15 / 25 × 3000
        self.assertTrue(ventilation_gr("2026-09")["provisoire"])

    def test_penalite_comptee_le_mois_du_retour(self):
        self.location(affaire=self.aff_a, statut=LocationGR.Statut.TERMINEE, lecture_initiale=Decimal("0"),
                      lecture_finale=Decimal("10"), date_retour=date(2026, 10, 3), jours_retard=3,
                      penalite=Decimal("9000"), date_fin=date(2026, 9, 30))
        sept = {r["affaire"]: r for r in ventilation_gr("2026-09")["rows"]}
        octo = {r["affaire"]: r for r in ventilation_gr("2026-10")["rows"]}
        self.assertEqual(sept[self.aff_a.code]["penalites"], Decimal("0.00"))
        self.assertEqual(octo[self.aff_a.code]["penalites"], Decimal("9000.00"))

    def test_sans_affaire_et_brouillon_annulee_exclus(self):
        self.location(statut=LocationGR.Statut.ACTIVE, lecture_initiale=Decimal("0"))
        self.location(equipement=self.nacelle, affaire=self.aff_a, statut=LocationGR.Statut.ANNULEE)
        res = ventilation_gr("2026-09")
        self.assertEqual([r["affaire"] for r in res["rows"]], [None])  # sans affaire = ligne « non affecté »
        self.assertTrue(res["rows"][0]["non_affecte"])

    def test_618_isole_aucune_ecriture_creee(self):
        self.location(affaire=self.aff_a, lecture_initiale=Decimal("0"), statut=LocationGR.Statut.ACTIVE)
        avant = AccountMove.objects.count()
        ventilation_gr("2026-09")
        self.assertEqual(AccountMove.objects.count(), avant)

    def test_periode_invalide(self):
        r = self.client.get("/api/controle-gestion/gr-affaires/?periode=2026-13")
        self.assertIn(r.status_code, (400, 403))

    def test_endpoint_m11_marge_apres_gr(self):
        loc = self.location(affaire=self.aff_a, lecture_initiale=Decimal("100"), statut=LocationGR.Statut.ACTIVE)
        self.lecture(loc, date(2026, 9, 30), "220")
        fy = FiscalYear.objects.create(year=2026, start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.client.force_authenticate(_user("finance@etls.ga", User.Role.FINANCE))
        r = self.client.get(f"/api/controle-gestion/gr-affaires/?periode=2026-09&fiscal_year={fy.pk}")
        self.assertEqual(r.status_code, 200, r.content)
        row = next(x for x in r.data["rows"] if x["affaire"] == self.aff_a.code)
        self.assertEqual(row["cout_gr"], "120000.00")
        self.assertEqual(row["marge_hors_gr"], "0.00")
        self.assertEqual(row["marge_apres_gr"], "-120000.00")
        self.assertTrue(r.data["provisoire"])
        self.assertEqual(r.data["compte"], "618000")

    def test_endpoint_refuse_aux_anonymes_et_chef_service(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.get("/api/controle-gestion/gr-affaires/?periode=2026-09").status_code, (401, 403))
        self.client.force_authenticate(_user("cs@etls.ga", User.Role.CHEF_SERVICE))
        self.assertEqual(self.client.get("/api/controle-gestion/gr-affaires/?periode=2026-09").status_code, 403)
