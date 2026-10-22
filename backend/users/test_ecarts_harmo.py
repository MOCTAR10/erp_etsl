"""Lot « harmonisation » (2026-10) : incohérences entre modules relevées par le dossier de paramétrage.

1. Durée d'agrément fournisseur : une seule source (ParametreAchats AGREMENT_DUREE_MOIS, 12 mois provisoires).
2. Conservation GED des contrats : 10 ans (CDC), sans jamais raccourcir une durée existante.
3. Paliers d'alerte : un paramètre central (`paliers_notification`, J-90/60/30/15/0) lu par M1, M12 et la Couche D.
4. Confirmation des paramètres : DAF (Finance) / Direction en M10 et M11, Direction en Couche D (403 sinon).
5. Paie : MAJ_NUIT / MAJ_ASTREINTE chargés à 0 % (« à saisir par ETSL »), 0 % = prime non valorisée.
6. RTO : 8 h (objectif du PRA), engagement contractuel CDC 48 h rappelé dans le libellé.
"""

import importlib
from datetime import date
from decimal import Decimal

from django.apps import apps as django_apps
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from users.models import User


def _user(role):
    return User.objects.create_user(email=f"{role}@harmo.ga", password="x-Harmo-2026", role=role)


def _set_paliers(valeur):
    from juridique.ecarts import parametre_obj
    from juridique.models import ParametreJuridique

    parametre_obj("paliers_notification")
    ParametreJuridique.objects.filter(cle="paliers_notification").update(valeur=valeur)


class PaliersCentrauxTests(TestCase):
    def test_un_seul_parametre_lu_par_tous_les_modules(self):
        from analytics import cubes, pilotage
        from commercial import ecarts_m1
        from config import echeances

        self.assertEqual(echeances.paliers(), (90, 60, 30, 15, 0))
        self.assertTrue(echeances.paliers_provisoires())
        self.assertNotIn("PALIER_ALERTE_J60", cubes.PARAMETRES_DEFAUT)
        self.assertFalse({"ECHEANCE_PALIER_1", "ECHEANCE_PALIER_2", "ECHEANCE_PALIER_3"} & set(ecarts_m1.PARAMETRES_DEFAUT))
        _set_paliers([45, 0, 120])
        self.assertEqual(echeances.paliers(), (120, 45, 0))
        self.assertEqual(ecarts_m1.paliers(), [120, 45, 0])
        self.assertEqual(pilotage.paliers_notification(), {120, 45, 0})
        self.assertEqual(echeances.bande(45), "j60")  # créneaux d'affichage inchangés

    def test_echeances_m1_lisent_le_central(self):
        c = APIClient()
        c.force_authenticate(_user(User.Role.DIRECTEUR_PROJETS))
        _set_paliers([30, 0])
        r = c.get("/api/commercial/pilotage/echeances/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["paliers"], [30, 0])
        self.assertTrue(r.data["provisoire"])


class ConfirmationParametresTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.comptable, self.finance = _user(User.Role.COMPTABLE), _user(User.Role.FINANCE)
        self.pdg = _user(User.Role.PDG)

    def _premier(self, url):
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200, url)
        data = r.json()
        return (data["results"] if isinstance(data, dict) else data)[0]["id"]

    def _confirmer(self, user, url, attendu):
        self.client.force_authenticate(user)
        self.assertEqual(self.client.post(url).status_code, attendu, (user.role, url))

    def test_compta_et_cg_modifier_comptable_confirmer_daf(self):
        for base in ("/api/comptabilite/parametres/", "/api/comptabilite/gabarits/", "/api/comptabilite/modele-facture/",
                     "/api/controle-gestion/parametres/?table=*"):
            self.client.force_authenticate(self.finance)
            pk = self._premier(base)
            url = f"{base.split('?')[0]}{pk}/confirmer/"
            self._confirmer(self.comptable, url, 403)
            self._confirmer(self.finance, url, 200)

    def test_comptable_modifie_un_parametre_compta(self):
        self.client.force_authenticate(self.comptable)
        r = self.client.get("/api/comptabilite/parametres/")
        p = (r.json()["results"] if isinstance(r.json(), dict) else r.json())[0]
        self.assertEqual(self.client.patch(f"/api/comptabilite/parametres/{p['id']}/", {"valeur": p["valeur"]},
                                           format="json").status_code, 200)

    def test_cube_confirmation_direction(self):
        self.client.force_authenticate(self.finance)
        pk = self._premier("/api/analytics/cubes/parametres/")
        url = f"/api/analytics/cubes/parametres/{pk}/confirmer/"
        self._confirmer(self.finance, url, 403)  # la Finance modifie, la Direction confirme
        self._confirmer(self.pdg, url, 200)


class AgrementContratsPaieRtoTests(TestCase):
    def test_duree_agrement_source_unique(self):
        from achats.ecarts import get_param
        from qualite.ecarts import PARAMETRES_QUALITE_DEFAUT

        self.assertNotIn("AGREMENT_DUREE_MOIS", PARAMETRES_QUALITE_DEFAUT)
        self.assertEqual(get_param("AGREMENT_DUREE_MOIS"), Decimal("12"))

    def test_contrats_dix_ans_sans_raccourcir(self):
        from documents.models import DocumentType

        call_command("seed_document_types")
        self.assertEqual(DocumentType.objects.get(code="contrats").retention_years, 10)
        allonger = importlib.import_module("documents.migrations.0010_ecarts_harmo").allonger
        DocumentType.objects.filter(code="contrats").update(retention_years=5)
        allonger(django_apps, None)
        self.assertEqual(DocumentType.objects.get(code="contrats").retention_years, 10)
        DocumentType.objects.filter(code="contrats").update(retention_years=12)
        allonger(django_apps, None)
        self.assertEqual(DocumentType.objects.get(code="contrats").retention_years, 12)

    def test_majorations_nuit_astreinte_a_saisir(self):
        from rh_paie.models import ParametrePaie

        call_command("seed_baremes_legaux_provisoires")
        for code in ("MAJ_NUIT", "MAJ_ASTREINTE"):
            p = ParametrePaie.objects.get(code=code, date_effet=date(2026, 1, 1))
            self.assertEqual((p.valeur, p.statut_valeur), (Decimal("0"), "provisoire"))
            self.assertIn("à saisir par ETSL", p.label)

    def test_nuit_a_zero_non_valorisee(self):
        from rh_paie.models import BulletinPaie, Employe, SaisieTemps
        from rh_paie.services import _primes_horaires

        call_command("seed_baremes_legaux_provisoires")
        emp = Employe.objects.create(code="EMP-H", nom="Doe", prenom="J", statut=Employe.Statut.ACTIF)
        SaisieTemps.objects.create(employe=emp, date=date(2026, 3, 2), heures=Decimal("10"), type="nuit")
        b = BulletinPaie.objects.create(employe=emp, periode=date(2026, 3, 1))
        self.assertEqual(_primes_horaires(b, Decimal("2000")), [])
        self.assertFalse(b.lignes.filter(rubrique__code="NUIT-TEMPS").exists())

    def test_rto_objectif_pra(self):
        from users.parametres import get_param_transverse

        p = get_param_transverse("RTO_HEURES")
        self.assertEqual(p.valeur, Decimal("8"))
        self.assertIn("48 h", p.label)
