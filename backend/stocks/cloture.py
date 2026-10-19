"""Clôture M5 (CDC M5 §7.11) : valorisation mensuelle figée → M11, inventaires tournants planifiés.

Valorisation : instantané des quants (CUMP) d'un dépôt à la fin du mois + consommations du mois ventilées par compte
analytique (affaire de l'OF). Elle est figée une seule fois, refusée si des mouvements postérieurs à la période existent
(le stock courant ne représenterait plus la fin de période) et publiée à M11 par l'outbox.
Inventaire tournant : chaque passage prépare une tranche d'articles du dépôt (rotation par code), à compter puis à
régulariser par la clôture de l'inventaire (mouvements d'écart).
"""

import calendar
import re
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from outbox.models import publish

from .models import Depot, Inventaire, InventaireLigne, MouvementStock, PlanInventaireTournant, StockQuant, ValorisationMensuelle
from .services import COMPTES_STOCK


def _fin_de_periode(periode):
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", periode or ""):
        raise ValueError("Période invalide : format AAAA-MM attendu.")
    annee, mois = int(periode[:4]), int(periode[5:])
    return date(annee, mois, calendar.monthrange(annee, mois)[1])


@transaction.atomic
def figer_valorisation_mensuelle(periode, user=None):
    """Fige la valorisation de tous les dépôts actifs pour `periode` (AAAA-MM) et la publie à M11."""
    fin = _fin_de_periode(periode)
    if fin.replace(day=1) > timezone.localdate():
        raise ValueError("La période n'est pas encore commencée.")
    if MouvementStock.objects.filter(executed=True, date__gt=fin).exists():
        raise ValueError(
            f"Des mouvements postérieurs au {fin} existent : le stock courant ne représente plus la fin de {periode}."
        )
    debut = fin.replace(day=1)
    resultat = []
    for depot in Depot.objects.filter(is_active=True).order_by("code"):
        if ValorisationMensuelle.objects.filter(periode=periode, depot=depot).exists():
            raise ValueError(f"La valorisation {periode} du dépôt {depot.code} est déjà figée.")
        quants = StockQuant.objects.filter(depot=depot).aggregate(q=Sum("quantity"), v=Sum("stock_value"))
        conso = (
            MouvementStock.objects.filter(
                executed=True, type_mouvement=MouvementStock.Type.CONSOMMATION,
                source=depot, date__gte=debut, date__lte=fin,
            )
            .values("analytic__code", "analytic__label")
            .annotate(valeur=Sum(F("quantite") * F("cout_unitaire")))
            .order_by("analytic__code")
        )
        ventilation = [
            {"axe": r["analytic__code"] or "—", "libelle": r["analytic__label"] or "Non imputé",
             "valeur": f"{(r['valeur'] or Decimal('0')):.2f}"}
            for r in conso
        ]
        total = sum((Decimal(v["valeur"]) for v in ventilation), Decimal("0"))
        par_compte = {}
        for q in StockQuant.objects.filter(depot=depot).select_related("article"):
            compte = COMPTES_STOCK.get(q.article.article_type, COMPTES_STOCK["consommable"])[0]
            par_compte[compte] = par_compte.get(compte, Decimal("0")) + q.stock_value
        val = ValorisationMensuelle.objects.create(
            periode=periode, depot=depot, quantite=quants["q"] or 0, valeur_stock=quants["v"] or 0,
            consommation=total, ventilation=ventilation, created_by=user,
            valeur_par_compte={k: f"{v:.2f}" for k, v in par_compte.items()},
        )
        comptabiliser_variation(val, fin, user)
        publish("stocks.valorisation.figee", {
            "periode": periode, "depot": depot.code, "valeur_stock": str(val.valeur_stock),
            "consommation": str(val.consommation), "ventilation": ventilation,
        })
        resultat.append(val)
    return resultat


@transaction.atomic
def generer_inventaire_tournant(plan, today=None):
    """Prépare l'inventaire tournant du passage : prochaine tranche d'articles en stock, lignes à compter."""
    plan = PlanInventaireTournant.objects.select_for_update().get(pk=plan.pk)
    today = today or timezone.localdate()
    articles = list(
        StockQuant.objects.filter(depot=plan.depot, quantity__gt=0).values_list("article_id", flat=True).distinct()
    )
    if not articles:
        plan.prochaine_date = today + timedelta(days=plan.periodicite_jours)
        plan.save(update_fields=["prochaine_date", "updated_at"])
        return None
    from referentiels.models import Article

    articles = list(Article.objects.filter(pk__in=articles).order_by("code").values_list("pk", flat=True))
    n = min(plan.articles_par_passage, len(articles))
    debut = plan.curseur % len(articles)
    tranche = [articles[(debut + i) % len(articles)] for i in range(n)]
    inv = Inventaire.objects.create(
        depot=plan.depot, date=today, type=Inventaire.Type.TOURNANT, plan=plan,
        statut=Inventaire.Statut.EN_COURS, responsable=plan.responsable,
        note=f"Passage tournant {plan.code} ({n} article(s)).",
    )
    for quant in StockQuant.objects.filter(depot=plan.depot, article_id__in=tranche, quantity__gt=0):
        InventaireLigne.objects.create(
            inventaire=inv, article_id=quant.article_id, lot=quant.lot,
            quantite_systeme=quant.quantity, quantite_reelle=quant.quantity, comptee=False,
        )
    plan.curseur = (debut + n) % len(articles)
    plan.prochaine_date = today + timedelta(days=plan.periodicite_jours)
    plan.save(update_fields=["curseur", "prochaine_date", "updated_at"])
    return inv


def planifier_inventaires_tournants(today=None):
    """Génère les inventaires des plans échus (tâche planifiée quotidienne)."""
    today = today or timezone.localdate()
    crees = []
    for plan in PlanInventaireTournant.objects.filter(actif=True, prochaine_date__lte=today):
        inv = generer_inventaire_tournant(plan, today)
        if inv:
            crees.append(inv)
    return crees


def comptabiliser_variation(val, fin, user=None):
    """Variation de stock du mois (SYSCOHADA, classes 3 / 603) passée au journal STK au figé de la valorisation :
    écart entre la valeur figée et celle du mois précédent, par compte de stock. Non bloquant : sans journal,
    période ou compte, le motif est conservé sur la valorisation et le figé reste valable pour M11."""
    from django.core.exceptions import ValidationError

    from accounting_kernel.models import AccountMove, AccountMoveLine, Journal
    from accounting_kernel.services import period_for_date, post_move
    from referentiels.models import Account

    precedente = (
        ValorisationMensuelle.objects.filter(depot=val.depot, periode__lt=val.periode).exclude(pk=val.pk).order_by("-periode").first()
    )
    avant = {k: Decimal(v) for k, v in (precedente.valeur_par_compte if precedente else {}).items()}
    apres = {k: Decimal(v) for k, v in val.valeur_par_compte.items()}
    variations = {c: apres.get(c, Decimal("0")) - avant.get(c, Decimal("0")) for c in set(avant) | set(apres)}
    variations = {c: d for c, d in variations.items() if d}
    if not variations:
        val.motif_ecriture = "Aucune variation de stock sur la période."
        val.save(update_fields=["motif_ecriture"])
        return None
    variation_de = {stock: var for stock, var in COMPTES_STOCK.values()}
    try:
        with transaction.atomic():  # savepoint : jamais d'écriture brouillon partielle
            journal = Journal.objects.get(code="STK")
            move = AccountMove.objects.create(
                journal=journal, period=period_for_date(fin), date=fin, reference=f"VAL-{val.periode}-{val.depot.code}",
                label=f"Variation de stock {val.periode} — {val.depot.code}", source="M5", source_ref=str(val.pk),
                status=AccountMove.Status.DRAFT,
            )
            ordre = 1
            for compte_stock, delta in sorted(variations.items()):
                stock, variation = Account.objects.get(code=compte_stock), Account.objects.get(code=variation_de[compte_stock])
                montant = abs(delta)
                # Hausse du stock : Dr 3x / Cr 603x ; baisse : Dr 603x / Cr 3x.
                debit, credit = (stock, variation) if delta > 0 else (variation, stock)
                AccountMoveLine.objects.create(move=move, account=debit, label=move.label, debit=montant, credit=0, order=ordre)
                AccountMoveLine.objects.create(move=move, account=credit, label=move.label, debit=0, credit=montant, order=ordre + 1)
                ordre += 2
            val.move = post_move(move, user=user)
        val.motif_ecriture = ""
    except (Journal.DoesNotExist, Account.DoesNotExist, ValidationError) as exc:
        val.motif_ecriture = f"Écriture non passée : {exc}"[:255]
    val.save(update_fields=["move", "motif_ecriture"])
    return val.move
