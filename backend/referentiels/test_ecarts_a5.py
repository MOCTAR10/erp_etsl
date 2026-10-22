"""Lot a5 : multi-sites (EX-G-03) et suites des rôles a4 (CG : montants M11 ; chargé d'affaires : saisie M1)."""

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from commercial.models import Affaire
from commercial.services import COMM_WRITE_ROLES
from controle_gestion.services import GESTION_AMOUNT_ROLES, can_see_amount
from operations.models import OrdreFabrication
from rh_paie.models import Employe
from stocks.models import Depot
from users.models import User
from users.parametres import get_param_transverse

from .models import Site
from .sites import meilleur_site, mots_cles, site_pour_texte


class _Base(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.pog = Site.objects.get(code="POG-ATELIER")
        self.pog_depot = Site.objects.get(code="POG-DEPOT")
        self.lbv_base = Site.objects.get(code="LBV-BASE")

    def _user(self, role, **kw):
        return User.objects.create_user(email=f"{role}{len(kw)}@a5.local", password="x" * 12, role=role, **kw)


class SitesReferentielTests(_Base):
    def test_sites_provisoires_par_defaut(self):
        codes = set(Site.objects.values_list("code", flat=True))
        self.assertTrue({"LBV-SIEGE", "LBV-BASE", "POG-ATELIER", "POG-DEPOT", "CHANTIERS"} <= codes)
        self.assertTrue(all(s.est_provisoire for s in Site.objects.all()))

    def test_reconnaissance_du_texte_libre(self):
        self.assertEqual(site_pour_texte("Dépôt Port-Gentil"), self.pog_depot.pk)  # mot-clé le plus long
        self.assertEqual(site_pour_texte("Port-Gentil"), self.pog.pk)
        self.assertEqual(site_pour_texte("Base Libreville"), self.lbv_base.pk)
        self.assertEqual(site_pour_texte("Zone Industrielle d'Owendo"), self.lbv_base.pk)
        self.assertEqual(site_pour_texte("Chantier RTC"), Site.objects.get(code="CHANTIERS").pk)
        self.assertIsNone(site_pour_texte("Inconnu"))
        self.assertIsNone(site_pour_texte(""))
        # Mot entier seulement : « ateliers » ne déclenche pas « atelier ».
        self.assertIsNone(meilleur_site("ateliers divers", [(1, mots_cles("X", "atelier", ""))]))

    def test_rattachement_automatique_et_heritage_of(self):
        d = Depot.objects.create(code="DEP-A5", label="Magasin A5", site="Base Libreville")
        self.assertEqual(d.site_etsl_id, self.lbv_base.pk)
        e = Employe.objects.create(nom="Test", prenom="A5", site="Port-Gentil")
        self.assertEqual(e.site_etsl_id, self.pog.pk)
        a = Affaire.objects.create(title="Affaire A5", site_etsl=self.pog)
        of = OrdreFabrication.objects.create(label="OF A5", affaire=a)
        self.assertEqual(of.site_etsl_id, self.pog.pk)

    def test_api_droits_confirmation_et_doublon(self):
        hse = self._user("hse")
        self.client.force_authenticate(hse)
        self.assertEqual(self.client.get("/api/referentiels/sites/").status_code, 200)
        self.assertEqual(self.client.post("/api/referentiels/sites/", {"code": "X", "libelle": "X"}, format="json").status_code, 403)
        self.client.force_authenticate(self._user("pdg"))
        r = self.client.post("/api/referentiels/sites/", {"code": "lbv-atl", "libelle": "Atelier Libreville", "type_site": "atelier",
                                                          "ville": "Libreville", "alias": "atelier libreville"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["code"], "LBV-ATL")
        self.assertTrue(r.json()["est_provisoire"])
        sid = r.json()["id"]
        self.assertEqual(self.client.post("/api/referentiels/sites/", {"code": "Lbv-Atl", "libelle": "Doublon"}, format="json").status_code, 400)
        r = self.client.post(f"/api/referentiels/sites/{sid}/confirmer/")
        self.assertEqual(r.json()["statut_valeur"], "confirme")
        r = self.client.patch(f"/api/referentiels/sites/{sid}/", {"alias": "atelier lbv"}, format="json")
        self.assertTrue(r.json()["est_provisoire"])  # une modification repasse en provisoire
        self.assertEqual(self.client.patch(f"/api/referentiels/sites/{sid}/", {"statut_valeur": "confirme"}, format="json").json()["statut_valeur"],
                         "provisoire")
        self.assertEqual(self.client.delete(f"/api/referentiels/sites/{sid}/").status_code, 405)

    def test_repartition_et_rattachement_a_posteriori(self):
        Depot.objects.create(code="DEP-A5B", label="Magasin", site="Port-Gentil")
        Depot.objects.create(code="DEP-A5C", label="Magasin", site="Ailleurs")
        self.client.force_authenticate(self._user("admin"))
        data = self.client.get("/api/referentiels/sites/repartition/").json()
        lignes = {ligne["code"]: ligne for ligne in data["lignes"]}
        self.assertGreaterEqual(lignes["POG-ATELIER"]["depots"], 1)
        self.assertGreaterEqual(lignes[""]["depots"], 1)  # non rattachés
        self.assertFalse(data["restriction"]["active"])
        # Nouveau mot-clé puis « Rattacher » : le texte « Ailleurs » est reconnu.
        self.client.patch(f"/api/referentiels/sites/{self.pog_depot.pk}/", {"alias": "ailleurs"}, format="json")
        r = self.client.post("/api/referentiels/sites/rattacher/")
        self.assertGreaterEqual(r.json()["rattaches"]["depots"], 1)
        self.assertEqual(Depot.objects.get(code="DEP-A5C").site_etsl_id, self.pog_depot.pk)


class FiltreEtRestrictionTests(_Base):
    def setUp(self):
        super().setUp()
        self.d_pog = Depot.objects.create(code="DEP-POG", label="Magasin POG", site_etsl=self.pog)
        self.d_lbv = Depot.objects.create(code="DEP-LBV", label="Magasin LBV", site_etsl=self.lbv_base)
        self.d_libre = Depot.objects.create(code="DEP-LIB", label="Magasin non rattaché")

    def _codes(self, url):
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200, r.content[:200])
        return {d["code"] for d in r.json()["results"]}

    def test_filtre_par_site_sur_les_listes(self):
        self.client.force_authenticate(self._user("admin"))
        self.assertEqual(self._codes(f"/api/stocks/depots/?site_etsl={self.pog.pk}") & {"DEP-POG", "DEP-LBV", "DEP-LIB"}, {"DEP-POG"})
        self.assertEqual(self.client.get("/api/stocks/depots/?site_etsl=abc").status_code, 400)
        defs = self.client.get("/api/stocks/depots/filtres/").json()["results"]
        site = next(d for d in defs if d["champ"] == "site_etsl")
        self.assertEqual(site["type"], "fk")
        self.assertIn(str(self.pog.pk), {c["valeur"] for c in site["choix"]})
        for url in ("/api/logistique/equipements/", "/api/maintenance/actifs/", "/api/rh-paie/employes/",
                    "/api/commercial/affaires/", "/api/operations/ordres/"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(f"{url}?site_etsl={self.pog.pk}").status_code, 200)
                self.assertEqual(self.client.get(f"{url}filtres/").status_code, 200)

    def test_restriction_de_lecture_par_site_parametrable(self):
        logi = self._user("logistique", site_etsl=self.pog)
        self.client.force_authenticate(logi)
        tous = {"DEP-POG", "DEP-LBV", "DEP-LIB"}
        self.assertEqual(self._codes("/api/stocks/depots/?page_size=100") & tous, tous)  # désactivée par défaut
        p = get_param_transverse("SITES_LECTURE_RESTREINTE")
        self.assertEqual(p.valeur, Decimal("0"))
        self.assertTrue(p.est_provisoire)
        p.valeur = Decimal("1")
        p.save()
        self.assertEqual(self._codes("/api/stocks/depots/?page_size=100") & tous, {"DEP-POG", "DEP-LIB"})
        self.assertEqual(self.client.get(f"/api/stocks/depots/{self.d_lbv.pk}/").status_code, 404)
        # Compte sans site, ou rôle « tous sites » : aucune limite.
        self.client.force_authenticate(self._user("logistique"))
        self.assertEqual(self._codes("/api/stocks/depots/?page_size=100") & tous, tous)
        self.client.force_authenticate(self._user("pdg", site_etsl=self.pog))
        self.assertEqual(self._codes("/api/stocks/depots/?page_size=100") & tous, tous)

    def test_parametre_booleen_valide(self):
        self.client.force_authenticate(self._user("pdg"))
        p = get_param_transverse("SITES_LECTURE_RESTREINTE")
        self.assertEqual(self.client.patch(f"/api/users/parametres/{p.pk}/", {"valeur": "2"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(f"/api/users/parametres/{p.pk}/", {"valeur": "1"}, format="json").status_code, 200)

    def test_site_de_rattachement_du_compte(self):
        admin = self._user("admin")
        cible = self._user("hse")
        self.client.force_authenticate(admin)
        r = self.client.patch(f"/api/users/users/{cible.pk}/", {"site_etsl": self.pog.pk}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["site_etsl_code"], "POG-ATELIER")
        cible.refresh_from_db()
        self.client.force_authenticate(cible)
        me = self.client.get("/api/users/me/").json()
        self.assertEqual(me["site_etsl_code"], "POG-ATELIER")
        # Le compte ne change pas lui-même son site (lecture seule sur /me).
        self.client.patch("/api/users/me/", {"site_etsl": self.lbv_base.pk}, format="json")
        cible.refresh_from_db()
        self.assertEqual(cible.site_etsl_id, self.pog.pk)


class RolesA4SuitesTests(_Base):
    def test_cg_voit_les_montants_et_charge_affaires_saisit_en_m1(self):
        self.assertIn(User.Role.CONTROLEUR_GESTION, GESTION_AMOUNT_ROLES)
        self.assertTrue(can_see_amount(self._user("controleur_gestion")))
        self.assertIn(User.Role.CHARGE_AFFAIRES, COMM_WRITE_ROLES)
        ca = self._user("charge_affaires")
        self.client.force_authenticate(ca)
        r = self.client.post("/api/commercial/affaires/", {}, format="json")
        self.assertEqual(r.status_code, 400, r.content[:200])  # droit accordé : seule la validation refuse

    def test_liste_des_roles_pour_les_circuits(self):
        self.client.force_authenticate(self._user("hse"))
        roles = {r["role"] for r in self.client.get("/api/users/roles/").json()["results"]}
        self.assertTrue({"charge_affaires", "controleur_gestion", "pdg"} <= roles)
        self.client.force_authenticate(None)
        self.assertIn(self.client.get("/api/users/roles/").status_code, (401, 403))
