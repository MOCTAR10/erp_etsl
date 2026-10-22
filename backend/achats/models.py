"""Module M2 — Achats & Approvisionnements (RF-ERP-10…13).

Demandes d'achat & consultation · bons de commande & réceptions ·
rapprochement 3-way (BL / facture) · circuit intra-groupe GLOBAL RENTAL.
"""

import uuid
from decimal import Decimal

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
    affaire = models.ForeignKey(
        "commercial.Affaire", null=True, blank=True, on_delete=models.SET_NULL, related_name="demandes_achat",
        verbose_name="Affaire d'origine (M1)",
    )
    notes = models.TextField(blank=True, verbose_name="Notes")
    analytic = models.ForeignKey(
        "referentiels.AnalyticAccount",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="Imputation analytique (affaire / chantier / centre)",
        help_text="Rattachement au budget M11 : contrôle RG-M2.08 (90 / 100 / 110 %).",
    )
    visa_dg_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="Visa exceptionnel DG (dépassement budgétaire)",
    )
    visa_dg_motif = models.TextField(blank=True, verbose_name="Motif du visa exceptionnel")
    visa_dg_le = models.DateTimeField(null=True, blank=True, verbose_name="Date du visa exceptionnel")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Demande d'achat"
        verbose_name_plural = "Demandes d'achat"

    def __str__(self):
        return f"{self.code} — {self.title}"

    @property
    def montant_estime(self):
        return sum((line.quantity * line.estimated_price for line in self.lines.all()), Decimal("0"))

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
    affaire = models.ForeignKey(
        "commercial.Affaire", null=True, blank=True, on_delete=models.SET_NULL, related_name="commandes_achat",
        verbose_name="Affaire (M1)",
    )
    location_gr = models.ForeignKey(
        "logistique.LocationGR", null=True, blank=True, on_delete=models.PROTECT, related_name="commandes_achat",
        verbose_name="Location GLOBAL RENTAL (M4)",
    )
    reference_ds = models.CharField(
        max_length=40, blank=True, verbose_name="Référence DS",
        help_text="Sigle « DS » à confirmer par ETSL (paramètre provisoire DS_OBLIGATOIRE_GR).",
    )
    document_ged = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        verbose_name="Pièce archivée en GED (conservation)",
    )
    notes = models.TextField(blank=True, verbose_name="Notes")
    analytic = models.ForeignKey(
        "referentiels.AnalyticAccount",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="Imputation analytique (affaire / chantier / centre)",
        help_text="Rattachement au budget M11 : contrôle RG-M2.08 (90 / 100 / 110 %).",
    )
    visa_dg_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="Visa exceptionnel DG (dépassement budgétaire)",
    )
    visa_dg_motif = models.TextField(blank=True, verbose_name="Motif du visa exceptionnel")
    visa_dg_le = models.DateTimeField(null=True, blank=True, verbose_name="Date du visa exceptionnel")
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
            anomalies = []
            if line.received_qty > line.quantity:
                anomalies.append(
                    f"Sur-réception : reçu {line.received_qty} > commandé {line.quantity}"
                )
            if line.invoiced_qty > line.received_qty:
                anomalies.append(
                    f"Facturé {line.invoiced_qty} > reçu {line.received_qty} (facture sans réception)"
                )
            for inv in line.invoice_lines.all():
                if abs(inv.unit_price - line.unit_price) > Decimal("0.01"):
                    anomalies.append(
                        f"Écart de prix : facturé {inv.unit_price} vs commandé {line.unit_price}"
                    )
                    break
            rows.append(
                {
                    "label": line.label,
                    "ordered": float(line.quantity),
                    "remaining": float(ordered),
                    "received": float(line.received_qty),
                    "invoiced": float(line.invoiced_qty),
                    "anomalies": anomalies,
                    "ok": not anomalies,
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
        if self.location_gr_id:
            if not self.is_global_rental:
                raise ValidationError({"location_gr": "Un BC lié à une location GR est un BC GLOBAL RENTAL (compte 618)."})
            if self.supplier_id and self.supplier_id != self.location_gr.partenaire_id:
                raise ValidationError({"supplier": "Le fournisseur doit être le partenaire GR de la location."})


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
    document_ged = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        verbose_name="Pièce archivée en GED (conservation)",
    )
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
    # Aval M5 : lot et certificat matière saisis à la réception, créés dans M5 à la validation.
    numero_lot = models.CharField(max_length=80, blank=True, verbose_name="N° lot fournisseur")
    numero_coulee = models.CharField(max_length=80, blank=True, verbose_name="N° de coulée")
    date_peremption = models.DateField(null=True, blank=True, verbose_name="Date de péremption")
    certificat_type = models.CharField(
        max_length=4, blank=True, choices=[("mtc", "MTC (Mill Test Certificate)"), ("coc", "CoC (Certificate of Conformity)")],
        verbose_name="Certificat matière",
    )
    numero_certificat = models.CharField(max_length=80, blank=True, verbose_name="N° certificat")
    organisme_certificat = models.CharField(max_length=120, blank=True, verbose_name="Organisme / labo")
    lot = models.ForeignKey(
        "stocks.LotMatiere", null=True, blank=True, on_delete=models.SET_NULL, related_name="lignes_reception",
        verbose_name="Lot créé (M5)",
    )
    # Lot a7 (CL-OM-08) : horodatage de la saisie sur l'appareil (réception hors ligne synchronisée plus tard).
    saisi_le = models.DateTimeField(null=True, blank=True, verbose_name="Saisie sur l'appareil (hors ligne)")

    class Meta:
        ordering = ["receipt", "id"]
        verbose_name = "Ligne de réception"
        verbose_name_plural = "Lignes de réception"

    def __str__(self):
        return f"{self.purchase_order_line.label} × {self.quantity}"

    def save(self, *args, **kwargs):
        with transaction.atomic():
            old = (
                None
                if self._state.adding
                else GoodsReceiptLine.objects.filter(pk=self.pk)
                .values("quantity", "purchase_order_line_id")
                .first()
            )
            order_ids = {_shift_qty(self.purchase_order_line_id, "received_qty", self.quantity)}
            if old:
                # modification : on retire l'ancienne quantité (de l'ancienne ligne si elle a changé)
                order_ids.add(
                    _shift_qty(old["purchase_order_line_id"], "received_qty", -old["quantity"])
                )
            result = super().save(*args, **kwargs)
        for order_id in order_ids:
            _refresh_purchase_order_status(order_id)
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


def _shift_qty(po_line_id, field, delta):
    """Ajoute `delta` (peut être négatif) à `received_qty`/`invoiced_qty` d'une ligne de BC, sous verrou.

    Retourne l'id du BC concerné. Jamais négatif (borné à 0).
    """
    line = PurchaseOrderLine.objects.select_for_update().get(pk=po_line_id)
    setattr(line, field, max(Decimal("0"), getattr(line, field) + Decimal(delta)))
    line.save(update_fields=[field])
    return line.purchase_order_id


def _refresh_purchase_order_status(order_id):
    """Statut du BC selon le solde des réceptions."""
    with transaction.atomic():
        order = PurchaseOrder.objects.select_for_update().get(pk=order_id)
        # Brouillon et annulé ne bougent pas ; sinon le statut est DÉRIVÉ des réceptions
        # (il redescend si une réception est corrigée ou supprimée).
        if order.status in (PurchaseOrder.Status.BROUILLON, PurchaseOrder.Status.ANNULEE):
            return
        lines = list(order.lines.all())
        if not lines:
            return
        all_received = all(float(l.received_qty) >= float(l.quantity) for l in lines)
        any_received = any(float(l.received_qty) > 0 for l in lines)
        if all_received:
            new = PurchaseOrder.Status.CLOTUREE
        elif any_received:
            new = PurchaseOrder.Status.PARTIELLE
        else:
            new = PurchaseOrder.Status.CONFIRMEE
        if new != order.status:
            order.status = new
            order.save(update_fields=["status"])


class PurchaseInvoice(models.Model):
    """Facture fournisseur — rapprochement 3-way avec le BC (RF-ERP-12)."""

    class Status(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente de rapprochement"
        RAPPROCHEE = "rapprochee", "Rapprochée"
        COMPTABILISEE = "comptabilisee", "Comptabilisée"
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
        max_length=14, choices=Status.choices, default=Status.EN_ATTENTE, verbose_name="Statut"
    )
    currency = models.ForeignKey(
        "referentiels.Currency",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Devise",
    )
    move = models.ForeignKey(
        "accounting_kernel.AccountMove",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="factures_fournisseurs",
        verbose_name="Écriture comptable",
        help_text="Écriture d'achat (charge + TVA déductible / fournisseur) posée par la comptabilisation.",
    )
    comptabilise_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="Comptabilisée par",
    )
    comptabilise_le = models.DateTimeField(null=True, blank=True, verbose_name="Comptabilisée le")
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
        """Total hors taxes."""
        return sum((line.price_total for line in self.lines.all()), 0) if self.id else 0

    @property
    def total_tva(self):
        return sum((line.tva_amount for line in self.lines.all()), Decimal("0")) if self.id else Decimal("0")

    @property
    def total_ttc(self):
        return self.total + self.total_tva

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
    taux_tva = models.ForeignKey(
        "comptabilite.TauxTva",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="Taux de TVA",
        help_text="Vide = taux par défaut paramétré en Comptabilité → TVA.",
    )

    class Meta:
        ordering = ["invoice", "id"]
        verbose_name = "Ligne de facture"
        verbose_name_plural = "Lignes de facture"

    def __str__(self):
        return f"{self.purchase_order_line.label} × {self.quantity}"

    @property
    def tva_amount(self):
        """TVA déductible de la ligne (taux de la ligne, sinon taux par défaut ; 0 si aucun taux)."""
        from .comptabilisation import taux_effectif

        taux = taux_effectif(self)
        return (self.price_total * taux.taux / Decimal("100")).quantize(Decimal("0.01")) if taux else Decimal("0")

    def save(self, *args, **kwargs):
        self.price_total = self.quantity * self.unit_price
        with transaction.atomic():
            old = (
                None
                if self._state.adding
                else PurchaseInvoiceLine.objects.filter(pk=self.pk)
                .values("quantity", "purchase_order_line_id")
                .first()
            )
            _shift_qty(self.purchase_order_line_id, "invoiced_qty", self.quantity)
            if old:
                _shift_qty(old["purchase_order_line_id"], "invoiced_qty", -old["quantity"])
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


class LitigeFournisseur(models.Model):
    """Litige fournisseur (clôture M2, CDC §5.4 « relance fournisseur, escalade, conservation M12 »).

    Cycle : ouvert → relancé (n relances tracées) → escaladé (pré-contentieux M12 ouvert) → résolu (motivé).
    """

    class Type(models.TextChoices):
        QUANTITE = "quantite", "Écart de quantité"
        QUALITE = "qualite", "Non-conformité qualité"
        PRIX = "prix", "Écart de prix / facturation"
        DELAI = "delai", "Retard de livraison"
        AUTRE = "autre", "Autre"

    class Statut(models.TextChoices):
        OUVERT = "ouvert", "Ouvert"
        RELANCE = "relance", "Relancé"
        ESCALADE = "escalade", "Escaladé (contentieux)"
        RESOLU = "resolu", "Résolu"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.PROTECT, related_name="litiges", verbose_name="Bon de commande"
    )
    receipt = models.ForeignKey(
        "GoodsReceipt", null=True, blank=True, on_delete=models.SET_NULL, related_name="litiges", verbose_name="Réception"
    )
    invoice = models.ForeignKey(
        "PurchaseInvoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="litiges", verbose_name="Facture"
    )
    type = models.CharField(max_length=10, choices=Type.choices, verbose_name="Type")
    description = models.TextField(verbose_name="Description")
    montant_en_jeu = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="Montant en jeu")
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.OUVERT, verbose_name="Statut")
    nb_relances = models.PositiveSmallIntegerField(default=0, verbose_name="Relances")
    derniere_relance_le = models.DateTimeField(null=True, blank=True, verbose_name="Dernière relance")
    contentieux = models.ForeignKey(
        "juridique.Contentieux", null=True, blank=True, on_delete=models.SET_NULL, related_name="litiges_fournisseurs",
        verbose_name="Contentieux (M12)",
    )
    resolution = models.TextField(blank=True, verbose_name="Résolution")
    resolu_le = models.DateTimeField(null=True, blank=True, verbose_name="Résolu le")
    document_ged = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        verbose_name="Pièce archivée en GED (conservation)",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Créé par"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Litige fournisseur"
        verbose_name_plural = "Litiges fournisseurs"

    def __str__(self):
        return f"{self.code} — {self.purchase_order.code}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = AchatsSequence.next_for("LTF", "LTF")
        return super().save(*args, **kwargs)

    def clean(self):
        for champ in ("receipt", "invoice"):
            objet = getattr(self, champ)
            if objet is not None and objet.purchase_order_id != self.purchase_order_id:
                raise ValidationError({champ: "Pièce d'un autre bon de commande."})


from django.db.models.signals import post_save  # noqa: E402


@receiver(post_save, sender=GoodsReceipt)
def _controle_a_reception(sender, instance, created, **kwargs):
    """Chaque réception (même partielle) déclenche son contrôle qualité M6 (CDC M2 §5.11)."""
    if not created:
        return
    from qualite.models import ControleQualite

    ControleQualite.objects.create(
        type_controle=ControleQualite.TypeControle.RECEPTION,
        reception=instance,
        point_controle=f"Réception {instance.code} — BC {instance.purchase_order.code}"[:200],
        statut=ControleQualite.Statut.EN_ATTENTE,
    )


class _ParametreBase(models.Model):
    class StatutValeur(models.TextChoices):
        PROVISOIRE = "provisoire", "Provisoire"
        CONFIRME = "confirme", "Confirmé"

    statut_valeur = models.CharField(
        max_length=10, choices=StatutValeur.choices, default=StatutValeur.PROVISOIRE, verbose_name="Statut de la valeur"
    )
    confirme_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Confirmé par",
    )
    confirme_le = models.DateTimeField(null=True, blank=True, verbose_name="Confirmé le")

    class Meta:
        abstract = True

    @property
    def est_provisoire(self):
        return self.statut_valeur != self.StatutValeur.CONFIRME


class ParametreAchats(_ParametreBase):
    """Paramètres M2 attendus d'ETSL : valeurs provisoires tant qu'ETSL ne les confirme pas (écarts M2)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=40, unique=True, verbose_name="Identifiant")
    label = models.CharField(max_length=200, verbose_name="Libellé")
    valeur = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Valeur")
    unite = models.CharField(max_length=20, blank=True, verbose_name="Unité")

    class Meta:
        ordering = ["code"]
        verbose_name = "Paramètre achats"
        verbose_name_plural = "Paramètres achats"

    def __str__(self):
        return f"{self.code} = {self.valeur} {self.unite}"


class AgrementFournisseur(models.Model):
    """Agrément fournisseur qualité (M6) ou HSE (M7) : décision des services QA/QC ou HSE reportée sur la fiche tiers."""

    class Domaine(models.TextChoices):
        QUALITE = "qualite", "Qualité (M6)"
        HSE = "hse", "HSE (M7)"

    class Statut(models.TextChoices):
        DEMANDE = "demande", "Demandé"
        VALIDE = "valide", "Validé"
        REFUSE = "refuse", "Refusé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    fournisseur = models.ForeignKey(
        "referentiels.Partner", on_delete=models.PROTECT, related_name="agrements_achats", verbose_name="Fournisseur"
    )
    domaine = models.CharField(max_length=8, choices=Domaine.choices, verbose_name="Domaine")
    reference = models.CharField(max_length=120, blank=True, verbose_name="Référence (audit, questionnaire, évaluation)")
    date_evaluation = models.DateField(default=timezone.localdate, verbose_name="Date d'évaluation")
    date_fin = models.DateField(null=True, blank=True, verbose_name="Agrément valable jusqu'au")
    note_evaluation = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Note d'évaluation /100")
    observations = models.TextField(blank=True, verbose_name="Observations")
    statut = models.CharField(max_length=8, choices=Statut.choices, default=Statut.DEMANDE, verbose_name="Statut")
    motif_refus = models.TextField(blank=True, verbose_name="Motif du refus")
    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+", verbose_name="Décision par"
    )
    valide_le = models.DateTimeField(null=True, blank=True, verbose_name="Décision le")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Créé par"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Agrément fournisseur"
        verbose_name_plural = "Agréments fournisseurs"

    def __str__(self):
        return f"{self.code} — {self.fournisseur} ({self.get_domaine_display()})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = AchatsSequence.next_for("AGR", "AGR")
        return super().save(*args, **kwargs)

    def clean(self):
        if self.date_fin and self.date_fin < self.date_evaluation:
            raise ValidationError({"date_fin": "La fin d'agrément doit suivre la date d'évaluation."})
        if self.note_evaluation is not None and not (0 <= self.note_evaluation <= 100):
            raise ValidationError({"note_evaluation": "Note sur 100."})


class RegleInspectionReception(_ParametreBase):
    """Règle d'inspection M6 à réception par catégorie d'article (ou article) : ITP et / ou CND exigés (provisoire)."""

    TYPES_ARTICLE = [
        ("produit", "Produit"), ("service", "Service / prestation"), ("matiere", "Matière première"),
        ("consommable", "Consommable"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    article_type = models.CharField(max_length=12, blank=True, choices=TYPES_ARTICLE, verbose_name="Catégorie d'article")
    article = models.ForeignKey(
        "referentiels.Article", null=True, blank=True, on_delete=models.CASCADE, related_name="regles_inspection_achats",
        verbose_name="Article (règle spécifique)",
    )
    exige_itp = models.BooleanField(default=False, verbose_name="ITP exigé")
    exige_cnd = models.BooleanField(default=False, verbose_name="CND exigé")
    methode_cnd = models.CharField(
        max_length=2, blank=True, choices=[("RT", "Radiographie (RT)"), ("UT", "Ultrasons (UT)"), ("PT", "Ressuage (PT)"),
                                           ("MT", "Magnétoscopie (MT)")],
        verbose_name="Méthode CND",
    )
    is_active = models.BooleanField(default=True, verbose_name="Active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["article_type", "-created_at"]
        verbose_name = "Règle d'inspection à réception"
        verbose_name_plural = "Règles d'inspection à réception"

    def __str__(self):
        cible = self.article.code if self.article_id else self.get_article_type_display()
        return f"{cible} : ITP={self.exige_itp} CND={self.exige_cnd}"

    def clean(self):
        if not self.article_id and not self.article_type:
            raise ValidationError({"article_type": "Catégorie d'article ou article requis."})
        if self.methode_cnd and not self.exige_cnd:
            raise ValidationError({"methode_cnd": "Méthode CND sans CND exigé."})


class AvoirFournisseur(models.Model):
    """Avoir fournisseur sur facture comptabilisée : contre-passation (extourne) au prorata de l'écriture d'achat."""

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        COMPTABILISE = "comptabilise", "Comptabilisé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    facture = models.ForeignKey(PurchaseInvoice, on_delete=models.PROTECT, related_name="avoirs", verbose_name="Facture d'origine")
    litige = models.ForeignKey(
        LitigeFournisseur, null=True, blank=True, on_delete=models.SET_NULL, related_name="avoirs", verbose_name="Litige"
    )
    reference_fournisseur = models.CharField(max_length=100, blank=True, verbose_name="Réf. avoir fournisseur")
    date_avoir = models.DateField(default=timezone.localdate, verbose_name="Date de l'avoir")
    montant_ht = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Montant HT")
    motif = models.TextField(verbose_name="Motif")
    statut = models.CharField(max_length=12, choices=Statut.choices, default=Statut.BROUILLON, verbose_name="Statut")
    move = models.ForeignKey(
        "accounting_kernel.AccountMove", null=True, blank=True, on_delete=models.PROTECT, related_name="avoirs_fournisseurs",
        verbose_name="Écriture comptable",
    )
    comptabilise_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+", verbose_name="Comptabilisé par"
    )
    comptabilise_le = models.DateTimeField(null=True, blank=True, verbose_name="Comptabilisé le")
    document_ged = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        verbose_name="Pièce archivée en GED (conservation)",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Créé par"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_avoir", "-created_at"]
        verbose_name = "Avoir fournisseur"
        verbose_name_plural = "Avoirs fournisseurs"

    def __str__(self):
        return f"{self.code} — {self.facture.code}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = AchatsSequence.next_for("AVF", "AVF")
        return super().save(*args, **kwargs)
