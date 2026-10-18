"""Recette M10 (clôture) — PR 4 : clôture mensuelle chronométrée (< 2 h) et envoi Direction à J+4.

Objectif (2 h) et jour d'envoi (J+4) sont des paramètres ETSL, provisoires jusqu'à confirmation.
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.utils import timezone

from accounting_kernel.models import AccountMove, AccountMoveLine, Journal, Period
from accounting_kernel.services import post_move
from referentiels.models import Account
from rh_paie.models import BulletinPaie, Employe
from rh_paie.services import comptabiliser_bulletin
from users.models import User
from workflow.models import Notification

from .models import ClotureMensuelle, ParametreCompta
from .services import get_param
from .tasks import suivre_clotures_mensuelles
from .tests import BASE, BaseComptaTest, _auth

URL = f"{BASE}clotures-mensuelles/"


class ClotureBase(BaseComptaTest):
    def setUp(self):
        super().setUp()
        self.janvier = Period.objects.get(number=1)
        self.produit = Account.objects.get_or_create(
            code="706000", defaults=dict(label="Ventes", account_class=7, account_type=Account.AccountType.INCOME)
        )[0]
        self.pdg = User.objects.create_user(email="pdg@etls.local", password="Etls#Demo2026", role=User.Role.PDG)
        _auth(self.client, "finance@etls.local")

    def ecriture(self, debit, credit, montant, d=date(2026, 1, 15), post=True):
        m = AccountMove.objects.create(
            journal=Journal.objects.get(code="OD"), period=Period.objects.get(start_date__lte=d, end_date__gte=d),
            date=d, label="t",
        )
        AccountMoveLine.objects.create(move=m, account=debit, debit=Decimal(montant), order=0)
        AccountMoveLine.objects.create(move=m, account=credit, credit=Decimal(montant), order=1)
        if post:
            post_move(m, self.admin)
        return m

    def demarrer(self, period=None):
        return self.client.post(f"{URL}demarrer/", {"period": (period or self.janvier).pk}, format="json")

    def cloturer(self, cid):
        return self.client.post(f"{URL}{cid}/cloturer/")

    def lancer(self, period=None):
        r = self.demarrer(period)
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()["id"]


class ControlesTests(ClotureBase):
    def test_controles_signalent_les_brouillons(self):
        self.ecriture(self.banque_account, self.produit, "1000", post=False)
        r = self.client.get(f"{URL}controles/?period={self.janvier.pk}")
        self.assertEqual(r.status_code, 200, r.content)
        par_code = {c["code"]: c for c in r.json()["controles"]}
        self.assertEqual((par_code["ecritures_brouillon"]["nb"], par_code["ecritures_brouillon"]["bloquant"]), (1, True))
        self.assertEqual(r.json()["bloquants"], 1)
        self.assertFalse(par_code["releves_non_rapproches"]["bloquant"])

    def test_cloture_bloquee_par_un_brouillon_puis_possible(self):
        m = self.ecriture(self.banque_account, self.produit, "1000", post=False)
        cid = self.lancer()
        r = self.cloturer(cid)
        self.assertEqual(r.status_code, 400)
        self.assertIn("brouillon", str(r.json()))
        self.janvier.refresh_from_db()
        self.assertEqual(self.janvier.status, "open")
        post_move(m, self.admin)
        r = self.cloturer(cid)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["statut"], "cloturee")
        self.janvier.refresh_from_db()
        self.assertEqual(self.janvier.status, "closed")
        self.assertTrue(r.json()["controles"])

    def test_periodes_precedentes_doivent_etre_closes(self):
        mars = Period.objects.get(number=3)
        cid = self.lancer(mars)
        r = self.cloturer(cid)
        self.assertEqual(r.status_code, 400)
        self.assertIn("précédentes", str(r.json()))

    def test_reception_de_la_paie_m9_est_controlee(self):
        for code, label in (("661000", "Personnel"), ("664000", "Charges sociales"), ("421000", "Personnel net"), ("431000", "Organismes")):
            Account.objects.get_or_create(code=code, defaults=dict(
                label=label, account_class=int(code[0]), account_type=Account.AccountType.EXPENSE))
        employe = Employe.objects.create(
            civilite=Employe.Sexe.MASCULIN, nom="TESTO", prenom="Alice", categorie=Employe.Categorie.CADRE,
            statut=Employe.Statut.ACTIF,
        )
        bulletin = BulletinPaie.objects.create(
            employe=employe, periode=date(2026, 1, 1), salaire_base=Decimal("1000000"), brut=Decimal("1000000"),
            net=Decimal("850000"), charges_patronales=Decimal("150000"), statut=BulletinPaie.Statut.VALIDE,
        )
        cid = self.lancer()
        r = self.cloturer(cid)
        self.assertEqual(r.status_code, 400)
        self.assertIn("paie", str(r.json()))
        comptabiliser_bulletin(bulletin, self.admin)
        r = self.cloturer(cid)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertGreaterEqual(r.json()["synthese"]["nb_ecritures"], 1)

    def test_paiements_et_factures_en_brouillon_bloquent(self):
        self._paiement()  # brouillon par défaut, date 2026-01-15
        cid = self.lancer()
        r = self.cloturer(cid)
        self.assertEqual(r.status_code, 400)
        self.assertIn("Paiements", str(r.json()))


class ChronoEtSyntheseTests(ClotureBase):
    def test_duree_dans_l_objectif_de_2_heures(self):
        cid = self.lancer()
        ClotureMensuelle.objects.filter(pk=cid).update(demarree_le=timezone.now() - timedelta(minutes=90))
        body = self.cloturer(cid).json()
        self.assertTrue(body["dans_objectif"])
        self.assertAlmostEqual(float(body["duree_minutes"]), 90, delta=1)
        self.assertEqual(body["objectif_minutes"], 120)

    def test_duree_hors_objectif(self):
        cid = self.lancer()
        ClotureMensuelle.objects.filter(pk=cid).update(demarree_le=timezone.now() - timedelta(hours=3))
        body = self.cloturer(cid).json()
        self.assertFalse(body["dans_objectif"])

    def test_objectif_parametrable(self):
        get_param("CLOTURE_OBJECTIF_HEURES")
        ParametreCompta.objects.filter(code="CLOTURE_OBJECTIF_HEURES").update(valeur=Decimal("4"))
        cid = self.lancer()
        ClotureMensuelle.objects.filter(pk=cid).update(demarree_le=timezone.now() - timedelta(hours=3))
        body = self.cloturer(cid).json()
        self.assertTrue(body["dans_objectif"])
        self.assertEqual(body["objectif_minutes"], 240)

    def test_synthese_figee_a_la_cloture(self):
        self.ecriture(self.banque_account, self.produit, "1000")
        self.ecriture(Account.objects.get(code="601000"), self.banque_account, "400")
        s = self.cloturer(self.lancer()).json()["synthese"]
        self.assertEqual(
            (Decimal(s["produits"]), Decimal(s["charges"]), Decimal(s["resultat"]), Decimal(s["tresorerie"])),
            (Decimal("1000"), Decimal("400"), Decimal("600"), Decimal("600")),
        )
        self.assertEqual(s["nb_ecritures"], 2)

    def test_echeance_d_envoi_j_plus_4_et_parametrable(self):
        body = self.cloturer(self.lancer()).json()
        self.assertEqual(body["echeance_envoi"], "2026-02-04")
        get_param("CLOTURE_JOUR_ENVOI")
        ParametreCompta.objects.filter(code="CLOTURE_JOUR_ENVOI").update(valeur=Decimal("10"))
        fevrier = Period.objects.get(number=2)
        body = self.cloturer(self.lancer(fevrier)).json()
        self.assertEqual(body["echeance_envoi"], "2026-03-10")

    def test_double_demarrage_et_double_cloture_refuses(self):
        cid = self.lancer()
        self.assertEqual(self.demarrer().status_code, 400)
        self.assertEqual(self.cloturer(cid).status_code, 200)
        self.assertEqual(self.cloturer(cid).status_code, 400)

    def test_synthese_masquee_hors_cercle_montants(self):
        self.ecriture(self.banque_account, self.produit, "1000")
        cid = self.lancer()
        self.cloturer(cid)
        directeur = User.objects.create_user(email="dp@etls.local", password="Etls#Demo2026", role="directeur_projets")
        self.client.force_authenticate(directeur)
        r = self.client.get(f"{URL}{cid}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["synthese"], {})
        self.assertFalse(r.json()["has_amount_access"])

    def test_logistique_ne_clot_pas(self):
        _auth(self.client, "logi@etls.local")
        self.assertIn(self.demarrer().status_code, (401, 403))


class EnvoiDirectionTests(ClotureBase):
    def test_envoi_notifie_la_direction_une_seule_fois(self):
        cid = self.lancer()
        self.cloturer(cid)
        r = self.client.post(f"{URL}{cid}/envoyer-direction/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["destinataires"], ["pdg@etls.local"])
        notif = Notification.objects.get(user=self.pdg)
        self.assertIn("Clôture", notif.subject)
        self.assertIn("Résultat", notif.message)
        self.assertEqual(self.client.post(f"{URL}{cid}/envoyer-direction/").status_code, 400)

    def test_envoi_impossible_avant_cloture_ou_sans_destinataire(self):
        cid = self.lancer()
        self.assertEqual(self.client.post(f"{URL}{cid}/envoyer-direction/").status_code, 400)
        self.cloturer(cid)
        User.objects.filter(role=User.Role.PDG).delete()
        self.assertEqual(self.client.post(f"{URL}{cid}/envoyer-direction/").status_code, 400)

    def test_tache_planifiee_envoie_a_j_plus_4(self):
        cid = self.lancer()
        self.cloturer(cid)
        with mock.patch("django.utils.timezone.localdate", return_value=date(2026, 2, 3)):
            self.assertEqual(suivre_clotures_mensuelles()["envoyees"], [])
        with mock.patch("django.utils.timezone.localdate", return_value=date(2026, 2, 4)):
            self.assertEqual(len(suivre_clotures_mensuelles()["envoyees"]), 1)
        self.assertEqual(Notification.objects.filter(user=self.pdg).count(), 1)
        with mock.patch("django.utils.timezone.localdate", return_value=date(2026, 2, 5)):
            self.assertEqual(suivre_clotures_mensuelles()["envoyees"], [])  # une seule fois

    def test_alerte_si_la_cloture_n_est_pas_faite_a_j_plus_4(self):
        with mock.patch("django.utils.timezone.localdate", return_value=date(2026, 2, 10)):
            res = suivre_clotures_mensuelles()
            suivre_clotures_mensuelles()  # relancé le même jour : pas de doublon
        self.assertTrue(res["alertes"])
        compta = User.objects.get(email="compta@etls.local")
        self.assertEqual(Notification.objects.filter(user=compta, subject__contains="en retard").count(), len(res["alertes"]))

    def test_retard_expose_par_l_api(self):
        cid = self.lancer()
        with mock.patch("django.utils.timezone.localdate", return_value=date(2026, 2, 10)):
            self.assertEqual(self.client.get(f"{URL}{cid}/").json()["retard"], "cloture_en_retard")
        with mock.patch("django.utils.timezone.localdate", return_value=date(2026, 2, 2)):
            self.assertIsNone(self.client.get(f"{URL}{cid}/").json()["retard"])
        self.cloturer(cid)
        with mock.patch("django.utils.timezone.localdate", return_value=date(2026, 2, 10)):
            self.assertEqual(self.client.get(f"{URL}{cid}/").json()["retard"], "envoi_en_retard")


class ReouvertureTests(ClotureBase):
    def test_reouverture_motivee_et_tracee(self):
        cid = self.lancer()
        self.cloturer(cid)
        self.client.post(f"{URL}{cid}/envoyer-direction/")
        self.assertEqual(self.client.post(f"{URL}{cid}/rouvrir/", {}, format="json").status_code, 400)
        r = self.client.post(f"{URL}{cid}/rouvrir/", {"motif": "facture oubliée"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual((body["statut"], body["envoyee_le"], body["periode_statut"]), ("en_cours", None, "open"))
        self.assertEqual(body["reouvertures"][0]["motif"], "facture oubliée")
        self.assertEqual(self.cloturer(cid).status_code, 200)
        self.assertEqual(self.client.post(f"{URL}{cid}/envoyer-direction/").status_code, 200)  # nouvel envoi corrigé

    def test_rouvrir_une_periode_non_cloturee_refuse(self):
        cid = self.lancer()
        self.assertEqual(self.client.post(f"{URL}{cid}/rouvrir/", {"motif": "x"}, format="json").status_code, 400)
