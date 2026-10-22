"""Recette du lot a7 (comptabilité) : provision pour perte de change latente (697 / 499) à la réévaluation de clôture,
contre-passée au calcul suivant ; paramètre provisoire DEVISE_PROVISION_PERTE."""

from decimal import Decimal

from .models import ParametreCompta, ProvisionChange
from .services import get_param
from . import test_ecarts_a2 as a2
from .test_ecarts_a2 import OPS, A2Base, solde
from .tests import BASE

PROV = f"{BASE}provisions-change/"
TOUT = f"{OPS}reevaluer-tout/"


class ProvisionPerteChangeTests(A2Base):
    creer = a2.OperationDeviseTests.creer

    def setUp(self):
        super().setUp()
        self.taux("USD", "2026-03-01", "600")
        op = self.creer("dette", self.fournisseur, "USD", "1000", "601000")
        self.assertEqual(self.client.post(f"{OPS}{op['id']}/comptabiliser/").status_code, 200)

    def test_perte_latente_provisionnee_puis_contre_passee(self):
        self.taux("USD", "2026-03-31", "610")
        r = self.client.post(TOUT, {"date": "2026-03-31"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["provision"]["montant"], r.json()["position_latente"]), ("10000.00", "-10000.00"))
        self.assertEqual((solde("697000"), solde("499000")), (Decimal("10000"), Decimal("-10000")))
        # Calcul suivant : la perte s'est retournée en gain → provision contre-passée, aucune nouvelle dotation.
        self.taux("USD", "2026-04-30", "595")
        r = self.client.post(TOUT, {"date": "2026-04-30"}, format="json")
        self.assertIsNone(r.json()["provision"])
        self.assertEqual(r.json()["provision_contre_passee"]["date_cloture"], "2026-03-31")
        self.assertEqual((solde("697000"), solde("499000")), (Decimal("0"), Decimal("0")))
        p = ProvisionChange.objects.get()
        self.assertEqual((p.statut, p.date_contre_passation.isoformat()), ("contre_passee", "2026-04-30"))
        liste = self.client.get(PROV).json()
        self.assertTrue(liste["provisoire"])
        self.assertEqual(liste["results"][0]["move_contre_passation_number"], p.move_contre_passation.number)

    def test_recalcul_meme_date_sans_doublon_et_date_anterieure_refusee(self):
        self.taux("USD", "2026-03-31", "610")
        self.client.post(TOUT, {"date": "2026-03-31"}, format="json")
        self.client.post(TOUT, {"date": "2026-03-31"}, format="json")
        self.assertEqual(ProvisionChange.objects.filter(statut="active").count(), 1)
        self.assertEqual(solde("499000"), Decimal("-10000"))
        self.assertEqual(self.client.post(TOUT, {"date": "2026-03-15"}, format="json").status_code, 400)

    def test_parametre_desactive_aucune_dotation(self):
        get_param("DEVISE_PROVISION_PERTE")  # crée le paramètre par défaut
        ParametreCompta.objects.filter(code="DEVISE_PROVISION_PERTE").update(valeur=0)
        self.taux("USD", "2026-03-31", "610")
        r = self.client.post(TOUT, {"date": "2026-03-31"}, format="json")
        self.assertEqual((r.json()["provision"], r.json()["provision_active"]), (None, False))
        self.assertFalse(ProvisionChange.objects.exists())
        self.assertEqual(solde("478000"), Decimal("10000"))  # l'écart de conversion reste constaté
