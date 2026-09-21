from django.core.management.base import BaseCommand
from django.utils import timezone

from referentiels.models import Article, Currency, Partner, UnitOfMeasure
from users.models import User

from achats.models import (
    ConsultationOffer,
    ConsultationRequest,
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseInvoice,
    PurchaseInvoiceLine,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseRequest,
    PurchaseRequestLine,
)


class Command(BaseCommand):
    help = "Seed de démonstration du module Achats (M2) — idempotent."

    def handle(self, *args, **options):
        currency, _ = Currency.objects.get_or_create(
            code="XAF", defaults={"label": "Franc CFA (BEAC)", "symbol": "FCFA", "decimals": 0}
        )
        unit, _ = UnitOfMeasure.objects.get_or_create(code="U", defaults={"label": "Unité"})

        logistique, _ = User.objects.get_or_create(
            email="demo.logistique@etls.local", defaults={"role": User.Role.LOGISTIQUE}
        )

        supplier, _ = Partner.objects.get_or_create(
            code="FOU-001",
            defaults={"name": "ACI Construction Equipment", "kind": Partner.Kind.FOURNISSEUR,
                      "currency": currency},
        )
        gr_partner, _ = Partner.objects.get_or_create(
            code="GR-1000",
            defaults={"name": "GLOBAL RENTAL (intra-groupe)", "kind": Partner.Kind.FOURNISSEUR,
                      "currency": currency, "is_global_rental": True},
        )
        for code, label in (("MAT-A106", "Tube A106 B"), ("GR-0002", "Grue 25t")):
            Article.objects.get_or_create(
                code=code, defaults={"label": label, "article_type": Article.ArticleType.MATIERE,
                                     "unit": unit}
            )

        today = timezone.localdate()

        request, _ = PurchaseRequest.objects.get_or_create(
            code="DA00001",
            defaults={
                "title": "Approvisionnement magasin ateliers",
                "requester": logistique,
                "department": "Logistique & Magasin",
                "expected_date": today + timezone.timedelta(days=10),
                "status": PurchaseRequest.Status.APPROUVEE,
            },
        )
        tube = Article.objects.get(code="MAT-A106")
        PurchaseRequestLine.objects.get_or_create(
            request=request, label="Tube A106 B", defaults={
                "article": tube, "quantity": 20, "unit": unit, "estimated_price": 45_000,
            },
        )

        consultation, _ = ConsultationRequest.objects.get_or_create(
            code="CONS00001",
            defaults={
                "request": request,
                "subject": "Mise en concurrence tubes & consommables",
                "due_date": today - timezone.timedelta(days=2),
                "status": ConsultationRequest.Status.CLOTUREE,
                "items": [{"label": "Tube A106 B", "qty": 20}, {"label": "Grue 25t", "qty": 6}],
            },
        )
        ConsultationOffer.objects.get_or_create(
            consultation=consultation, supplier=supplier, defaults={
                "amount": 1_250_000, "delivery_days": 14, "is_selected": True,
            },
        )
        ConsultationOffer.objects.get_or_create(
            consultation=consultation, supplier=gr_partner, defaults={
                "amount": 21_500_000, "delivery_days": 2, "is_selected": False,
            },
        )

        gr_line = ConsultationOffer.objects.get(
            consultation=consultation, supplier=supplier
        )
        order, _ = PurchaseOrder.objects.get_or_create(
            code="BC00001",
            defaults={
                "supplier": supplier,
                "request": request,
                "consultation": consultation,
                "order_date": today - timezone.timedelta(days=5),
                "expected_date": today + timezone.timedelta(days=9),
                "status": PurchaseOrder.Status.CONFIRMEE,
                "currency": currency,
                "created_by": logistique,
            },
        )
        PurchaseOrderLine.objects.get_or_create(
            purchase_order=order, label="Tube A106 B", defaults={
                "article": tube, "quantity": 20, "unit": unit, "unit_price": 45_000,
            },
        )
        grue = Article.objects.get(code="GR-0002")
        PurchaseOrderLine.objects.get_or_create(
            purchase_order=order, label="Location grue 25t (GLOBAL RENTAL)", defaults={
                "article": grue, "quantity": 6, "unit": unit, "unit_price": 3_500_000,
            },
        )

        order_gr, _ = PurchaseOrder.objects.get_or_create(
            code="BC00002",
            defaults={
                "supplier": gr_partner,
                "order_date": today - timezone.timedelta(days=3),
                "expected_date": today - timezone.timedelta(days=1),
                "status": PurchaseOrder.Status.CONFIRMEE,
                "currency": currency,
                "is_global_rental": True,
                "created_by": logistique,
            },
        )
        PurchaseOrderLine.objects.get_or_create(
            purchase_order=order_gr, label="Grue 25t — prestation intra-groupe", defaults={
                "article": grue, "quantity": 2, "unit": unit, "unit_price": 3_500_000,
            },
        )

        receipt, _ = GoodsReceipt.objects.get_or_create(
            code="BL00001",
            defaults={
                "purchase_order": order,
                "received_at": today - timezone.timedelta(days=1),
                "status": GoodsReceipt.Status.VALIDE,
                "received_by": logistique,
                "notes": "Réception partielle du BC00001",
            },
        )
        po_line = order.lines.get(label="Tube A106 B")
        GoodsReceiptLine.objects.get_or_create(
            receipt=receipt, purchase_order_line=po_line, defaults={
                "quantity": 12, "comment": "Solde à recevoir : 8",
            },
        )

        invoice, _ = PurchaseInvoice.objects.get_or_create(
            code="RC00001",
            defaults={
                "purchase_order": order,
                "supplier": supplier,
                "invoice_ref": "F-2026-118",
                "invoice_date": today,
                "status": PurchaseInvoice.Status.EN_ATTENTE,
                "currency": currency,
            },
        )
        PurchaseInvoiceLine.objects.get_or_create(
            invoice=invoice, purchase_order_line=po_line, defaults={
                "quantity": 12, "unit_price": 45_000,
            },
        )

        self.stdout.write(self.style.SUCCESS(
            f"Achats M2 prêt : {PurchaseRequest.objects.count()} DA, "
            f"{PurchaseOrder.objects.count()} BC, {GoodsReceipt.objects.count()} BL, "
            f"{PurchaseInvoice.objects.count()} facture."
        ))