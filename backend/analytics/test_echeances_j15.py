"""Lot 15 (2026-10-17) — alertes d'échéance J-90 / J-30 / J-15 / J-0 (CDC EX-G-05).

- Tranches d'échéance communes à tous les modules : expirée, J-0 (aujourd'hui), J-15, J-30, J-60, J-90.
- Chaque jour, la tâche `notifier_echeances` prévient les responsables aux paliers J-90, J-30, J-15 et J-0 :
  juridique (conventions, cautions, assurances) → Secrétariat général + PDG/DGA ; contrats et qualifications
  RH → RH. Une relance par palier : relancer la tâche le même jour ne double pas les notifications.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase

from config.echeances import bande
from juridique.models import Caution
from referentiels.models import Partner
from rh_paie.models import ContratTravail, Employe
from users.models import User
from workflow.models import Notification

from .services import alertes_agregees
from .tasks import notifier_echeances


class BandesTests(TestCase):
    def test_tranches(self):
        attendu = {-1: "expiree", 0: "j0", 1: "j15", 15: "j15", 16: "j30", 30: "j30", 45: "j60", 90: "j90", 91: "en_cours"}
        self.assertEqual({j: bande(j) for j in attendu}, attendu)
        self.assertEqual(bande(None), "en_cours")


class NotificationEcheancesTests(TestCase):
    def setUp(self):
        self.sg = User.objects.create_user(email="sg@etls.ga", password="x-Audit-2026", role=User.Role.SECRETAIRE_GENERAL)
        self.rh = User.objects.create_user(email="rh@etls.ga", password="x-Audit-2026", role=User.Role.RH)
        self.banque = Partner.objects.create(code="BQ-X", name="BGFI", kind=Partner.Kind.FOURNISSEUR)

    def caution(self, jours):
        return Caution.objects.create(type="bonne_execution", emetteur=self.banque, beneficiaire="CLIENT", objet="Garantie",
                                      montant=Decimal("750000"), date_emission=date(2026, 1, 1),
                                      date_echeance=date.today() + timedelta(days=jours), statut=Caution.Statut.EN_COURS)

    def test_caution_a_j15_dans_les_compteurs_et_notifiee(self):
        caution = self.caution(15)
        self.assertEqual(caution.expiry_status, "j15")
        self.assertEqual(alertes_agregees()["compteurs"]["j15"], 1)
        notifier_echeances()
        notif = Notification.objects.get(user=self.sg)
        self.assertIn(caution.code, notif.subject)
        self.assertIn("J-15", notif.subject)
        self.assertFalse(Notification.objects.filter(user=self.rh).exists())

    def test_hors_palier_pas_de_notification(self):
        self.caution(16)
        notifier_echeances()
        self.assertFalse(Notification.objects.exists())

    def test_contrat_rh_a_j0_notifie_la_rh_une_seule_fois(self):
        emp = Employe.objects.create(code="EMP-X", nom="Doe", prenom="John", statut=Employe.Statut.ACTIF)
        ContratTravail.objects.create(code="CTR-X", employe=emp, type="cdd", date_debut=date.today() - timedelta(days=60),
                                      date_fin=date.today(), statut=ContratTravail.Statut.ACTIF)
        self.assertEqual(alertes_agregees()["compteurs"]["j0"], 1)
        notifier_echeances()
        notifier_echeances()
        notif = Notification.objects.get(user=self.rh)
        self.assertIn("J-0", notif.subject)
