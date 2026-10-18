"""Lot C M2 (2026-10-18) — support API des écrans de saisie Achats : retenir une offre, libellés des listes de choix."""

from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from referentiels.models import Partner
from users.models import User

from .models import ConsultationOffer, ConsultationRequest, PurchaseOrder, PurchaseOrderLine


class RetenirOffreTests(APITestCase):
    def setUp(self):
        self.client.force_authenticate(User.objects.create_user(email="fin@etls.ga", password="x-Audit-2026", role=User.Role.FINANCE))
        self.consult = ConsultationRequest.objects.create(subject="Tubes", status=ConsultationRequest.Status.OUVERTE)
        f1 = Partner.objects.create(code="F1", name="Un", kind=Partner.Kind.FOURNISSEUR)
        f2 = Partner.objects.create(code="F2", name="Deux", kind=Partner.Kind.FOURNISSEUR)
        self.o1 = ConsultationOffer.objects.create(consultation=self.consult, supplier=f1, amount=Decimal("100"))
        self.o2 = ConsultationOffer.objects.create(consultation=self.consult, supplier=f2, amount=Decimal("90"))

    def test_retenir_deselectionne_les_autres(self):
        self.assertEqual(self.client.post(f"/api/achats/consultation-offers/{self.o1.pk}/retenir/").status_code, 200)
        self.assertEqual(self.client.post(f"/api/achats/consultation-offers/{self.o2.pk}/retenir/").status_code, 200)
        self.o1.refresh_from_db()
        self.o2.refresh_from_db()
        self.assertEqual((self.o1.is_selected, self.o2.is_selected), (False, True))
        self.assertEqual(self.client.post(f"/api/achats/consultations/{self.consult.pk}/cloturer/").status_code, 200)

    def test_consultation_non_ouverte_refuse(self):
        ConsultationRequest.objects.filter(pk=self.consult.pk).update(status=ConsultationRequest.Status.CLOTUREE)
        self.assertEqual(self.client.post(f"/api/achats/consultation-offers/{self.o1.pk}/retenir/").status_code, 400)

    def test_codes_exposes_pour_les_listes_de_choix(self):
        r = self.client.get(f"/api/achats/consultation-offers/{self.o1.pk}/")
        self.assertEqual(r.data["consultation_code"], self.consult.code)
        bc = PurchaseOrder.objects.create(order_date=date.today())
        ligne = PurchaseOrderLine.objects.create(purchase_order=bc, label="Tube", quantity=1, unit_price=Decimal("1"))
        self.assertEqual(self.client.get(f"/api/achats/order-lines/{ligne.pk}/").data["order_code"], bc.code)
