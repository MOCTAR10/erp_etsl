"""Lot 15 (2026-10-17) — saisie comptable manuelle restreinte (CDC M10 RG-M10.01).

« 95 % des écritures sont issues des modules » : les modules (paiements, paie, imports, balances
d'ouverture…) passent par leurs services ; l'API de saisie ne crée que des écritures **manuelles** :
- source forcée à `MANUEL` (un client ne peut pas se faire passer pour un module) ;
- uniquement au journal des opérations diverses (OD) ;
- motif obligatoire ;
- indicateur de part de saisie manuelle (écritures comptabilisées de l'exercice), alerte au-delà de 5 %.
"""

from datetime import date
from decimal import Decimal

from django.core.management import call_command
from rest_framework.test import APITestCase

from referentiels.models import Account
from users.models import User

from .models import AccountMove, AccountMoveLine, Journal, Period
from .services import post_move


class SaisieManuelleTests(APITestCase):
    URL = "/api/accounting/moves/"

    def setUp(self):
        call_command("seed_accounting", year=2026)
        self.comptable = User.objects.create_user(email="compta@etls.ga", password="x-Audit-2026", role=User.Role.COMPTABLE)
        self.client.force_authenticate(self.comptable)
        self.a411, _ = Account.objects.get_or_create(code="411000", defaults={"label": "Clients", "account_class": 4, "account_type": Account.AccountType.ASSET})
        self.a701, _ = Account.objects.get_or_create(code="701000", defaults={"label": "Ventes", "account_class": 7, "account_type": Account.AccountType.INCOME})
        self.od = Journal.objects.get(code="OD")

    def payload(self, **kw):
        body = {"journal": self.od.pk, "date": "2026-01-20", "label": "Reclassement", "motif": "Erreur d'imputation PV-12",
                "lines": [{"account": self.a411.pk, "debit": "10.00", "credit": "0"},
                          {"account": self.a701.pk, "debit": "0", "credit": "10.00"}]}
        body.update(kw)
        return body

    def test_source_forcee_a_manuel(self):
        r = self.client.post(self.URL, self.payload(source="M10", source_ref="PAI00001"), format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual((r.data["source"], r.data["source_ref"]), ("MANUEL", ""))

    def test_motif_obligatoire(self):
        r = self.client.post(self.URL, self.payload(motif=""), format="json")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("motif", r.data)

    def test_hors_journal_od_refuse(self):
        r = self.client.post(self.URL, self.payload(journal=Journal.objects.get(code="VTE").pk), format="json")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("journal", r.data)

    def ecriture_module(self, numero):
        move = AccountMove.objects.create(journal=Journal.objects.get(code="BQ"), period=Period.objects.get(number=1, fiscal_year__year=2026),
                                          date=date(2026, 1, 10), reference=f"PAI{numero}", source="M10")
        AccountMoveLine.objects.create(move=move, account=self.a411, debit=Decimal("5"), order=1)
        AccountMoveLine.objects.create(move=move, account=self.a701, credit=Decimal("5"), order=2)
        post_move(move, user=self.comptable)

    def test_taux_de_saisie_manuelle(self):
        for i in range(9):
            self.ecriture_module(i)
        move_id = self.client.post(self.URL, self.payload(), format="json").data["id"]
        self.client.post(f"{self.URL}{move_id}/post/")
        r = self.client.get(f"{self.URL}taux-saisie-manuelle/", {"exercice": 2026})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.data["total"], r.data["manuelles"], r.data["taux"], r.data["alerte"]), (10, 1, "10.00", True))
