"""Réception → stock (CDC M2 §5.10 aval M5 « réception → mise en stock »).

À la validation d'une réception, chaque ligne dont l'article est géré en stock crée une entrée au dépôt de réception, au
prix du BC (valorisation CUMP par `stocks.services.apply_move`). Lots et certificats MTC/CoC restent saisis dans M5.
"""

from django.core.exceptions import ValidationError
from django.utils import timezone

from stocks.models import Depot, MouvementStock
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


def entrer_en_stock(receipt, user, depot_id=None):
    """Crée et applique les entrées de stock de la réception ; renvoie les mouvements (vide si rien n'est stockable)."""
    lignes = [
        ligne
        for ligne in receipt.lines.select_related("purchase_order_line__article", "purchase_order_line__purchase_order")
        if ligne.quantity > 0
        and ligne.purchase_order_line.article_id
        and ligne.purchase_order_line.article.is_stockable
    ]
    if not lignes:
        return []
    if MouvementStock.objects.filter(document_reference=receipt.code, type_mouvement=MouvementStock.Type.RECEPTION).exists():
        raise ValidationError("Entrée en stock déjà enregistrée pour cette réception.")
    depot = _depot_reception(depot_id)
    mouvements = []
    for ligne in lignes:
        po_line = ligne.purchase_order_line
        mouvement = MouvementStock.objects.create(
            type_mouvement=MouvementStock.Type.RECEPTION,
            article=po_line.article,
            quantite=ligne.quantity,
            prix_unitaire=po_line.unit_price,
            devise=po_line.purchase_order.currency,
            destination=depot,
            document_reference=receipt.code,
            date=receipt.received_at or timezone.localdate(),
            created_by=user,
            notes=f"Réception {receipt.code} — BC {po_line.purchase_order.code}",
        )
        mouvements.append(apply_move(mouvement))
    return mouvements
