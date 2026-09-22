"""Droits métier M5 (RF-ERP-40…43) + moteur de stock (double-entrée) + valorisation.

Écriture : Logistique & Magasin, Direction des Opérations, Chefs d'atelier
/ chantier (consommations OF), appui Projets (M1), Finance (valorisation),
Direction.
Montants (prix, valeur du stock) : restreints hors rôles autorisés (RF-59,
pattern `logistique` M4).

Stock en double-entrée (concept Odoo `quant` + `move`, jamais copié) :
`apply_move` débite le dépôt source et crédite la destination sous verrou
`select_for_update`, et met à jour la quantité restante du lot. La valeur est
tenue en **CUMP** (coût moyen pondéré) — comptes 31 SYSCOHADA → M10.
"""

from django.db import transaction
from rest_framework.permissions import BasePermission

from users.models import User

from .models import Inventaire, InventaireLigne, LotMatiere, MouvementStock, StockQuant

STOCK_WRITE_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.DIRECTEUR_PROJETS,
    User.Role.DIRECTEUR_OPERATIONS,
    User.Role.LOGISTIQUE,
    User.Role.FINANCE,
    User.Role.MAINTENANCE,
    User.Role.CHEF_ATELIER,
    User.Role.DIRECTION,
)

STOCK_AMOUNT_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.DIRECTEUR_PROJETS,
    User.Role.DIRECTEUR_OPERATIONS,
    User.Role.FINANCE,
    User.Role.COMPTABLE,
    User.Role.DIRECTION,
)


def is_admin_or_staff(user):
    return user.is_authenticated and (
        user.is_staff or user.is_superuser or user.role == User.Role.ADMIN
    )


def can_manage_stocks(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in STOCK_WRITE_ROLES


def can_see_amount(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in STOCK_AMOUNT_ROLES


class CanManageStocks(BasePermission):
    """Écriture réservée aux rôles Magasin / Opérations / Direction."""

    def has_permission(self, request, view):
        return can_manage_stocks(getattr(request, "user", None))


def _quant(depot, article, lot):
    """Récupère ou crée le quant (dépôt, article, lot) sous verrou."""
    qs = StockQuant.objects.select_for_update().filter(depot=depot, article=article)
    if lot:
        quant = qs.filter(lot=lot).first()
        if not quant:
            quant = StockQuant.objects.select_for_update().create(
                depot=depot, article=article, lot=lot
            )
    else:
        quant = qs.filter(lot__isnull=True).first()
        if not quant:
            quant = StockQuant.objects.select_for_update().create(
                depot=depot, article=article, lot=None
            )
    return quant


@transaction.atomic
def apply_move(mouvement):
    """Applique un mouvement aux quants (double-entrée) et aux lots.

    Entrée : crédite la destination (CUMP) · Sortie : débite la source
    (le stock sort à sa valeur moyenne) · Transfert : les deux.
    """
    if mouvement.executed:
        return mouvement
    if mouvement.source:
        src = _quant(mouvement.source, mouvement.article, mouvement.lot)
        if float(src.quantity) + 1e-9 < float(mouvement.quantite):
            raise ValueError(
                f"Stock insuffisant au dépôt {mouvement.source.label} : "
                f"{float(src.quantity)} dispo pour {float(mouvement.quantite)}."
            )
        unit_cost = src.stock_value / src.quantity if float(src.quantity) > 0 else 0
        src.quantity -= mouvement.quantite
        src.stock_value -= mouvement.quantite * unit_cost
        if float(src.quantity) <= 1e-9:
            src.quantity = 0
            src.stock_value = 0
        src.save(update_fields=["quantity", "stock_value", "updated_at"])
    if mouvement.destination:
        dst = _quant(mouvement.destination, mouvement.article, mouvement.lot)
        nouveau_qty = dst.quantity + mouvement.quantite
        if float(dst.quantity) > 0 or float(mouvement.prix_unitaire) <= 0:
            dst.stock_value += mouvement.quantite * mouvement.prix_unitaire
        else:
            dst.stock_value = mouvement.quantite * mouvement.prix_unitaire
        dst.quantity = nouveau_qty
        dst.save(update_fields=["quantity", "stock_value", "updated_at"])
    if mouvement.lot:
        lot = LotMatiere.objects.select_for_update().get(pk=mouvement.lot.pk)
        if mouvement.source and not mouvement.destination:
            lot.quantite_restante -= mouvement.quantite
        elif mouvement.destination and not mouvement.source:
            lot.quantite_restante += mouvement.quantite
        if float(lot.quantite_restante) < 0:
            lot.quantite_restante = 0
        lot.refresh_statut()
        lot.save(update_fields=["quantite_restante", "statut", "updated_at"])
    mouvement.executed = True
    mouvement.save(update_fields=["executed", "updated_at"])
    return mouvement


@transaction.atomic
def cloturer_inventaire(inventaire, user):
    """Clôture un inventaire : crée et applique un mouvement par écart (RF-ERP-43)."""
    inventaire = Inventaire.objects.select_for_update().get(pk=inventaire.pk)
    if inventaire.statut == Inventaire.Statut.CLOTURE:
        return inventaire
    for ligne in InventaireLigne.objects.filter(inventaire=inventaire).select_related(
        "article", "lot", "inventaire__depot"
    ):
        ecart = ligne.ecart  # Decimal
        if abs(float(ecart)) < 1e-9:
            continue
        mouvement = MouvementStock.objects.create(
            type_mouvement=MouvementStock.Type.INVENTAIRE,
            article=ligne.article,
            quantite=abs(ecart),
            source=inventaire.depot if ecart < 0 else None,
            destination=None if ecart < 0 else inventaire.depot,
            lot=ligne.lot,
            document_reference=inventaire.code,
            date=inventaire.date,
            created_by=user,
        )
        apply_move(mouvement)
    inventaire.statut = Inventaire.Statut.CLOTURE
    inventaire.save(update_fields=["statut", "updated_at"])
    return inventaire


def valuation(depot_id=None):
    """Valorisation du stock par article — méthode ArticleStock (RF-ERP-42).

    Valeur unitaire = stock_value / quantity (CUMP tenu par `apply_move`) ;
    méthode configurée révélée (FIFO / PEPS / CUMP / PP).
    """
    from django.db.models import Q

    quants = StockQuant.objects.select_related("depot", "article", "article__stock_config")
    if depot_id:
        quants = quants.filter(depot_id=depot_id)
    rows = []
    for quant in quants:
        config = getattr(quant.article, "stock_config", None)
        method = "cump"
        if config and config.methode:
            method = config.methode
        value = float(quant.stock_value)
        qty = float(quant.quantity)
        if method == "pp" and config:
            value = qty * float(config.prix_standard)
        rows.append(
            {
                "depot": quant.depot.code,
                "article": quant.article.code,
                "label": quant.article.label,
                "quantity": qty,
                "value": value,
                "unit_cost": (value / qty) if qty else 0,
                "method": method,
                "lot": quant.lot.code if quant.lot else None,
            }
        )
    return rows


def traceabilite(article_id=None, lot_id=None):
    """Traçabilité amont / aval d'un article ou lot (RF-ERP-41).

    Chaîne des mouvements source → destination avec références documents
    (BC / BL / OF / INV) pour remonter l'origine et suivre la consommation.
    """
    qs = MouvementStock.objects.select_related(
        "article", "source", "destination", "lot", "ordre", "created_by"
    )
    if article_id:
        qs = qs.filter(article_id=article_id)
    if lot_id:
        qs = qs.filter(lot_id=lot_id)
    return [
        {
            "code": m.code,
            "date": m.date,
            "type": m.type_mouvement,
            "type_label": m.get_type_mouvement_display(),
            "article": m.article.code,
            "quantite": float(m.quantite),
            "prix_unitaire": float(m.prix_unitaire),
            "source": m.source.code if m.source else None,
            "destination": m.destination.code if m.destination else None,
            "lot": m.lot.code if m.lot else None,
            "ordre": m.ordre.code if m.ordre else None,
            "reference": m.document_reference,
        }
        for m in qs.order_by("date", "code")
    ]