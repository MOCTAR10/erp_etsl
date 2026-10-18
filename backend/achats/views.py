"""API module M2 — Achats & Approvisionnements (RF-ERP-10…13)."""

from integrations.idempotency import idempotent
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import (
    LitigeFournisseur,
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
from .serializers import (
    LitigeFournisseurSerializer,
    ConsultationOfferSerializer,
    ConsultationRequestSerializer,
    GoodsReceiptLineSerializer,
    GoodsReceiptSerializer,
    PurchaseInvoiceLineSerializer,
    PurchaseInvoiceSerializer,
    PurchaseOrderLineSerializer,
    PurchaseOrderSerializer,
    PurchaseRequestLineSerializer,
    PurchaseRequestSerializer,
)
from users.permissions import can_read_module
from controle_gestion import budget_control

from comptabilite.services import CanValidateCompta

from .comptabilisation import comptabiliser_facture
from .stock_link import entrer_en_stock
from .services import CanApproveDa, CanManageAchats, can_see_amount, can_viser_dg


class _CommonViewSet(viewsets.ModelViewSet):
    """Lecture authentifiée ; écriture réservée aux rôles Achats/Finance."""

    http_method_names = ["get", "post", "patch", "delete"]

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [can_read_module("achats")()]
        return [CanManageAchats()]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["can_view_amount"] = can_see_amount(self.request.user)
        return context


class PurchaseRequestViewSet(_CommonViewSet):
    serializer_class = PurchaseRequestSerializer
    search_fields = ("code", "title", "department",)

    def get_permissions(self):
        # _CommonViewSet.get_permissions ignore les permission_classes d'action : l'approbation est déclarée ici.
        if self.action in ("approuver", "rejeter"):
            return [CanManageAchats(), CanApproveDa()]
        return super().get_permissions()

    def get_queryset(self):
        qs = PurchaseRequest.objects.select_related("requester").all()
        status_ = self.request.query_params.get("status")
        if status_:
            qs = qs.filter(status=status_)
        if self.request.query_params.get("requester"):
            qs = qs.filter(requester_id=self.request.query_params["requester"])
        return qs

    def perform_create(self, serializer):
        serializer.save(requester=self.request.user)

    def _transition(self, frm, to, extra_note=None, controle_budget=False):
        da = PurchaseRequest.objects.select_for_update().get(pk=self.get_object().pk)
        if da.status != frm:
            return Response(
                {"detail": f"DA {da.get_status_display().lower()} : action impossible."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if controle_budget:
            # RG-M2.08 : > 100 % du budget consommé → blocage de la DA (sauf visa exceptionnel DG).
            blocage = budget_control.controler(
                da.analytic, timezone.localdate(), da.montant_estime, budget_control.SEUIL_DA,
                f"la DA {da.code}", visa_dg=bool(da.visa_dg_par_id),
            )
            if blocage:
                return Response({"budget": blocage}, status=status.HTTP_400_BAD_REQUEST)
        da.status = to
        fields = ["status", "updated_at"]
        if extra_note:
            da.notes = f"{da.notes}\n{extra_note}".strip()
            fields.append("notes")
        da.save(update_fields=fields)
        return Response(self.get_serializer(da).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def soumettre(self, request, pk=None):
        return self._transition(PurchaseRequest.Status.BROUILLON, PurchaseRequest.Status.SOUMISE, controle_budget=True)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def approuver(self, request, pk=None):
        return self._transition(PurchaseRequest.Status.SOUMISE, PurchaseRequest.Status.APPROUVEE, controle_budget=True)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def rejeter(self, request, pk=None):
        motif = (request.data.get("motif") or "").strip()
        if not motif:
            return Response({"motif": "Motif du rejet obligatoire."}, status=status.HTTP_400_BAD_REQUEST)
        who = request.user.get_full_name() or request.user.email
        return self._transition(
            PurchaseRequest.Status.SOUMISE, PurchaseRequest.Status.REJETEE, f"Rejet ({who}) : {motif}"
        )

    @action(detail=True, methods=["post"], url_path="visa-dg")
    @transaction.atomic
    def visa_dg(self, request, pk=None):
        """Visa exceptionnel du DG : lève les blocages budgétaires RG-M2.08 pour cette pièce (motif obligatoire)."""
        if not can_viser_dg(request.user):
            return Response({"detail": "Visa exceptionnel réservé à la Direction Générale."}, status=status.HTTP_403_FORBIDDEN)
        motif = (request.data.get("motif") or "").strip()
        if not motif:
            return Response({"motif": "Motif du visa exceptionnel obligatoire."}, status=status.HTTP_400_BAD_REQUEST)
        obj = self.get_queryset().model.objects.select_for_update().get(pk=self.get_object().pk)
        obj.visa_dg_par = request.user
        obj.visa_dg_motif = motif
        obj.visa_dg_le = timezone.now()
        obj.save(update_fields=["visa_dg_par", "visa_dg_motif", "visa_dg_le", "updated_at"])
        return Response(self.get_serializer(obj).data)


class PurchaseRequestLineViewSet(_CommonViewSet):
    serializer_class = PurchaseRequestLineSerializer

    def get_queryset(self):
        qs = PurchaseRequestLine.objects.select_related("article", "unit").all()
        request_id = self.request.query_params.get("request")
        if request_id:
            qs = qs.filter(request_id=request_id)
        return qs


class ConsultationRequestViewSet(_CommonViewSet):
    serializer_class = ConsultationRequestSerializer
    search_fields = ("code", "subject",)

    def get_queryset(self):
        qs = ConsultationRequest.objects.select_related("request").all()
        status_ = self.request.query_params.get("status")
        if status_:
            qs = qs.filter(status=status_)
        return qs

    def _consultation(self):
        return ConsultationRequest.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def ouvrir(self, request, pk=None):
        """Mise en concurrence : la consultation est envoyée aux fournisseurs (CDC M2 §5.3)."""
        consultation = self._consultation()
        if consultation.status != ConsultationRequest.Status.BROUILLON:
            return Response({"detail": "Seule une consultation en brouillon s'ouvre."}, status=status.HTTP_400_BAD_REQUEST)
        consultation.status = ConsultationRequest.Status.OUVERTE
        consultation.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(consultation).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def cloturer(self, request, pk=None):
        """Clôture de la mise en concurrence : une et une seule offre retenue."""
        consultation = self._consultation()
        if consultation.status != ConsultationRequest.Status.OUVERTE:
            return Response({"detail": "Seule une consultation ouverte se clôture."}, status=status.HTTP_400_BAD_REQUEST)
        retenues = consultation.offers.filter(is_selected=True).count()
        if retenues != 1:
            return Response({"detail": "Retenez une et une seule offre fournisseur avant de clôturer."},
                            status=status.HTTP_400_BAD_REQUEST)
        consultation.status = ConsultationRequest.Status.CLOTUREE
        consultation.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(consultation).data)


class ConsultationOfferViewSet(_CommonViewSet):
    serializer_class = ConsultationOfferSerializer
    search_fields = ("consultation__code", "supplier__name",)

    def get_queryset(self):
        qs = ConsultationOffer.objects.select_related("consultation", "supplier").all()
        consultation = self.request.query_params.get("consultation")
        if consultation:
            qs = qs.filter(consultation_id=consultation)
        return qs

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def retenir(self, request, pk=None):
        """Retient cette offre (et une seule) tant que la consultation est ouverte."""
        offre = ConsultationOffer.objects.select_for_update(of=("self",)).select_related("consultation").get(
            pk=self.get_object().pk
        )
        if offre.consultation.status != ConsultationRequest.Status.OUVERTE:
            return Response({"detail": "Seule une consultation ouverte permet de retenir une offre."},
                            status=status.HTTP_400_BAD_REQUEST)
        offre.consultation.offers.exclude(pk=offre.pk).update(is_selected=False)
        offre.is_selected = True
        offre.save(update_fields=["is_selected"])
        return Response(self.get_serializer(offre).data)


class PurchaseOrderViewSet(_CommonViewSet):
    serializer_class = PurchaseOrderSerializer
    search_fields = ("code", "supplier__name", "supplier__code",)

    def get_queryset(self):
        qs = PurchaseOrder.objects.select_related(
            "supplier", "request", "consultation", "currency"
        ).prefetch_related("lines__invoice_lines")
        status_ = self.request.query_params.get("status")
        if status_:
            qs = qs.filter(status=status_)
        if self.request.query_params.get("supplier"):
            qs = qs.filter(supplier_id=self.request.query_params["supplier"])
        if self.request.query_params.get("global_rental") is not None:
            gr = self.request.query_params["global_rental"].lower() in ("1", "true", "yes")
            qs = qs.filter(is_global_rental=gr)
        return qs

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def confirmer(self, request, pk=None):
        """Engagement du BC : contrôles CDC M2 avant émission vers le fournisseur."""
        order = PurchaseOrder.objects.select_for_update(of=("self",)).select_related("supplier").get(pk=self.get_object().pk)
        if order.status != PurchaseOrder.Status.BROUILLON:
            return Response({"detail": f"BC {order.get_status_display().lower()} : confirmation impossible."},
                            status=status.HTTP_400_BAD_REQUEST)
        if not order.lines.exists():
            return Response({"detail": "BC sans ligne : rien à engager."}, status=status.HTTP_400_BAD_REQUEST)
        jour = timezone.localdate()
        # M2 §5.8 : aucun BC émis vers un fournisseur non agréé qualité / HSE.
        if order.supplier is None or not order.supplier.agrement_valide(jour):
            nom = order.supplier.name if order.supplier else "non renseigné"
            return Response({"supplier": f"Fournisseur {nom} non agréé qualité / HSE (ou agrément expiré) : BC non émis."},
                            status=status.HTTP_400_BAD_REQUEST)
        # RG-M2.08 : > 110 % du budget consommé → aucun engagement (sauf visa exceptionnel DG).
        blocage = budget_control.controler(
            order.analytic, jour, order.total, budget_control.SEUIL_ENGAGEMENT, f"le BC {order.code}",
            visa_dg=bool(order.visa_dg_par_id),
        )
        if blocage:
            return Response({"budget": blocage}, status=status.HTTP_400_BAD_REQUEST)
        order.status = PurchaseOrder.Status.CONFIRMEE
        order.save(update_fields=["status"])
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def annuler(self, request, pk=None):
        order = PurchaseOrder.objects.select_for_update().get(pk=self.get_object().pk)
        if order.status not in (PurchaseOrder.Status.BROUILLON, PurchaseOrder.Status.CONFIRMEE):
            return Response({"detail": "Seul un BC brouillon ou confirmé sans réception s'annule."},
                            status=status.HTTP_400_BAD_REQUEST)
        if order.lines.filter(received_qty__gt=0).exists():
            return Response({"detail": "Réception enregistrée : annulez d'abord les réceptions."}, status=status.HTTP_400_BAD_REQUEST)
        order.status = PurchaseOrder.Status.ANNULEE
        order.save(update_fields=["status"])
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["post"], url_path="visa-dg")
    @transaction.atomic
    def visa_dg(self, request, pk=None):
        """Visa exceptionnel du DG : lève les blocages budgétaires RG-M2.08 pour cette pièce (motif obligatoire)."""
        if not can_viser_dg(request.user):
            return Response({"detail": "Visa exceptionnel réservé à la Direction Générale."}, status=status.HTTP_403_FORBIDDEN)
        motif = (request.data.get("motif") or "").strip()
        if not motif:
            return Response({"motif": "Motif du visa exceptionnel obligatoire."}, status=status.HTTP_400_BAD_REQUEST)
        obj = self.get_queryset().model.objects.select_for_update().get(pk=self.get_object().pk)
        obj.visa_dg_par = request.user
        obj.visa_dg_motif = motif
        obj.visa_dg_le = timezone.now()
        obj.save(update_fields=["visa_dg_par", "visa_dg_motif", "visa_dg_le", "updated_at"])
        return Response(self.get_serializer(obj).data)

    @transaction.atomic
    def perform_create(self, serializer):
        order = serializer.save(created_by=self.request.user)
        # Le BC hérite de l'imputation analytique de sa DA (sinon le contrôle budgétaire RG-M2.08 serait contourné).
        if order.request_id and not order.analytic_id and order.request.analytic_id:
            order.analytic_id = order.request.analytic_id
            order.save(update_fields=["analytic"])
        # La DA approuvée à l'origine du BC est désormais « convertie en commande ».
        if order.request_id and order.request.status == PurchaseRequest.Status.APPROUVEE:
            order.request.status = PurchaseRequest.Status.CONVERTIE
            order.request.save(update_fields=["status", "updated_at"])

    @action(detail=False, methods=["get"], url_path="performance-fournisseurs")
    def performance_fournisseurs(self, request):
        """Notation fournisseur : taux de service, retard moyen, conformité qualité, litiges (CDC M2 §5.4 / §5.7)."""
        from .pilotage import performance_fournisseurs

        return Response(performance_fournisseurs())

    @action(detail=False, methods=["get"], url_path="reporting")
    def reporting(self, request):
        """Reporting achats : prix moyens par article, engagements par axe analytique (→ M11), fournisseurs."""
        from .pilotage import reporting_achats

        return Response(reporting_achats(can_see_amount(request.user)))

    @action(detail=True, methods=["get"], url_path="reconciliation")
    def reconciliation(self, request, pk=None):
        """Rapprochement 3-way (RF-ERP-12) : commandé / reçu / facturé par ligne."""
        order = self.get_object()
        return Response({"code": order.code, "conformity": order.conformity})


class PurchaseOrderLineViewSet(_CommonViewSet):
    serializer_class = PurchaseOrderLineSerializer

    def get_queryset(self):
        qs = PurchaseOrderLine.objects.select_related("purchase_order", "article", "unit").all()
        purchase_order = self.request.query_params.get("purchase_order")
        if purchase_order:
            qs = qs.filter(purchase_order_id=purchase_order)
        return qs


class GoodsReceiptViewSet(_CommonViewSet):
    serializer_class = GoodsReceiptSerializer
    search_fields = ("code", "purchase_order__code",)

    def get_queryset(self):
        qs = GoodsReceipt.objects.select_related("purchase_order", "received_by").all()
        purchase_order = self.request.query_params.get("purchase_order")
        if purchase_order:
            qs = qs.filter(purchase_order_id=purchase_order)
        return qs

    def perform_create(self, serializer):
        serializer.save(received_by=self.request.user)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def valider(self, request, pk=None):
        """Réception validée seulement après le contrôle qualité M6 validé conforme ou accepté sous réserve (§5.11)."""
        from qualite.models import ControleQualite

        receipt = GoodsReceipt.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if receipt.status != GoodsReceipt.Status.EN_ATTENTE:
            return Response({"detail": "Réception déjà validée ou annulée."}, status=status.HTTP_400_BAD_REQUEST)
        ctrl = receipt.controles_qualite.order_by("-created_at").first()
        if ctrl is None or ctrl.statut != ControleQualite.Statut.VALIDE:
            return Response({"detail": "Contrôle qualité à réception (M6) non validé : réception en attente."},
                            status=status.HTTP_400_BAD_REQUEST)
        if ctrl.resultat == ControleQualite.Resultat.NON_CONFORME:
            return Response({"detail": f"Contrôle qualité {ctrl.code} non conforme : ouvrez un litige fournisseur."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            entrer_en_stock(receipt, request.user, request.data.get("depot"))
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict if hasattr(exc, "error_dict") else {"detail": exc.messages})
        receipt.status = GoodsReceipt.Status.VALIDE
        receipt.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(receipt).data)

    def perform_destroy(self, instance):
        if instance.status != GoodsReceipt.Status.EN_ATTENTE:
            raise ValidationError({"detail": "Réception validée : suppression impossible (le stock a été alimenté)."})
        instance.delete()


class LitigeFournisseurViewSet(_CommonViewSet):
    """Litiges fournisseurs (clôture M2) : relance, escalade en pré-contentieux M12, résolution motivée."""

    serializer_class = LitigeFournisseurSerializer
    search_fields = ("code", "purchase_order__code",)

    def get_queryset(self):
        qs = LitigeFournisseur.objects.select_related("purchase_order__supplier", "contentieux")
        params = self.request.query_params
        if statut := params.get("statut"):
            qs = qs.filter(statut=statut)
        if fournisseur := params.get("fournisseur"):
            qs = qs.filter(purchase_order__supplier_id=fournisseur)
        if params.get("ouverts") == "1":
            qs = qs.exclude(statut=LitigeFournisseur.Statut.RESOLU)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def _litige(self):
        litige = LitigeFournisseur.objects.select_for_update(of=("self",)).select_related("purchase_order__supplier").get(
            pk=self.get_object().pk
        )
        if litige.statut == LitigeFournisseur.Statut.RESOLU:
            raise ValidationError({"detail": "Litige déjà résolu."})
        return litige

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def relancer(self, request, pk=None):
        litige = self._litige()
        litige.nb_relances += 1
        litige.derniere_relance_le = timezone.now()
        if litige.statut == LitigeFournisseur.Statut.OUVERT:
            litige.statut = LitigeFournisseur.Statut.RELANCE
        litige.save()
        return Response(self.get_serializer(litige).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def escalader(self, request, pk=None):
        """Escalade : ouverture d'un pré-contentieux fournisseur au module juridique (M12), lié au litige."""
        from juridique.models import Contentieux

        litige = self._litige()
        if litige.contentieux_id:
            raise ValidationError({"detail": "Litige déjà escaladé."})
        bc = litige.purchase_order
        litige.contentieux = Contentieux.objects.create(
            nature=Contentieux.Nature.FOURNISSEUR,
            phase=Contentieux.Phase.PRE_CONTENTIEUX,
            objet=f"Litige {litige.code} — BC {bc.code} : {litige.get_type_display()}"[:250],
            partie_adverse=bc.supplier.name if bc.supplier_id else "Fournisseur",
            montant_en_jeu=litige.montant_en_jeu or 0,
            reference=litige.code,
        )
        litige.statut = LitigeFournisseur.Statut.ESCALADE
        litige.save()
        return Response(self.get_serializer(litige).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def resoudre(self, request, pk=None):
        litige = self._litige()
        resolution = str(request.data.get("resolution") or "").strip()
        if not resolution:
            raise ValidationError({"resolution": "Résolution obligatoire (avoir, remplacement, abandon…)."})
        litige.resolution, litige.resolu_le, litige.statut = resolution, timezone.now(), LitigeFournisseur.Statut.RESOLU
        litige.save()
        return Response(self.get_serializer(litige).data)


class GoodsReceiptLineViewSet(_CommonViewSet):
    serializer_class = GoodsReceiptLineSerializer

    def get_queryset(self):
        qs = GoodsReceiptLine.objects.select_related("receipt", "purchase_order_line").all()
        receipt = self.request.query_params.get("receipt")
        if receipt:
            qs = qs.filter(receipt_id=receipt)
        return qs

    @idempotent
    def create(self, request, *args, **kwargs):  # réception magasin rejouable (hors-ligne)
        return super().create(request, *args, **kwargs)

    @staticmethod
    def _garde_reception_ouverte(receipt):
        # Réception validée = stock alimenté : ses lignes ne bougent plus (correction = mouvement de stock inverse).
        if receipt.status != GoodsReceipt.Status.EN_ATTENTE:
            raise ValidationError({"detail": "Réception validée : lignes non modifiables."})

    def perform_create(self, serializer):
        self._garde_reception_ouverte(serializer.validated_data["receipt"])
        serializer.save()

    def perform_update(self, serializer):
        self._garde_reception_ouverte(serializer.instance.receipt)
        serializer.save()

    def perform_destroy(self, instance):
        self._garde_reception_ouverte(instance.receipt)
        instance.delete()


class PurchaseInvoiceViewSet(_CommonViewSet):
    serializer_class = PurchaseInvoiceSerializer
    search_fields = ("code", "invoice_ref", "supplier__name",)

    def get_permissions(self):
        # La comptabilisation relève du cercle comptable (CanValidateCompta), pas des rôles d'écriture Achats.
        if self.action == "comptabiliser":
            return [CanValidateCompta()]
        return super().get_permissions()

    def get_queryset(self):
        qs = PurchaseInvoice.objects.select_related("purchase_order", "supplier", "currency", "move").all()
        status_ = self.request.query_params.get("status")
        if status_:
            qs = qs.filter(status=status_)
        purchase_order = self.request.query_params.get("purchase_order")
        if purchase_order:
            qs = qs.filter(purchase_order_id=purchase_order)
        return qs

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def rapprocher(self, request, pk=None):
        """Rapprochement 3-way BR / BC / facture (CDC M2 §5.8) : préalable obligatoire à la comptabilisation."""
        invoice = PurchaseInvoice.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if invoice.status != PurchaseInvoice.Status.EN_ATTENTE:
            return Response({"detail": f"Facture {invoice.get_status_display().lower()} : rapprochement impossible."},
                            status=status.HTTP_400_BAD_REQUEST)
        lignes = list(invoice.lines.select_related("purchase_order_line"))
        if not lignes:
            return Response({"detail": "Facture sans ligne : rien à rapprocher."}, status=status.HTTP_400_BAD_REQUEST)
        anomalies = []
        for inv_line in lignes:
            po_line = inv_line.purchase_order_line
            if po_line.purchase_order_id != invoice.purchase_order_id:
                anomalies.append(f"{po_line.label} : ligne d'un autre BC.")
            if po_line.invoiced_qty > po_line.received_qty:
                anomalies.append(f"{po_line.label} : facturé {po_line.invoiced_qty} > reçu {po_line.received_qty}.")
            if abs(inv_line.unit_price - po_line.unit_price) > Decimal("0.01"):
                anomalies.append(f"{po_line.label} : prix facturé {inv_line.unit_price} ≠ commandé {po_line.unit_price}.")
        if anomalies:
            return Response({"three_way": anomalies}, status=status.HTTP_400_BAD_REQUEST)
        invoice.status = PurchaseInvoice.Status.RAPPROCHEE
        invoice.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(invoice).data)

    @action(detail=True, methods=["post"])
    def comptabiliser(self, request, pk=None):
        """Écriture d'achat (CDC M2 §5.10) : Dr charge HT (618 si BC GR) + Dr TVA déductible / Cr 401. Facture scellée."""
        try:
            invoice = comptabiliser_facture(self.get_object(), request.user)
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict if hasattr(exc, "error_dict") else {"detail": exc.messages})
        return Response(self.get_serializer(invoice).data)


class PurchaseInvoiceLineViewSet(_CommonViewSet):
    serializer_class = PurchaseInvoiceLineSerializer

    @staticmethod
    def _garde_facture_ouverte(invoice):
        # Facture rapprochée ou comptabilisée = pièce scellée : plus d'ajout, de modification ni de suppression de ligne.
        if invoice.status != PurchaseInvoice.Status.EN_ATTENTE:
            raise ValidationError({"detail": f"Facture {invoice.get_status_display().lower()} : lignes non modifiables."})

    def perform_create(self, serializer):
        self._garde_facture_ouverte(serializer.validated_data["invoice"])
        serializer.save()

    def perform_update(self, serializer):
        self._garde_facture_ouverte(serializer.instance.invoice)
        serializer.save()

    def perform_destroy(self, instance):
        self._garde_facture_ouverte(instance.invoice)
        instance.delete()

    def get_queryset(self):
        qs = PurchaseInvoiceLine.objects.select_related("invoice", "purchase_order_line").all()
        invoice = self.request.query_params.get("invoice")
        if invoice:
            qs = qs.filter(invoice_id=invoice)
        return qs