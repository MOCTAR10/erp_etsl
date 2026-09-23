"""Droits métier M11 — Contrôle de gestion (RF-ERP-A0…A4).

Écriture : cercle financier (budgets, révisions, clôtures) — Admin / PDG / DGA /
Secrétariat Général (visa des dépenses) / Finance / Comptable / Direction.
Montants masqués hors rôles autorisés (pattern RF-59). Lecture : tous
utilisateurs authentifiés. Les marges et les écarts sont agréés depuis les
écritures comptabilisées du noyau `accounting_kernel` ; le coût GLOBAL RENTAL
(compte 618) est isolé (RF-ERP-A4).
"""

from decimal import Decimal

from django.db.models import Q, Sum
from rest_framework.permissions import BasePermission

from users.models import User

GESTION_WRITE_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.SECRETAIRE_GENERAL,
    User.Role.FINANCE,
    User.Role.COMPTABLE,
    User.Role.DIRECTION,
)

GESTION_AMOUNT_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.SECRETAIRE_GENERAL,
    User.Role.FINANCE,
    User.Role.COMPTABLE,
    User.Role.DIRECTION,
)

ZERO = Decimal("0")


def is_admin_or_staff(user):
    return user.is_authenticated and (
        user.is_staff or user.is_superuser or user.role == User.Role.ADMIN
    )


def can_manage_gestion(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in GESTION_WRITE_ROLES


def can_see_amount(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in GESTION_AMOUNT_ROLES


class CanManageGestion(BasePermission):
    """Lecture authentifiée ; écriture réservée au cercle financier."""

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return bool(getattr(request, "user", None) and request.user.is_authenticated)
        return can_manage_gestion(getattr(request, "user", None))


class CanApproveBudget(BasePermission):
    """Approbation des budgets / révisions / clôtures : cercle montants."""

    message = "Rôle non autorisé à approuver un budget ou une clôture."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return is_admin_or_staff(user) or user.role in GESTION_AMOUNT_ROLES


def _posted_lines_qs(fiscal_year):
    """Lignes d'écritures comptabilisées (POSTED, non extournées) d'un exercice."""
    from accounting_kernel.models import AccountMove, AccountMoveLine

    posted_ids = AccountMove.objects.filter(
        period__fiscal_year_id=fiscal_year, status=AccountMove.Status.POSTED
    ).values_list("id", flat=True)
    return AccountMoveLine.objects.filter(
        move_id__in=posted_ids
    ).select_related("account")


def compute_marges(fiscal_year, axis=None, analytic=None, sens_gr_inclus=("produit", "618")):
    """Marges réelles par axe analytique (RF-ERP-A2), coût GR isolé (A4).

    Produits = crédits des comptes de produits (classe 7 : INCOME).
    Charges = débits des comptes de charges (classe 6 : EXPENSE) **hors** 618
    (refacturations intra-groupe isolées, A4). Le coût GLOBAL RENTAL (compte
    618) est agrégé séparément. `axis` / `analytic` filtrent l'axe de lecture.
    Retour : liste de dict `{analytic, code_axe, produits, charges, marge,
    taux_marge}` + totaux.
    """
    from accounting_kernel.models import AccountMoveLine
    from referentiels.models import Account, AnalyticAccount

    lines = _posted_lines_qs(fiscal_year)

    accounts = {
        (acc.code, acc.account_type) for acc in Account.objects.filter(
            account_class__in=(6, 7)
        )
    }
    produits_accounts = {
        code for code, atype in accounts if atype == Account.AccountType.INCOME
    }
    charges_accounts = {
        code for code, atype in accounts if atype == Account.AccountType.EXPENSE
    }
    qs = lines.filter(account__code__in=produits_accounts | charges_accounts)
    if axis:
        qs = qs.filter(analytic_account__axis_id=axis)
    if analytic:
        qs = qs.filter(analytic_account_id=analytic)

    gr_lines = qs.filter(account__code="618000")
    cout_gr = {
        "debit": gr_lines.aggregate(t=Sum("debit"))["t"] or ZERO,
        "credit": gr_lines.aggregate(t=Sum("credit"))["t"] or ZERO,
    }

    rows = []
    by_analytic = {}
    for line in qs.exclude(account__code="618000"):
        key = line.analytic_account_id
        row = by_analytic.setdefault(
            key,
            {
                "analytic": key,
                "code_axe": "",
                "libelle": "",
                "produits": ZERO,
                "charges": ZERO,
            },
        )
        if line.account_id and line.account.code in produits_accounts:
            row["produits"] += line.credit
        if line.account_id and line.account.code in charges_accounts:
            row["charges"] += line.debit

    analytics = {
        a.id: a
        for a in AnalyticAccount.objects.filter(
            id__in=list(by_analytic.keys()) or [0]
        ).select_related("axis")
    }
    for key, row in by_analytic.items():
        anal = analytics.get(key)
        if anal:
            row["code_axe"] = anal.axis.code if anal.axis else ""
            row["libelle"] = anal.label
        row["marge"] = (row["produits"] - row["charges"]).quantize(Decimal("0.01"))
        row["taux_marge"] = (
            (row["marge"] / row["produits"]).quantize(Decimal("0.001"))
            if row["produits"]
            else None
        )
        rows.append(row)
    rows.sort(key=lambda r: r.get("libelle") or "")

    total_produits = sum((r["produits"] for r in rows), ZERO)
    total_charges = sum((r["charges"] for r in rows), ZERO)
    marge = total_produits - total_charges
    # A4 : coût GR isolé (compte 618) — marge globale hors refacturations.
    marge_hors_gr = marge - cout_gr["debit"]
    return {
        "rows": rows,
        "totals": {
            "produits": total_produits,
            "charges": total_charges,
            "marge": marge,
            "marge_hors_gr": marge_hors_gr,
            "cout_gr": cout_gr["debit"],
        },
    }


def compute_variance(budget, fiscal_year=None):
    """Écart budget / réalisé par période (RF-ERP-A2) + sous-activité.

    Réalisé d'une période = lignes comptabilisées (POSTED) de la classe
    correspondante (produits si budget produits, charges hors 618 si budget
    de charges) filtrées sur l'axe / la valeur analytique du budget. Retour :
    `{lignes: [{period, montant, realise, ecart, taux}], totals}`.
    """
    from accounting_kernel.models import AccountMove, AccountMoveLine
    from referentiels.models import Account

    year = fiscal_year or budget.fiscal_year_id
    move_ids = AccountMove.objects.filter(
        period__fiscal_year_id=year, status=AccountMove.Status.POSTED
    ).values_list("id", flat=True)
    qs = AccountMoveLine.objects.filter(move_id__in=move_ids)
    if budget.axis_id:
        qs = qs.filter(analytic_account__axis_id=budget.axis_id)
    if budget.analytic_id:
        qs = qs.filter(analytic_account_id=budget.analytic_id)

    if budget.type_budget == budget.TypeBudget.PRODUIT:
        account_q = Q(account__account_type=Account.AccountType.INCOME)
        sign_field = "credit"
    else:
        account_q = Q(account__account_type=Account.AccountType.EXPENSE) & ~Q(
            account__code="618000"
        )
        sign_field = "debit"

    realised_by_period = {}
    for line in qs.filter(account_q):
        period_id = line.move.period_id
        realised_by_period[period_id] = (
            realised_by_period.get(period_id, ZERO) + getattr(line, sign_field)
        )

    rows = []
    total_budget = ZERO
    total_realise = ZERO
    for ligne in budget.lignes.select_related("period").order_by("period__number"):
        realise = realised_by_period.get(ligne.period_id, ZERO)
        ecart = ligne.montant - realise
        rows.append(
            {
                "period": ligne.period_id,
                "period_number": ligne.period.number,
                "period_label": str(ligne.period),
                "montant": ligne.montant,
                "realise": realise,
                "ecart": ecart,
                "taux": (realise / ligne.montant).quantize(Decimal("0.001"))
                if ligne.montant
                else None,
            }
        )
        total_budget += ligne.montant
        total_realise += realise

    taux_global = (total_realise / total_budget).quantize(Decimal("0.001")) if total_budget else None
    return {
        "lignes": rows,
        "totals": {
            "montant": total_budget,
            "realise": total_realise,
            "ecart": total_budget - total_realise,
            "taux": taux_global,
            # Sous-activité : budget non consommé (taux < 100 %).
            "sous_activite": (taux_global is not None and taux_global < 1),
        },
    }


def compute_clotures_stats(fiscal_year=None):
    """Statistiques de clôtures de gestion (RF-ERP-A3) pour un exercice."""
    from accounting_kernel.models import FiscalYear, Period

    if fiscal_year is None:
        fy = FiscalYear.objects.order_by("-year").first()
        fiscal_year = fy.pk if fy else None
    periods = list(Period.objects.filter(fiscal_year_id=fiscal_year).order_by("number"))
    from .models import ClotureGestion

    closed = {c.period_id: c for c in
              ClotureGestion.objects.filter(period__fiscal_year_id=fiscal_year)}
    n_conformes = 0
    n_realisees = 0
    n_en_attente = 0
    max_jours = None
    for period in periods:
        c = closed.get(period.id)
        if c and c.statut == c.Statut.REALISEE:
            n_realisees += 1
            jc = c.jours_ecoulement
            if jc is not None:
                if max_jours is None or jc > max_jours:
                    max_jours = jc
            if c.conforme_j4:
                n_conformes += 1
        else:
            n_en_attente += 1
    return {
        "periodes": len(periods),
        "realisees": n_realisees,
        "conformes_j4": n_conformes,
        "en_attente": n_en_attente,
        "max_jours_ecoulement": max_jours,
    }