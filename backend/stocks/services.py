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
from django.utils import timezone
from rest_framework.permissions import BasePermission

from users.models import User
from users.rbac import can_read_app

from .models import ArticleStock, Inventaire, InventaireLigne, LotMatiere, MouvementStock, StockQuant  # noqa: F401

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
    """Lecture réservée aux rôles Magasin / Opérations / Direction, écriture idem."""

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return can_read_app(getattr(request, "user", None), "stocks")
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


SORTIES_CONTROLEES = (MouvementStock.Type.CONSOMMATION, MouvementStock.Type.TRANSFERT)


def controler_sortie_lot(mouvement):
    """CDC M5 §7.8 / §7.11 : aucune sortie (consommation, transfert) d'un lot en quarantaine, périmé ou dont le
    certificat MTC / CoC n'est pas validé et conforme. Le retour fournisseur reste possible (traitement d'un lot non
    conforme) ; l'entrée et l'inventaire ne sont pas des sorties."""
    if not (mouvement.lot_id and mouvement.source_id and mouvement.type_mouvement in SORTIES_CONTROLEES):
        return
    lot = mouvement.lot
    if lot.statut == LotMatiere.Statut.BLOQUE:
        raise ValueError(f"Lot {lot.code} ({lot.numero_lot}) en quarantaine : sortie interdite (CDC M5 §7.8).")
    jour = mouvement.date or timezone.localdate()
    if lot.date_peremption and lot.date_peremption < jour:
        raise ValueError(f"Lot {lot.code} ({lot.numero_lot}) périmé depuis le {lot.date_peremption} : sortie interdite.")
    certificats = list(lot.certificats.all())
    if certificats:
        if not any(c.conforme and c.date_validation for c in certificats):
            raise ValueError(
                f"Lot {lot.code} ({lot.numero_lot}) : certificat MTC / CoC non validé ou non conforme — sortie interdite."
            )
    elif ArticleStock.objects.filter(article_id=mouvement.article_id, certificat_requis=True).exists():
        raise ValueError(
            f"Lot {lot.code} ({lot.numero_lot}) sans certificat MTC / CoC : exigé pour cet article (traçabilité pétrolière)."
        )


@transaction.atomic
def apply_move(mouvement):
    """Applique un mouvement aux quants (double-entrée) et aux lots.

    Entrée : crédite la destination (CUMP) · Sortie : débite la source
    (le stock sort à sa valeur moyenne) · Transfert : les deux.
    """
    if mouvement.executed:
        return mouvement
    controler_lot_obligatoire(mouvement.article_id, mouvement.lot_id)
    controler_sortie_lot(mouvement)
    prix = mouvement.prix_unitaire
    cout = prix
    if mouvement.source:
        src = _quant(mouvement.source, mouvement.article, mouvement.lot)
        if float(src.quantity) + 1e-9 < float(mouvement.quantite):
            raise ValueError(
                f"Stock insuffisant au dépôt {mouvement.source.label} : "
                f"{float(src.quantity)} dispo pour {float(mouvement.quantite)}."
            )
        unit_cost = src.stock_value / src.quantity if float(src.quantity) > 0 else 0
        if mouvement.destination:
            # Transfert : la destination reçoit au COÛT de la source (valeur conservée),
            # jamais au « prix unitaire » saisi (0 par défaut => valeur détruite).
            prix = unit_cost
        cout = unit_cost
        src.quantity -= mouvement.quantite
        src.stock_value -= mouvement.quantite * unit_cost
        if float(src.quantity) <= 1e-9:
            src.quantity = 0
            src.stock_value = 0
        src.save(update_fields=["quantity", "stock_value", "updated_at"])
    if mouvement.destination:
        dst = _quant(mouvement.destination, mouvement.article, mouvement.lot)
        nouveau_qty = dst.quantity + mouvement.quantite
        if float(dst.quantity) > 0 or float(prix) <= 0:
            dst.stock_value += mouvement.quantite * prix
        else:
            dst.stock_value = mouvement.quantite * prix
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
    mouvement.cout_unitaire = cout
    if not mouvement.analytic_id and mouvement.ordre_id and mouvement.ordre.affaire_id:
        mouvement.analytic = mouvement.ordre.affaire.assurer_compte_analytique()
    mouvement.executed = True
    mouvement.save(update_fields=["executed", "cout_unitaire", "analytic", "updated_at"])
    return mouvement


@transaction.atomic
def cloturer_inventaire(inventaire, user):
    """Clôture un inventaire : crée et applique un mouvement par écart (RF-ERP-43)."""
    inventaire = Inventaire.objects.select_for_update().get(pk=inventaire.pk)
    if inventaire.statut == Inventaire.Statut.CLOTURE:
        return inventaire
    if InventaireLigne.objects.filter(inventaire=inventaire, comptee=False).exists():
        raise ValueError("Des lignes de l'inventaire n'ont pas encore été comptées : clôture impossible.")
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


# ----------------------------------------------------------------------------------------------------------------
# Écarts M5 (2026-10-19) : lot obligatoire, quarantaine, certificats, alertes, bon de sortie, archivage GED
# ----------------------------------------------------------------------------------------------------------------
QUALITE_ROLES = (
    User.Role.ADMIN, User.Role.QAQC, User.Role.DIRECTEUR_OPERATIONS, User.Role.DIRECTEUR_PROJETS, User.Role.DIRECTION,
)
ROLES_ALERTE_STOCK = (User.Role.LOGISTIQUE, User.Role.DIRECTEUR_OPERATIONS)
PARAMETRES_STOCK_DEFAUT = {
    "PEREMPTION_ALERTE_JOURS": ("Alerte de péremption des lots", "30", "jours"),
    "CERTIFICAT_RETENTION_ANS": ("Conservation des certificats matière en GED", "10", "ans"),
}
TYPE_GED_CERTIFICAT = "certificats-matiere"
TYPE_GED_PIECE_STOCK = "pieces-stock"


def peut_valider_qualite(user):
    return bool(user and user.is_authenticated and (user.is_staff or user.role in QUALITE_ROLES))


class CanQualiteStock(BasePermission):
    """Validation d'un certificat, quarantaine / levée : QA/QC et hiérarchie (CDC M5 §7.4)."""

    def has_permission(self, request, view):
        return peut_valider_qualite(getattr(request, "user", None))


def get_param_stock(code):
    from decimal import Decimal

    from .models import ParametreStock

    label, valeur, unite = PARAMETRES_STOCK_DEFAUT[code]
    obj, _ = ParametreStock.objects.get_or_create(code=code, defaults={"label": label, "valeur": Decimal(valeur), "unite": unite})
    return obj.valeur


def parametres_stock_provisoires():
    from .models import ParametreStock

    for code in PARAMETRES_STOCK_DEFAUT:
        get_param_stock(code)
    return ParametreStock.objects.exclude(statut_valeur="confirme").exists()


def controler_lot_obligatoire(article_id, lot_id):
    """Traçabilité client pétrolier : un article à lot obligatoire ne bouge jamais sans lot."""
    if not lot_id and ArticleStock.objects.filter(article_id=article_id, lot_obligatoire=True).exists():
        raise ValueError("Lot obligatoire pour cet article (traçabilité client pétrolier) : renseigner le lot.")


def alertes_stock(aujourdhui=None):
    """Stock sous le seuil minimal (toutes quantités de l'article), lots périmés ou proches de la péremption
    (délai paramétrable), lots en stock dont le fournisseur certifiant n'est plus agréé qualité / HSE (M2)."""
    from datetime import timedelta

    from django.db.models import Sum

    aujourdhui = aujourdhui or timezone.localdate()
    delai = int(get_param_stock("PEREMPTION_ALERTE_JOURS"))
    rows = []
    for cfg in ArticleStock.objects.filter(is_active=True, seuil_minimal__gt=0).select_related("article"):
        stock = StockQuant.objects.filter(article_id=cfg.article_id).aggregate(q=Sum("quantity"))["q"] or 0
        if stock < cfg.seuil_minimal:
            rows.append({"type": "stock_mini", "article": cfg.article.code, "libelle": cfg.article.label, "lot": None,
                         "detail": f"stock {stock:g} < seuil {cfg.seuil_minimal:g}", "date": None, "jours": None})
    lots = LotMatiere.objects.filter(quantite_restante__gt=0).exclude(statut=LotMatiere.Statut.EPUISE).select_related("article")
    for lot in lots.filter(date_peremption__isnull=False, date_peremption__lte=aujourdhui + timedelta(days=delai)):
        jours = (lot.date_peremption - aujourdhui).days
        rows.append({"type": "peremption", "article": lot.article.code, "libelle": lot.article.label, "lot": lot.code,
                     "detail": ("périmé depuis le " if jours < 0 else "péremption le ") + f"{lot.date_peremption:%d/%m/%Y}",
                     "date": lot.date_peremption, "jours": jours})
    from .models import CertificatMatiere

    vus = set()
    for cert in CertificatMatiere.objects.filter(lot__in=lots, fournisseur__isnull=False).select_related("lot", "lot__article", "fournisseur"):
        if cert.lot_id in vus or cert.fournisseur.agrement_valide(aujourdhui):
            continue
        vus.add(cert.lot_id)
        rows.append({"type": "fournisseur_non_agree", "article": cert.lot.article.code, "libelle": cert.lot.article.label,
                     "lot": cert.lot.code, "detail": f"fournisseur {cert.fournisseur.name} non agréé qualité / HSE",
                     "date": None, "jours": None})
    return {"rows": rows, "peremption_jours": delai, "provisoire": parametres_stock_provisoires()}


def notifier_alertes_stock(aujourdhui=None):
    """Notification interne logistique + direction des opérations, une fois par alerte et par jour."""
    from workflow.models import Notification
    from workflow.notifications import notify

    aujourdhui = aujourdhui or timezone.localdate()
    envoyees = 0
    for a in alertes_stock(aujourdhui)["rows"]:
        sujet = f"Stock {aujourdhui:%d/%m} — {a['article']}{' / ' + a['lot'] if a['lot'] else ''} : {a['detail']}"[:255]
        for user in User.objects.filter(role__in=ROLES_ALERTE_STOCK, is_active=True):
            if not Notification.objects.filter(user=user, subject=sujet).exists():
                notify(user, sujet, f"{a['libelle']} : {a['detail']}.", kind="reminder")
                envoyees += 1
    return envoyees


def archiver_piece_ged(contenu, nom, titre, type_code, type_label, retention, reference, user=None, mots=()):
    """Pièce (PDF / scan) scellée SHA-256 en GED, type à rétention minimale garantie ; renvoie le document."""
    import hashlib

    from django.core.files.base import ContentFile

    from documents.models import Document, DocumentType, Version

    type_doc, _ = DocumentType.objects.get_or_create(code=type_code, defaults={"label": type_label, "retention_years": retention})
    if (type_doc.retention_years or 0) < retention:
        type_doc.retention_years = retention
        type_doc.save(update_fields=["retention_years"])
    sha = hashlib.sha256(contenu).hexdigest()
    document = Document.objects.create(
        title=titre[:200], status=Document.Status.ARCHIVED, archived_at=timezone.now(), type=type_doc,
        document_date=timezone.localdate(), reference=reference[:120], keywords=list(mots), sha256=sha, created_by=user,
    )
    version = Version.objects.create(document=document, number=1, file=ContentFile(contenu, name=nom), sha256=sha,
                                     size=len(contenu), original_filename=nom, created_by=user)
    document.current_version = version
    document.save(update_fields=["current_version"])
    return document


def bon_de_sortie_pdf(mouvement):
    """Bon de sortie magasin (consommation / transfert) : pièce imprimable, signée par le magasinier et le receveur."""
    import io

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, title=f"BS {mouvement.code}")
    m = mouvement
    ordre = f"{m.ordre.code}" + (f" — affaire {m.ordre.affaire.code}" if m.ordre_id and m.ordre.affaire_id else "") if m.ordre_id else "—"
    rows = [
        ["Mouvement", m.code, "Date", f"{m.date:%d/%m/%Y}" if m.date else "—"],
        ["Article", f"{m.article.code} — {m.article.label}", "Quantité", f"{m.quantite:g}"],
        ["Lot", f"{m.lot.code} ({m.lot.numero_lot})" if m.lot_id else "—", "Dépôt", m.source.code if m.source_id else "—"],
        ["Ordre de fabrication", ordre, "Destination", m.destination.code if m.destination_id else "Consommation"],
        ["Référence", m.document_reference or "—", "Saisi par", str(m.created_by or "—")],
    ]
    table = Table(rows, colWidths=[35 * mm, 70 * mm, 25 * mm, 50 * mm])
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 9),
                               ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef1f8")),
                               ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#eef1f8"))]))
    signatures = Table([["Magasinier", "Receveur"], ["\n\n\n", "\n\n\n"]], colWidths=[90 * mm, 90 * mm])
    signatures.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey)]))
    doc.build([Paragraph(f"Bon de sortie magasin {m.code}", styles["Title"]), Spacer(1, 4 * mm), table,
               Spacer(1, 10 * mm), signatures])
    return buf.getvalue()
