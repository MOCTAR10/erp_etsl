"""Couche D — cubes OLAP à 6 axes archivés 10 ans (CDC Couche D §2.4 / §2.11) : tests de recette."""

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management import call_command

from analytics import cubes
from analytics.models import CubeArchive, CubeFait, ParametreCube
from commercial.models import Affaire
from controle_gestion.services import compute_marges
from controle_gestion.tests import BaseGestionTest
from referentiels.models import AnalyticAccount, AnalyticAxis

BASE = "/api/analytics/cubes/"


class CubeBase(BaseGestionTest):
    def setUp(self):
        super().setUp()
        self.axis_site, _ = AnalyticAxis.objects.get_or_create(
            code="AX-SITE", defaults={"label": "Site", "axis_type": AnalyticAxis.AxisType.SITE}
        )
        self.analytic_site, _ = AnalyticAccount.objects.get_or_create(
            axis=self.axis_site, code="SITE-PG", defaults={"label": "Port-Gentil"}
        )
        Affaire.objects.create(title="Maintenance pipelines", affaire_type="maintenance", analytic=self.analytic_aff)
        self._post_produit("5000000.00", analytic=self.analytic_aff, ref="C1")
        self._post_charge("1200000.00", analytic=self.analytic_aff, ref="C2")
        self._post_charge("400000.00", analytic=self.analytic_cc, ref="C3")
        self._post_charge("250000.00", analytic=self.analytic_site, ref="C4")
        self._post_charge_gr("300000.00", analytic=self.analytic_aff, ref="C5")
        self.client.force_authenticate(self.finance)


class AlimentationTests(CubeBase):
    def test_idempotente_et_egale_aux_marges(self):
        n1 = cubes.alimenter_cube("2026-01")
        n2 = cubes.alimenter_cube("2026-01")
        self.assertEqual((n1, n2), (3, 3))  # affaire, centre, site
        self.assertEqual(CubeFait.objects.count(), 3)
        regle = compute_marges(self._fy.pk)["totals"]
        lu = cubes.lire_cube(["2026-01"])["totaux"]
        self.assertEqual(Decimal(lu["produits"]), regle["produits"])
        self.assertEqual(Decimal(lu["charges"]), regle["charges"])
        self.assertEqual(Decimal(lu["cout_gr"]), regle["cout_gr"])

    def test_activite_derivee_de_l_affaire_et_618_isole(self):
        cubes.alimenter_cube("2026-01")
        f = CubeFait.objects.get(affaire="AFF-PIPE-001")
        self.assertEqual((f.activite, f.chantier, f.site, f.centre), ("maintenance", "", "", ""))
        self.assertEqual((f.produits, f.charges, f.cout_gr), (Decimal("5000000"), Decimal("1200000"), Decimal("300000")))

    def test_lecture_par_axe_et_filtre(self):
        cubes.alimenter_cube("2026-01")
        par_axe = cubes.lire_cube(["2026-01"], ("affaire", "centre", "site"))
        self.assertEqual(len(par_axe["rows"]), 3)
        par_activite = cubes.lire_cube(None, ("activite",), {"activite": "maintenance"})
        self.assertEqual([r["activite"] for r in par_activite["rows"]], ["maintenance"])
        self.assertEqual(par_activite["rows"][0]["marge"], "3800000.00")
        with self.assertRaises(ValueError):
            cubes.lire_cube(None, ("inconnu",))

    def test_periode_invalide(self):
        for p in ("2026-13", "2026", "abcd-ef", "2026-1"):
            with self.assertRaises(ValueError, msg=p):
                cubes.alimenter_cube(p)


class ArchiveTests(CubeBase):
    def test_archive_scellee_conservee_10_ans(self):
        a = cubes.archiver_cube("2026-01", self.finance, today=date(2026, 10, 18))
        self.assertEqual(a.conserve_jusqu_au, date(2036, 1, 31))
        self.assertEqual(a.nb_faits, 3)
        self.assertEqual(len(a.sha256), 64)
        self.assertTrue(cubes.verifier_archive(a))
        self.assertTrue(a.retention_provisoire)

    def test_immuable_non_supprimable_non_recalculable(self):
        a = cubes.archiver_cube("2026-01", self.finance, today=date(2026, 10, 18))
        a.nb_faits = 99
        with self.assertRaises(ValidationError):
            a.save()
        with self.assertRaises(ValidationError):
            a.delete()
        with self.assertRaises(ValueError):
            cubes.alimenter_cube("2026-01")
        with self.assertRaises(ValueError):
            cubes.archiver_cube("2026-01", self.finance, today=date(2026, 10, 18))

    def test_falsification_detectee(self):
        a = cubes.archiver_cube("2026-01", self.finance, today=date(2026, 10, 18))
        CubeArchive.objects.filter(pk=a.pk).update(faits=[])  # altération directe en base
        a.refresh_from_db()
        self.assertFalse(cubes.verifier_archive(a))

    def test_periode_non_terminee_refusee(self):
        with self.assertRaises(ValueError):
            cubes.archiver_cube("2026-10", self.finance, today=date(2026, 10, 18))

    def test_lecture_depuis_l_archive(self):
        cubes.archiver_cube("2026-01", self.finance, today=date(2026, 10, 18))
        CubeFait.objects.all().delete()
        lu = cubes.lire_cube(["2026-01"], ("affaire",))
        self.assertEqual(lu["periodes_archivees"], ["2026-01"])
        self.assertEqual(Decimal(lu["totaux"]["produits"]), Decimal("5000000"))

    def test_duree_parametrable_et_avertissement(self):
        cubes.get_param_cube("RETENTION_ANS")
        ParametreCube.objects.filter(code="RETENTION_ANS").update(valeur=Decimal("15"), statut_valeur="confirme")
        a = cubes.archiver_cube("2026-01", self.finance, today=date(2026, 10, 18))
        self.assertEqual(a.conserve_jusqu_au, date(2041, 1, 31))
        self.assertFalse(a.retention_provisoire)


class ApiTests(CubeBase):
    def test_flux_complet_api(self):
        r = self.client.post(BASE + "alimenter/", {"periode": "2026-01"}, format="json")
        self.assertEqual((r.status_code, r.json()["faits"]), (200, 3), r.content)
        r = self.client.get(BASE + "?periode=2026-01&axes=affaire,activite")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["parametres_provisoires"])
        r = self.client.post(BASE + "archives/archiver/", {"periode": "2026-01"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.json()["integre"])
        self.assertEqual(self.client.get(BASE + "archives/2026-01/").status_code, 200)
        self.assertEqual(self.client.post(BASE + "alimenter/", {"periode": "2026-01"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(BASE + "archives/archiver/", {"periode": "2026-01"}, format="json").status_code, 400)

    def test_archives_en_lecture_seule(self):
        cubes.archiver_cube("2026-01", self.finance, today=date(2026, 10, 18))
        for methode in (self.client.patch, self.client.put, self.client.delete):
            self.assertEqual(methode(BASE + "archives/2026-01/", {}, format="json").status_code, 405)

    def test_droits(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(BASE).status_code, (401, 403))
        self.client.force_authenticate(self.logistique)
        self.assertEqual(self.client.get(BASE).status_code, 403)
        self.assertEqual(self.client.post(BASE + "alimenter/", {"periode": "2026-01"}, format="json").status_code, 403)
        self.assertEqual(self.client.get(BASE + "archives/").status_code, 403)
        self.client.force_authenticate(self.comptable)
        self.assertEqual(self.client.get(BASE).status_code, 200)

    def test_parametre_provisoire_puis_confirme(self):
        r = self.client.get(BASE + "parametres/")
        self.assertEqual(r.status_code, 200, r.content)
        rows = r.json() if isinstance(r.json(), list) else r.json()["results"]
        p = next(x for x in rows if x["code"] == "RETENTION_ANS")
        self.assertEqual((p["code"], p["est_provisoire"]), ("RETENTION_ANS", True))
        # Harmonisation : la Finance modifie, la Direction confirme.
        self.assertEqual(self.client.post(f"{BASE}parametres/{p['id']}/confirmer/").status_code, 403)
        from users.models import User

        self.client.force_authenticate(User.objects.create_user(email="pdg-cube@etls.ga", password="x-Cube-2026", role=User.Role.PDG))
        r = self.client.post(f"{BASE}parametres/{p['id']}/confirmer/")
        self.assertEqual((r.status_code, r.json()["est_provisoire"]), (200, False))
        self.client.force_authenticate(self.finance)
        r = self.client.patch(f"{BASE}parametres/{p['id']}/", {"valeur": "12"}, format="json")
        self.assertEqual((r.status_code, r.json()["est_provisoire"]), (200, True))
        self.assertEqual(self.client.patch(f"{BASE}parametres/{p['id']}/", {"valeur": "0"}, format="json").status_code, 400)

    def test_tache_quotidienne(self):
        from analytics.tasks import alimenter_cubes

        call_command("setup_beat_schedule")
        from django_celery_beat.models import PeriodicTask

        self.assertTrue(PeriodicTask.objects.filter(task="analytics.tasks.alimenter_cubes").exists())
        self.assertIsInstance(alimenter_cubes(), int)
