"""Réception → stock (CDC M2 §5.10 aval M5 « réception → mise en stock »).

À la validation d'une réception, chaque ligne dont l'article est géré en stock crée une entrée au dépôt de réception, au
prix du BC (valorisation CUMP par `stocks.services.apply_move`). Écart M2 : le n° de lot et le certificat MTC / CoC
saisis sur la ligne de réception créent le lot et son certificat dans M5 (certificat à valider par QA/QC en M5) ; un
article à lot obligatoire ne se réceptionne pas sans n° de lot.
"""

from django.core.exceptions import ValidationError
from django.utils import timezone

from stocks.models import ArticleStock, CertificatMatiere, Depot, LotMatiere, MouvementStock
from stocks.services import apply_move


def _depot_reception(depot_id):
    actifs = Depot.objects.filter(is_active=True)
    if depot_id:
        try:
            return actifs.get(pk=depot_id)
        except (Depot.DoesNotExist, ValueError, ValidationError):
            raise ValidationError({"depot": "Dépôt de réception introuvable ou inactif."})
    if actifs.count() == 1:
        return actifs.get()
    raise ValidationError(
        {"depot": "Dépôt de réception à préciser (plusieurs dépôts actifs)." if actifs.exists()
         else "Aucun dépôt actif : créez un dépôt (Stocks) avant de valider une réception d'articles stockés."}
    )


def _lot_et_certificat(receipt, ligne):
    """Crée le lot (quantité portée par l'entrée de stock) et son certificat matière saisis à la réception."""
    from .models import GoodsReceiptLine

    po_line = ligne.purchase_order_line
    lot = LotMatiere.objects.create(
        article=po_line.article, numero_lot=ligne.numero_lot.strip(), numero_coulee=ligne.numero_coulee.strip(),
        date_reception=receipt.received_at or timezone.localdate(), date_peremption=ligne.date_peremption,
        quantite_initiale=ligne.quantity, quantite_restante=0,
    )
    if ligne.certificat_type and ligne.numero_certificat.strip():
        CertificatMatiere.objects.create(
            lot=lot, type=ligne.certificat_type, numero_certificat=ligne.numero_certificat.strip(),
            fournisseur=po_line.purchase_order.supplier, organisme=ligne.organisme_certificat.strip(),
            notes=f"Saisi à la réception {receipt.code} — à valider par QA/QC (M5).",
        )
    GoodsReceiptLine.objects.filter(pk=ligne.pk).update(lot=lot)
    return lot


def entrer_en_stock(receipt, user, depot_id=None):
    """Crée et applique les entrées de stock de la réception ; renvoie les mouvements (vide si rien n'est stockable)."""
    lignes = [
        ligne
        for ligne in receipt.lines.select_related("purchase_order_line__article", "purchase_order_line__purchase_order__supplier")
        if ligne.quantity > 0
        and ligne.purchase_order_line.article_id
        and ligne.purchase_order_line.article.is_stockable
    ]
    if not lignes:
        return []
    if MouvementStock.objects.filter(document_reference=receipt.code, type_mouvement=MouvementStock.Type.RECEPTION).exists():
        raise ValidationError("Entrée en stock déjà enregistrée pour cette réception.")
    obligatoires = set(
        ArticleStock.objects.filter(
            article_id__in=[ligne.purchase_order_line.article_id for ligne in lignes], lot_obligatoire=True
        ).values_list("article_id", flat=True)
    )
    for ligne in lignes:
        if ligne.purchase_order_line.article_id in obligatoires and not ligne.numero_lot.strip():
            raise ValidationError({"numero_lot": (
                f"Lot obligatoire pour l'article {ligne.purchase_order_line.article.code} (traçabilité client pétrolier) : "
                "renseignez le n° de lot sur la ligne de réception."
            )})
    depot = _depot_reception(depot_id)
    mouvements = []
    for ligne in lignes:
        po_line = ligne.purchase_order_line
        lot = _lot_et_certificat(receipt, ligne) if ligne.numero_lot.strip() else None
        mouvement = MouvementStock.objects.create(
            type_mouvement=MouvementStock.Type.RECEPTION,
            article=po_line.article,
            lot=lot,
            quantite=ligne.quantity,
            prix_unitaire=po_line.unit_price,
            devise=po_line.purchase_order.currency,
            destination=depot,
            document_reference=receipt.code,
            date=receipt.received_at or timezone.localdate(),
            created_by=user,
            notes=f"Réception {receipt.code} — BC {po_line.purchase_order.code}",
        )
        try:
            mouvements.append(apply_move(mouvement))
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)})
    return mouvements
