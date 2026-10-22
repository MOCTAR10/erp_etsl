"""Écarts M6 (lot ecarts-m6m7) — tests de recette.

- M6.1-09 : un contrôle confié à un organisme agréé cite un organisme du référentiel, agréé à la date du contrôle
  et pour la méthode CND (paramètre provisoire CND_ORGANISME_REFERENTIEL).
- WPS / profil M1.3 : WPS requis par profil contractuel (ou par contrat) ; un contrôle, une diffusion sur OF ou un
  joint soudé avec un WPS non prévu est refusé (paramètre provisoire WPS_PROFIL_BLOQUANT) ; état de couverture.
"""

from datetime import date, timedelta

from rest_framework.test import APITestCase

from commercial.models import Affaire, Contract
from operations.models import OrdreFabrication
from users.models import User

from .ecarts import get_param_qualite
from .models import ControleQualite, OrganismeAgree, ParametreQualite, WpsRequis, WpsWpqr


def _user(role):
    return User.objects.create_user(email=f"{role}@m6m7.test", password="x-Audit-2026", role=role)


class _Base(APITestCase):
    def setUp(self):
        self.qaqc = _user(User.Role.QAQC)
        self.client.force_authenticate(self.qaqc)
        self.affaire = Affaire.objects.create(title="Pipeline M6M7")

    def controle(self, **data):
        corps = {"type_controle": "cnd", "methode_cnd": "UT", "point_controle": "Joint 1", "date_controle": str(date.today())}
        corps.update(data)
        return self.client.post("/api/qualite/controles/", corps, format="json")


class OrganismeAgreeTests(_Base):
    def organisme(self, **kw):
        valeurs = {"nom": "Bureau CND Gabon", "numero_agrement": "AGR-77", "methodes": "RT,UT",
                   "date_fin_validite": date.today() + timedelta(days=200)}
        valeurs.update(kw)
        return OrganismeAgree.objects.create(**valeurs)

    def test_referentiel_cree_a_l_ecran_et_methodes_controlees(self):
        r = self.client.post("/api/qualite/organismes-agrees/", {
            "nom": "Apave Gabon", "numero_agrement": "MIN-123", "methodes": "ut, rt",
            "date_fin_validite": str(date.today() + timedelta(days=365)),
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual((r.data["methodes"], r.data["valide"]), ("UT,RT", True))
        r = self.client.post("/api/qualite/organismes-agrees/", {
            "nom": "X", "numero_agrement": "1", "methodes": "XX", "date_fin_validite": str(date.today()),
        }, format="json")
        self.assertEqual(r.status_code, 400)
        # Écriture réservée au cercle de validation qualité ; suppression interdite (désactivation).
        self.client.force_authenticate(_user(User.Role.CHEF_ATELIER))
        self.assertEqual(self.client.post("/api/qualite/organismes-agrees/", {}).status_code, 403)
        self.client.force_authenticate(self.qaqc)
        self.assertEqual(self.client.delete(f"/api/qualite/organismes-agrees/{self.organisme().pk}/").status_code, 405)

    def test_controle_agree_exige_organisme_valide_et_methode_couverte(self):
        r = self.controle(organisme="agrege", organisme_libelle="Libre")
        self.assertEqual(r.status_code, 400)
        self.assertIn("organisme_agree", r.data)
        expire = self.organisme(date_fin_validite=date.today() - timedelta(days=1))
        self.assertEqual(self.controle(organisme="agrege", organisme_agree=str(expire.pk)).status_code, 400)
        rt_seul = self.organisme(methodes="RT")
        r = self.controle(organisme="agrege", organisme_agree=str(rt_seul.pk))
        self.assertEqual(r.status_code, 400)
        self.assertIn("UT", str(r.data["organisme_agree"]))
        ok = self.organisme()
        r = self.controle(organisme="agrege", organisme_agree=str(ok.pk))
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual((r.data["organisme_agree_nom"], r.data["organisme_libelle"]), (ok.nom, ok.nom))
        # Contrôle interne : aucun organisme exigé.
        self.assertEqual(self.controle(organisme="interne").status_code, 201)

    def test_parametre_provisoire_desactive_le_controle(self):
        get_param_qualite("CND_ORGANISME_REFERENTIEL")
        p = ParametreQualite.objects.get(code="CND_ORGANISME_REFERENTIEL")
        self.assertTrue(p.est_provisoire)
        r = self.client.patch(f"/api/qualite/parametres/{p.pk}/", {"valeur": "0"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.controle(organisme="agrege", organisme_libelle="Libre").status_code, 201)


class WpsProfilTests(_Base):
    def setUp(self):
        super().setUp()
        self.wps_a = WpsWpqr.objects.create(type="wps", procede="gtaw", statut="valide")
        self.wps_b = WpsWpqr.objects.create(type="wps", procede="smaw", statut="valide")
        self.contrat = Contract.objects.create(
            affaire=self.affaire, profile=Contract.Profile.MARCHE_TRAVAUX, start_date=date.today(),
        )

    def test_wps_requis_par_profil_bloque_un_wps_non_prevu(self):
        r = self.client.post("/api/qualite/wps-requis/", {"profile": "marche_travaux", "wps": str(self.wps_a.pk)}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(self.client.post("/api/qualite/wps-requis/", {"profile": "marche_travaux", "wps": str(self.wps_a.pk)},
                                          format="json").status_code, 400)  # doublon
        self.assertEqual(self.client.post("/api/qualite/wps-requis/", {"wps": str(self.wps_a.pk)}, format="json").status_code, 400)
        r = self.controle(affaire=str(self.affaire.pk), wps=str(self.wps_b.pk))
        self.assertEqual(r.status_code, 400)
        self.assertIn(self.wps_a.code, str(r.data["wps"]))
        self.assertEqual(self.controle(affaire=str(self.affaire.pk), wps=str(self.wps_a.pk)).status_code, 201)
        # Diffusion vers un OF de l'affaire : même règle.
        of = OrdreFabrication.objects.create(label="Spool", affaire=self.affaire)
        self.assertEqual(self.client.post(f"/api/qualite/wps/{self.wps_b.pk}/diffuser/", {"ordre": str(of.pk)}).status_code, 400)
        self.assertEqual(self.client.post(f"/api/qualite/wps/{self.wps_a.pk}/diffuser/", {"ordre": str(of.pk)}).status_code, 201)

    def test_exigence_du_contrat_prime_sur_le_profil_et_couverture(self):
        WpsRequis.objects.create(profile="marche_travaux", wps=self.wps_a)
        WpsRequis.objects.create(contract=self.contrat, wps=self.wps_b)
        self.assertEqual(self.controle(affaire=str(self.affaire.pk), wps=str(self.wps_b.pk)).status_code, 201)
        self.assertEqual(self.controle(affaire=str(self.affaire.pk), wps=str(self.wps_a.pk)).status_code, 400)
        r = self.client.get(f"/api/qualite/wps-requis/conformite/?affaire={self.affaire.pk}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([x["wps_code"] for x in r.data["requis"]], [self.wps_b.code])
        self.assertTrue(r.data["conforme"])
        WpsWpqr.objects.filter(pk=self.wps_b.pk).update(statut="obsolete")
        self.assertFalse(self.client.get(f"/api/qualite/wps-requis/conformite/?affaire={self.affaire.pk}").data["conforme"])
        self.assertEqual(self.client.get("/api/qualite/wps-requis/conformite/?affaire=x").status_code, 400)
        of = OrdreFabrication.objects.create(label="Spool 2", affaire=self.affaire)
        r = self.client.get(f"/api/qualite/wps-requis/conformite/?ordre={of.pk}")
        self.assertEqual((r.status_code, r.data["affaire_code"]), (200, self.affaire.code))

    def test_affaire_sans_exigence_reste_libre(self):
        self.assertEqual(self.controle(affaire=str(self.affaire.pk), wps=str(self.wps_b.pk)).status_code, 201)
        self.assertEqual(ControleQualite.objects.count(), 1)
