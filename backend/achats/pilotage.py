"""Pilotage achats (clôture M2, CDC §5.4 / §5.7) : notation fournisseur, délais, prix moyens, engagements par axe.

Notation sur 100 : taux de service (commandes livrées complètes à l'heure) 50 points, conformité qualité des
réceptions (contrôles M6 validés conformes) 30 points, litiges 20 points (− 5 points par litige non résolu).
Un critère sans donnée compte pour sa valeur maximale ; sans aucune commande échue, la note n'est pas calculée.
"""

from collections import defaultdict
from decimal import Decimal

from django.db.models import F, Max, Sum
from django.utils import timezone

from .models import LitigeFournisseur, PurchaseOrder, PurchaseOrderLine

STATUTS_ENGAGES = (PurchaseOrder.Status.CONFIRMEE, PurchaseOrder.Status.PARTIELLE, PurchaseOrder.Status.CLOTUREE)


def _livraison(bc):
    """(complète, date de dernière réception) d'un bon de commande."""
    lignes = list(bc.lines.all())
    complete = bool(lignes) and all(ligne.received_qty >= ligne.quantity for ligne in lignes)
    derniere = bc.receipts.aggregate(d=Max("received_at"))["d"]
    return complete, derniere


def performance_fournisseurs():
    from qualite.models import ControleQualite

    today = timezone.localdate()
    commandes = (
        PurchaseOrder.objects.filter(status__in=STATUTS_ENGAGES, supplier__isnull=False)
        .select_related("supplier").prefetch_related("lines")
    )
    stats = defaultdict(lambda: {"commandes": 0, "echues": 0, "a_l_heure": 0, "retards": []})
    noms = {}
    for bc in commandes:
        s = stats[bc.supplier_id]
        noms[bc.supplier_id] = bc.supplier.name
        s["commandes"] += 1
        complete, derniere = _livraison(bc)
        if not bc.expected_date or (bc.expected_date > today and not complete):
            continue  # pas encore échue
        s["echues"] += 1
        if complete and derniere and bc.expected_date:
            retard = (derniere - bc.expected_date).days
            if retard > 0:
                s["retards"].append(retard)  # délai moyen = retard moyen des livraisons tardives
            else:
                s["a_l_heure"] += 1
    resultat = []
    for fid, s in stats.items():
        controles = ControleQualite.objects.filter(
            reception__purchase_order__supplier_id=fid, statut=ControleQualite.Statut.VALIDE
        )
        nb_controles = controles.count()
        conformes = controles.exclude(resultat=ControleQualite.Resultat.NON_CONFORME).count()
        litiges = LitigeFournisseur.objects.filter(purchase_order__supplier_id=fid).exclude(
            statut=LitigeFournisseur.Statut.RESOLU
        ).count()
        taux_service = round(s["a_l_heure"] / s["echues"], 3) if s["echues"] else None
        taux_conformite = round(conformes / nb_controles, 3) if nb_controles else None
        note = None
        if taux_service is not None:
            note = round(
                50 * taux_service
                + 30 * (1 if taux_conformite is None else taux_conformite)
                + 20 * max(0.0, 1 - 0.25 * litiges)
            )
        resultat.append({
            "fournisseur_id": fid,
            "fournisseur": noms[fid],
            "commandes": s["commandes"],
            "taux_service": taux_service,
            "retard_moyen_jours": round(sum(s["retards"]) / len(s["retards"]), 1) if s["retards"] else None,
            "taux_conformite": taux_conformite,
            "litiges_ouverts": litiges,
            "note": note,
        })
    return sorted(resultat, key=lambda x: (x["note"] is None, -(x["note"] or 0), x["fournisseur"]))


def reporting_achats(voir_montants):
    lignes = PurchaseOrderLine.objects.filter(purchase_order__status__in=STATUTS_ENGAGES)
    prix = []
    for row in (
        lignes.filter(article__isnull=False)
        .values("article__code", "article__label")
        .annotate(quantite=Sum("quantity"), montant=Sum("price_total"))
        .order_by("article__code")
    ):
        moyen = (row["montant"] / row["quantite"]) if row["quantite"] else Decimal("0")
        prix.append({
            "article": row["article__code"],
            "libelle": row["article__label"],
            "quantite": f"{row['quantite']:.2f}",
            "prix_moyen": f"{moyen:.2f}" if voir_montants else None,
        })
    engagements = []
    for row in (
        lignes.values("purchase_order__analytic__code", "purchase_order__analytic__label")
        .annotate(engage=Sum((F("quantity") - F("invoiced_qty")) * F("unit_price")))
        .order_by("purchase_order__analytic__code")
    ):
        engagements.append({
            "axe": row["purchase_order__analytic__code"] or "—",
            "libelle": row["purchase_order__analytic__label"] or "Non imputé",
            "engage": f"{row['engage'] or 0:.2f}" if voir_montants else None,
        })
    return {"prix_moyens": prix, "engagements": engagements, "fournisseurs": performance_fournisseurs()}
