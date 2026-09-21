"""Module M2 — Achats & Approvisionnements (RF-ERP-10…13).

Demandes d'achat & consultation · bons de commande & réceptions ·
rapprochement 3-way (BL / facture) · circuit intra-groupe GLOBAL RENTAL.
"""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


class AchatsSequence(models.Model):
    """Numérotation séquentielle par type (DA, CONS, BC, BL, RC)."""

    kind = models.CharField(max_length=10, unique=True, verbose_name="Type")
    prefix = models.CharField(max_length=10, verbose_name="Préfixe")
    padding = models.PositiveSmallIntegerField(default=5, verbose_name="Zéro-padding")
    next_number = models.PositiveIntegerField(default=1, verbose_name="Prochain numéro")

    class Meta:
        verbose_name = "Séquence Achats"
        verbose_name_plural = "Séquences Achats"

    def __str__(self):
        return f"{self.kind} → {self.prefix}{self.next_number:0{self.padding}d}"

    @classmethod
    def next_for(cls, kind, prefix):
        seq, _ = cls.objects.get_or_create(
            kind=kind, defaults={"prefix": prefix, "padding": 5}
        )
        with transaction.atomic():
            seq = cls.objects.select_for_update().get(pk=seq.pk)
            number = f"{seq.prefix}{str(seq.next_number).zfill(seq.padding)}"
            seq.next_number += 1
            seq.save(update_fields=["next_number"])
        return number


class PurchaseRequest(models.Model):
    """Demande d'achat (DA, proc. MANUEL 4.3-4.8 / 9.x)."""

    class Status(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        SOUMISE = "soumise", "Soumise"
        APPROUVEE = "approuvee", "Approuvée"
        REJETEE = "rejetee", "Rejetée"
        CONVERTIE = "convertie", "Convertie en commande"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    title = models.CharField(max_length=200, verbose_name="Objet")
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="purchase_requests",
        verbose_name="Demandeur",
    )
    department = models.CharField(max_length=100, blank=True, verbose_name="Service")
    expected_date = models.DateField(null=True, blank=True, verbose_name="Échéance souhaitée")
    status = models.CharField(
        max_length=14, choices=Status.choices, default=Status.BROUILLON, verbose_name="Statut"
    )
    is_urgent = models.BooleanField(default=False, verbose_name="Urgente")
    notes = models.TextField(blank=True, verbose_name="Notes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Demande d'achat"
        verbose_name_plural = "Demandes d'achat"

    def __str__(self):
        return f"{self.code} — {self.title}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = AchatsSequence.next_for("DA", "DA")
        return super().save(*args, **kwargs)


class PurchaseRequestLine(models.Model):
    """Ligne de demande d'achat."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(
        PurchaseRequest, on_delete=models.CASCADE, related_name="lines", verbose_name="Demande"
    )
    article = models.ForeignKey(
        "referentiels.Article",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="purchase_request_lines",
        verbose_name="Article",
    )
    label = models.CharField(max_length=200, verbose_name="Désignation")
    quantity = models.DecimalField(max_digits=14, decimal_places=2, default=1, verbose_name="Qté")
    unit = models.ForeignKey(
        "referentiels.UnitOfMeasure",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Unité",
    )
    estimated_price = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Prix estimé unitaire"
    )

    class Meta:
        ordering = ["request", "id"]
        verbose_name = "Ligne de demande d'achat"
        verbose_name_plural = "Lignes de demande d'achat"

    def __str__(self):
        return f"{self.label} × {self.quantity}"


class ConsultationRequest(models.Model):
    """Consultation fournisseurs (mise en concurrence, RF-ERP-10)."""

    class Status(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        OUVERTE = "ouverte", "Ouverte"
        CLOTUREE = "cloturee", "Clôturée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    request = models.ForeignKey(
        PurchaseRequest,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="consultations",
        verbose_name="Demande d'achat",
    )
    subject = models.CharField(max_length=200, verbose_name="Objet")
    due_date = models.DateField(null=True, blank=True, verbose_name="Date limite d'offre")
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.BROUILLON, verbose_name="Statut"
    )
    items = models.JSONField(default=list, blank=True, verbose_name="Lignes consultées")
    notes = models.TextField(blank=True, verbose_name="Notes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Consultation fournisseurs"
        verbose_name_plural = "Consultations fournisseurs"

    def __str__(self):
        return f"{self.code} — {self.subject}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = AchatsSequence.next_for("CONS", "CONS")
        return super().save(*args, **kwargs)


class ConsultationOffer(models.Model):
    """Offre reçue à la consultation (fournisseur, montant, délai)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    consultation = models.ForeignKey(
        ConsultationRequest,
        on_delete=models.CASCADE,
        related_name="offers",
        verbose_name="Consultation",
    )
    supplier = models.ForeignKey(
        "referentiels.Partner",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="consultation_offers",
        verbose_name="Fournisseur",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Montant")
    delivery_days = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Délai (jours)"
    )
    is_selected = models.BooleanField(default=False, verbose_name="Retenue")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["consultation", "-created_at"]
        verbose_name = "Offre de consultation"
        verbose_name_plural = "Offres de consultation"

    def __str__(self):
        return f"{self.consultation.code} / {self.supplier}"


class PurchaseOrder(models.Model):
    """Bon de commande fournisseur (BC, RF-ERP-11)."""

    class Status(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        CONFIRMEE = "confirmee", "Confirmée"
        PARTIELLE = "partielle", "Réception partielle"
        CLOTUREE = "cloturee", "Clôturée (réception totale)"
        ANNULEE = "annulee", "Annulée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    supplier = models.ForeignKey(
        "referentiels.Partner",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="purchase_orders",
        verbose_name="Fournisseur",
    )
    request = models.ForeignKey(
        PurchaseRequest,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="purchase_orders",
        verbose_name="Demande d'achat",
    )
    consultation = models.ForeignKey(
        ConsultationRequest,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="purchase_orders",
        verbose_name="Consultation",
    )
    order_date = models.DateField(default=timezone.localdate, verbose_name="Date")
    expected_date = models.DateField(null=True, blank=True, verbose_name="Livraison attendue")
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.BROUILLON, verbose_name="Statut"
    )
    currency = models.ForeignKey(
        "referentiels.Currency",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Devise",
    )
    is_global_rental = models.BooleanField(
        default=False, verbose_name="Intra-groupe GLOBAL RENTAL"
    )
    notes = models.TextField(blank=True, verbose_name="Notes")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="purchase_orders",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Bon de commande"
        verbose_name_plural = "Bons de commande"

    def __str__(self):
        return f"{self.code} — {self.supplier}"

    @property
    def total(self):
        return sum((line.price_total for line in self.lines.all()), 0) if self.id else 0

    @property
    def conformity(self):
        """Rapprochement 3-way par ligne : commandé / reçu / facturé."""
        rows = []
        for line in self.lines.all():
            ordered = line.quantity - line.received_qty
            rows.append(
                {
                    "label": line.label,
                    "ordered": float(line.quantity),
                    "remaining": float(ordered),
                    "received": float(line.received_qty),
                    "invoiced": float(line.invoiced_qty),
                    "ok": float(line.received_qty) <= float(line.quantity),
                }
            )
        return rows

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = AchatsSequence.next_for("BC", "BC")
        return super().save(*args, **kwargs)

    def clean(self):
        if self.is_global_rental and self.supplier_id and not self.supplier.is_global_rental:
            raise ValidationError(
                {"supplier": "Le partenaire doit être marqué GLOBAL RENTAL (intra-groupe)."}
            )


class PurchaseOrderLine(models.Model):
    """Ligne de bon de commande — quantités reçue/facturée pour le 3-way."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name="lines", verbose_name="Bon de commande"
    )
    article = models.ForeignKey(
        "referentiels.Article",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="purchase_order_lines",
        verbose_name="Article",
    )
    label = models.CharField(max_length=200, verbose_name="Désignation")
    quantity = models.DecimalField(max_digits=14, decimal_places=2, default=1, verbose_name="Qté")
    unit = models.ForeignKey(
        "referentiels.UnitOfMeasure",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Unité",
    )
    unit_price = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Prix unitaire"
    )
    price_total = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Total ligne"
    )
    received_qty = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Qté reçue"
    )
    invoiced_qty = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Qté facturée"
    )

    class Meta:
        ordering = ["purchase_order", "id"]
        verbose_name = "Ligne de bon de commande"
        verbose_name_plural = "Lignes de bon de commande"

    def __str__(self):
        return f"{self.label} × {self.quantity}"

    def save(self, *args, **kwargs):
        self.price_total = self.quantity * self.unit_price
        return super().save(*args, **kwargs)


class GoodsReceipt(models.Model):
    """Bon de livraison / réception (BL, RF-ERP-11)."""

    class Status(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente de validation"
        VALIDE = "valide", "Validé"
        ANNULE = "annule", "Annulé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name="receipts",
        verbose_name="Bon de commande",
    )
    received_at = models.DateField(default=timezone.localdate, verbose_name="Date de réception")
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.EN_ATTENTE, verbose_name="Statut"
    )
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="goods_receipts",
        verbose_name="Réceptionné par",
    )
    notes = models.TextField(blank=True, verbose_name="Notes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-received_at", "-created_at"]
        verbose_name = "Bon de livraison / réception"
        verbose_name_plural = "Bons de livraison / réceptions"

    def __str__(self):
        return f"{self.code} — {self.purchase_order.code}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = AchatsSequence.next_for("BL", "BL")
        return super().save(*args, **kwargs)


class GoodsReceiptLine(models.Model):
    """Ligne du BL — incrémente la quantité reçue du BC (select_for_update)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    receipt = models.ForeignKey(
        GoodsReceipt, on_delete=models.CASCADE, related_name="lines", verbose_name="Réception"
    )
    purchase_order_line = models.ForeignKey(
        PurchaseOrderLine,
        on_delete=models.CASCADE,
        related_name="receipt_lines",
        verbose_name="Ligne BC",
    )
    quantity = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Qté reçue"
    )
    comment = models.CharField(max_length=200, blank=True, verbose_name="Commentaire")

    class Meta:
        ordering = ["receipt", "id"]
        verbose_name = "Ligne de réception"
        verbose_name_plural = "Lignes de réception"

    def __str__(self):
        return f"{self.purchase_order_line.label} × {self.quantity}"

    def save(self, *args, **kwargs):
        with transaction.atomic():
            line = PurchaseOrderLine.objects.select_for_update().get(
                pk=self.purchase_order_line_id
            )
            if self._state.adding:
                line.received_qty += self.quantity
                line.save(update_fields=["received_qty"])
            result = super().save(*args, **kwargs)
        _refresh_purchase_order_status(line.purchase_order_id)
        return result


from django.db.models.signals import post_delete  # noqa: E402
from django.dispatch import receiver  # noqa: E402


@receiver(post_delete, sender=GoodsReceiptLine)
def _on_receipt_line_deleted(sender, instance, **kwargs):
    """Retire la quantité reçue lors de la suppression d'une ligne de BL."""
    with transaction.atomic():
        line = PurchaseOrderLine.objects.select_for_update().get(
            pk=instance.purchase_order_line_id
        )
        line.received_qty -= instance.quantity
        if line.received_qty < 0:
            line.received_qty = 0
        line.save(update_fields=["received_qty"])
    _refresh_purchase_order_status(line.purchase_order_id)


def _refresh_purchase_order_status(order_id):
    """Statut du BC selon le solde des réceptions."""
    with transaction.atomic():
        order = PurchaseOrder.objects.select_for_update().get(pk=order_id)
        if order.status in (PurchaseOrder.Status.ANNULEE, PurchaseOrder.Status.CLOTUREE):
            return
        lines = list(order.lines.all())
        if not lines:
            return
        all_received = all(float(l.received_qty) >= float(l.quantity) for l in lines)
        any_received = any(float(l.received_qty) > 0 for l in lines)
        if all_received:
            order.status = PurchaseOrder.Status.CLOTUREE
        elif any_received:
            order.status = PurchaseOrder.Status.PARTIELLE
        order.save(update_fields=["status"])


class PurchaseInvoice(models.Model):
    """Facture fournisseur — rapprochement 3-way avec le BC (RF-ERP-12)."""

    class Status(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente de rapprochement"
        RAPPROCHEE = "rapprochee", "Rapprochée"
        ANNULEE = "annulee", "Annulée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name="invoices",
        verbose_name="Bon de commande",
    )
    supplier = models.ForeignKey(
        "referentiels.Partner",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="purchase_invoices",
        verbose_name="Fournisseur",
    )
    invoice_ref = models.CharField(max_length=100, default="", blank=True, verbose_name="Réf. fournisseur")
    invoice_date = models.DateField(default=timezone.localdate, verbose_name="Date de facture")
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.EN_ATTENTE, verbose_name="Statut"
    )
    currency = models.ForeignKey(
        "referentiels.Currency",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Devise",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-invoice_date", "-created_at"]
        verbose_name = "Facture fournisseur"
        verbose_name_plural = "Factures fournisseurs"

    def __str__(self):
        return f"{self.code} — {self.invoice_ref or self.supplier}"

    @property
    def total(self):
        return sum((line.price_total for line in self.lines.all()), 0) if self.id else 0

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = AchatsSequence.next_for("RC", "RC")
        return super().save(*args, **kwargs)


class PurchaseInvoiceLine(models.Model):
    """Ligne de facture — incrémente la quantité facturée du BC."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(
        PurchaseInvoice,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name="Facture",
    )
    purchase_order_line = models.ForeignKey(
        PurchaseOrderLine,
        on_delete=models.CASCADE,
        related_name="invoice_lines",
        verbose_name="Ligne BC",
    )
    quantity = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Qté facturée"
    )
    unit_price = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Prix unitaire"
    )
    price_total = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="Total ligne"
    )

    class Meta:
        ordering = ["invoice", "id"]
        verbose_name = "Ligne de facture"
        verbose_name_plural = "Lignes de facture"

    def __str__(self):
        return f"{self.purchase_order_line.label} × {self.quantity}"

    def save(self, *args, **kwargs):
        self.price_total = self.quantity * self.unit_price
        with transaction.atomic():
            line = PurchaseOrderLine.objects.select_for_update().get(
                pk=self.purchase_order_line_id
            )
            if self._state.adding:
                line.invoiced_qty += self.quantity
                line.save(update_fields=["invoiced_qty"])
        return super().save(*args, **kwargs)


@receiver(post_delete, sender=PurchaseInvoiceLine)
def _on_invoice_line_deleted(sender, instance, **kwargs):
    """Retire la quantité facturée lors de la suppression d'une ligne de facture."""
    with transaction.atomic():
        line = PurchaseOrderLine.objects.select_for_update().get(
            pk=instance.purchase_order_line_id
        )
        line.invoiced_qty -= instance.quantity
        if line.invoiced_qty < 0:
            line.invoiced_qty = 0
        line.save(update_fields=["invoiced_qty"])