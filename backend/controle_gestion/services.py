"""Droits métier M11 — Contrôle de gestion (RF-ERP-A0…A4).

Écriture : cercle financier (budgets, révisions, clôtures) — Admin / PDG / DGA /
Secrétariat Général (visa des dépenses) / Finance / Comptable / Direction.
Montants masqués hors rôles autorisés (pattern RF-59). Lecture : tous
utilisateurs authentifiés. Les marges et les écarts sont agréés depuis les
écritures comptabilisées du noyau `accounting_kernel` ; le coût GLOBAL RENTAL
(compte 618) est isolé (RF-ERP-A4).
"""

from decimal import Decimal

from django.db.models import Case, DecimalField, F, Q, Sum, Value, When
from django.utils import timezone
from rest_framework.permissions import BasePermission

from users.models import User
from users.rbac import can_read_app

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
            return can_read_app(getattr(request, "user", None), "controle_gestion")
        return can_manage_gestion(getattr(request, "user", None))


class CanApproveBudget(BasePermission):
    """Approbation des budgets / révisions / clôtures : cercle montants."""

    message = "Rôle non autorisé à approuver un budget ou une clôture."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return is_admin_or_staff(user) or user.role in GESTION_AMOUNT_ROLES


def _net(cond, plus, minus):
    """Expression SQL : (plus - minus) si `cond`, sinon 0 — somme en NET d'un côté du grand livre."""
    return Case(
        When(cond, then=F(plus) - F(minus)),
        default=Value(ZERO),
        output_field=DecimalField(max_digits=18, decimal_places=2),
    )


def _posted_lines_qs(fiscal_year):
    """Lignes d'écritures comptabilisées (POSTED, non extournées) d'un exercice."""
    from accounting_kernel.models import AccountMove, AccountMoveLine

    # POSTED **et** REVERSED : une extourne = écriture d'origine + contre-écriture, qui
    # s'annulent en net. Exclure l'originale ne retirerait que la moitié de la paire.
    posted_ids = AccountMove.objects.filter(
        period__fiscal_year_id=fiscal_year,
        status__in=(AccountMove.Status.POSTED, AccountMove.Status.REVERSED),
    ).values_list("id", flat=True)
    return AccountMoveLine.objects.filter(move_id__in=posted_ids)


def compute_marges(fiscal_year, axis=None, analytic=None, sens_gr_inclus=("produit", "618")):
    """Marges réelles par axe analytique (RF-ERP-A2), coût GR isolé (A4).

    Produits = crédits des comptes de produits (classe 7 : INCOME).
    Charges = débits des comptes de charges (classe 6 : EXPENSE) **hors** 618
    (refacturations intra-groupe isolées, A4). Le coût GLOBAL RENTAL (compte
    618) est agrégé séparément. `axis` / `analytic` filtrent l'axe de lecture.
    Retour : liste de dict `{analytic, code_axe, produits, charges, marge,
    taux_marge}` + totaux.
    """
    from referentiels.models import Account, AnalyticAccount

    qs = _posted_lines_qs(fiscal_year).filter(account__account_class__in=(6, 7))
    if axis:
        qs = qs.filter(analytic_account__axis_id=axis)
    if analytic:
        qs = qs.filter(analytic_account_id=analytic)

    # NET : produits = crédit - débit (classe 7), charges = débit - crédit (classe 6),
    # de sorte que avoirs et extournes viennent en déduction au lieu d'être ignorés.
    is_income = Q(account__account_type=Account.AccountType.INCOME)
    is_gr = Q(account__code="618000")
    is_charge = Q(account__account_type=Account.AccountType.EXPENSE) & ~is_gr

    gr = qs.filter(is_gr).aggregate(t=Sum(F("debit") - F("credit")))["t"] or ZERO
    cout_gr = {"debit": gr, "credit": ZERO}

    grouped = (
        qs.exclude(is_gr)
        .values("analytic_account_id")
        .annotate(
            produits=Sum(_net(is_income, "credit", "debit")),
            charges=Sum(_net(is_charge, "debit", "credit")),
        )
    )
    analytics = {
        a.id: a
        for a in AnalyticAccount.objects.filter(
            id__in=[g["analytic_account_id"] for g in grouped if g["analytic_account_id"]]
        ).select_related("axis")
    }
    rows = []
    for g in grouped:
        key = g["analytic_account_id"]
        row = {
            "analytic": key,
            "code_axe": "",
            "libelle": "",
            "produits": g["produits"] or ZERO,
            "charges": g["charges"] or ZERO,
        }
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
    from referentiels.models import Account

    year = fiscal_year or budget.fiscal_year_id
    qs = _posted_lines_qs(year)
    if budget.axis_id:
        qs = qs.filter(analytic_account__axis_id=budget.axis_id)
    if budget.analytic_id:
        qs = qs.filter(analytic_account_id=budget.analytic_id)

    if budget.type_budget == budget.TypeBudget.PRODUIT:
        expr = _net(Q(account__account_type=Account.AccountType.INCOME), "credit", "debit")
    else:
        expr = _net(
            Q(account__account_type=Account.AccountType.EXPENSE) & ~Q(account__code="618000"),
            "debit",
            "credit",
        )
    realised_by_period = {
        r["move__period_id"]: r["total"] or ZERO
        for r in qs.values("move__period_id").annotate(total=Sum(expr))
    }

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


def detecter_ecarts(budgets=None, today=None):
    """Ouvre une analyse (échéance J+5) pour chaque période écoulée d'un budget approuvé dont le réalisé
    s'écarte de plus de 10 % du budget, et prévient le contrôle de gestion (lot 15, CDC M11 §4.4)."""
    from datetime import timedelta

    from accounting_kernel.models import Period
    from workflow.notifications import notify

    from .models import AnalyseEcart, Budget

    today = today or timezone.localdate()
    budgets = budgets if budgets is not None else Budget.objects.filter(statut=Budget.Statut.APPROUVE)
    destinataires = list(User.objects.filter(role__in=(User.Role.FINANCE, User.Role.DGA), is_active=True))
    crees = []
    for budget in budgets:
        deja = set(budget.analyses_ecart.values_list("period_id", flat=True))
        for ligne in compute_variance(budget)["lignes"]:
            if not ligne["montant"] or ligne["period"] in deja:
                continue
            if Period.objects.get(pk=ligne["period"]).end_date >= today:
                continue  # période non écoulée
            pct = ((ligne["realise"] - ligne["montant"]) * 100 / ligne["montant"]).quantize(Decimal("0.01"))
            if abs(pct) <= AnalyseEcart.SEUIL_PCT:
                continue
            analyse = AnalyseEcart.objects.create(
                budget=budget, period_id=ligne["period"], montant_budget=ligne["montant"],
                realise=ligne["realise"], ecart_pct=pct, detecte_le=today,
                echeance=today + timedelta(days=AnalyseEcart.DELAI_JOURS),
            )
            crees.append(analyse)
            for user in destinataires:
                notify(
                    user,
                    f"Écart budgétaire {pct:+} % : {budget.code} — {ligne['period_label']}",
                    f"Le budget « {budget.label} » ({budget.code}) s'écarte de {pct:+} % sur {ligne['period_label']}. "
                    f"Analyse obligatoire avant le {analyse.echeance:%d/%m/%Y} ({analyse.code}).",
                    kind="reminder",
                )
    return crees


# --------------------------------------------------------------------------------------------------
# Paramètres modifiables (valeur = donnée ETSL, défaut provisoire créé à la volée)
# --------------------------------------------------------------------------------------------------
PARAMETRES_DEFAUT = {
    "SOUS_ACTIVITE_SEUIL_90": ("Sous-activité maximale du centre 90 (au-delà : centre 91)", Decimal("5"), "%"),
    "SOUS_ACTIVITE_SEUIL_91": ("Sous-activité maximale du centre 91 (au-delà : centre 99)", Decimal("15"), "%"),
    "RGM_MIX_A": ("Doctrine d'imputation : part cible du Mix A", Decimal("55"), "%"),
    "RGM_MIX_B": ("Doctrine d'imputation : part cible du Mix B", Decimal("40"), "%"),
    "RGM_MIX_C": ("Doctrine d'imputation : part maximale du Mix C", Decimal("5"), "%"),
    "RGM_TOLERANCE_MIX": ("Doctrine d'imputation : écart toléré à la cible", Decimal("5"), "points"),
    "REPORTING_JOUR_J4": ("Reporting Direction : jour cible (J+n après la fin du mois)", Decimal("4"), "jours"),
    "REPORTING_JOUR_J6": ("Reporting Direction : jour limite (J+n après la fin du mois)", Decimal("6"), "jours"),
}


def get_param_gestion(code):
    """Valeur du paramètre `code` ; crée le défaut provisoire si absent."""
    from .models import ParametreGestion

    label, valeur, unite = PARAMETRES_DEFAUT[code]
    obj, _ = ParametreGestion.objects.get_or_create(
        code=code, defaults={"label": label, "valeur": valeur, "unite": unite}
    )
    return obj.valeur


def parametres_gestion_provisoires(codes):
    """Vrai si l'un des paramètres `codes` n'est pas encore confirmé par ETSL."""
    from .models import ParametreGestion

    for c in codes:
        get_param_gestion(c)
    return ParametreGestion.objects.filter(code__in=codes).exclude(statut_valeur="confirme").exists()


# --------------------------------------------------------------------------------------------------
# Sous-activité : centres 90 / 91 / 99 (CDC M11 §4.4)
# --------------------------------------------------------------------------------------------------
CODES_SOUS_ACTIVITE = ("SOUS_ACTIVITE_SEUIL_90", "SOUS_ACTIVITE_SEUIL_91")
CODES_DOCTRINE = ("RGM_MIX_A", "RGM_MIX_B", "RGM_MIX_C", "RGM_TOLERANCE_MIX")


def classer_centre(taux_pct):
    """Centre 90 (≤ seuil bas), 91 (jusqu'au seuil haut) ou 99 (au-delà) selon le taux de sous-activité en %."""
    if taux_pct <= get_param_gestion("SOUS_ACTIVITE_SEUIL_90"):
        return "90"
    if taux_pct <= get_param_gestion("SOUS_ACTIVITE_SEUIL_91"):
        return "91"
    return "99"


def compute_sous_activite(fiscal_year, today=None):
    """Taux de sous-activité par budget approuvé/clôturé : part du budget non consommée sur les périodes écoulées."""
    from accounting_kernel.models import Period

    from .models import Budget

    today = today or timezone.localdate()
    ecoulees = set(
        Period.objects.filter(fiscal_year_id=fiscal_year, end_date__lt=today).values_list("id", flat=True)
    )
    budgets = Budget.objects.filter(
        fiscal_year_id=fiscal_year, statut__in=(Budget.Statut.APPROUVE, Budget.Statut.CLOTURE)
    ).select_related("analytic")
    rows = []
    for budget in budgets:
        lignes = [x for x in compute_variance(budget)["lignes"] if x["period"] in ecoulees]
        prevu = sum((x["montant"] for x in lignes), ZERO)
        realise = sum((x["realise"] for x in lignes), ZERO)
        if not prevu:
            continue
        taux = max(ZERO, (prevu - realise) * 100 / prevu).quantize(Decimal("0.01"))
        rows.append({
            "budget": budget.pk, "code": budget.code, "label": budget.label,
            "analytic_label": budget.analytic.label if budget.analytic_id else "",
            "budget_ecoule": prevu, "realise": realise, "taux_sous_activite": taux,
            "centre": classer_centre(taux),
        })
    rows.sort(key=lambda r: (-r["taux_sous_activite"], r["code"]))
    return {"rows": rows, "provisoire": parametres_gestion_provisoires(CODES_SOUS_ACTIVITE)}


def alerter_sous_activite(today=None):
    """Alerte (une seule fois par budget) lorsqu'un budget entre au centre 99 ; prévient Finance / DGA."""
    from accounting_kernel.models import FiscalYear
    from workflow.notifications import notify

    from .models import AlerteSousActivite

    today = today or timezone.localdate()
    destinataires = list(User.objects.filter(role__in=(User.Role.FINANCE, User.Role.DGA), is_active=True))
    crees = []
    for fy in FiscalYear.objects.all():
        for r in compute_sous_activite(fy.pk, today)["rows"]:
            if r["centre"] != "99":
                continue
            alerte, cree = AlerteSousActivite.objects.get_or_create(
                budget_id=r["budget"], centre="99",
                defaults={"taux": r["taux_sous_activite"], "detecte_le": today},
            )
            if not cree:
                continue
            crees.append(alerte)
            for user in destinataires:
                notify(
                    user, f"Sous-activité {r['taux_sous_activite']} % : {r['code']} (centre 99)",
                    f"Le budget « {r['label']} » ({r['code']}) est sous-consommé de {r['taux_sous_activite']} % "
                    f"sur les périodes écoulées : classement au centre 99.",
                    kind="reminder",
                )
    return crees


# --------------------------------------------------------------------------------------------------
# Doctrine d'imputation Mix A / B / C (valeurs RGM_* = paramètres provisoires)
# --------------------------------------------------------------------------------------------------
def compute_doctrine(fiscal_year):
    """Répartition réelle des budgets par classe de Mix (A/B/C) face à la cible paramétrée.

    Interprétation provisoire : la part d'une classe = son budget / total des budgets classés. A et B sont
    conformes à ±tolérance de la cible ; C l'est tant qu'il ne dépasse pas son plafond.
    """
    from .models import Budget

    cible = {k: get_param_gestion(f"RGM_MIX_{k}") for k in "ABC"}
    tol = get_param_gestion("RGM_TOLERANCE_MIX")
    totaux = {k: ZERO for k in "ABC"}
    non_classes = 0
    for b in Budget.objects.filter(fiscal_year_id=fiscal_year).exclude(statut=Budget.Statut.BROUILLON):
        if b.classe_mix in totaux:
            totaux[b.classe_mix] += b.montant
        else:
            non_classes += 1
    total = sum(totaux.values(), ZERO)
    lignes = []
    for k in "ABC":
        part = (totaux[k] * 100 / total).quantize(Decimal("0.01")) if total else ZERO
        conforme = (part <= cible[k]) if k == "C" else (abs(part - cible[k]) <= tol)
        lignes.append({"classe": k, "montant": totaux[k], "part": part, "cible": cible[k],
                       "conforme": conforme if total else None})
    return {
        "lignes": lignes, "non_classes": non_classes,
        "cible_coherente": cible["A"] + cible["B"] + cible["C"] == 100,
        "provisoire": parametres_gestion_provisoires(CODES_DOCTRINE),
    }


# --------------------------------------------------------------------------------------------------
# Reporting Direction J+4 / J+6 (paramètres provisoires REPORTING_JOUR_J4 / J6)
# --------------------------------------------------------------------------------------------------
CODES_REPORTING = ("REPORTING_JOUR_J4", "REPORTING_JOUR_J6")
FENETRE_RELANCE_JOURS = 62  # on ne relance que les mois récents : les mois d'avant la mise en service sont ignorés


def suivre_reporting(today=None):
    """Crée la clôture de gestion manquante et relance (une fois) les mois dont la publication dépasse J+6."""
    from datetime import timedelta

    from accounting_kernel.models import Period
    from workflow.notifications import notify

    from .models import ClotureGestion

    today = today or timezone.localdate()
    j6 = timedelta(days=int(get_param_gestion("REPORTING_JOUR_J6")))
    destinataires = list(
        User.objects.filter(role__in=(User.Role.FINANCE, User.Role.DGA, User.Role.PDG), is_active=True)
    )
    relances = []
    periods = Period.objects.filter(
        end_date__lt=today - j6, end_date__gte=today - timedelta(days=FENETRE_RELANCE_JOURS)
    )
    for period in periods:
        cloture, _ = ClotureGestion.objects.get_or_create(period=period)
        if cloture.date_publication or cloture.alerte_j6_le:
            continue
        cloture.alerte_j6_le = today
        cloture.save(update_fields=["alerte_j6_le", "updated_at"])
        relances.append(cloture)
        for user in destinataires:
            notify(
                user, f"Reporting Direction en retard : {period}",
                f"Le reporting de gestion de {period} n'est pas publié à J+{int(j6.days)} "
                f"({cloture.echeance_j6:%d/%m/%Y}).",
                kind="escalation",
            )
    return relances


# --------------------------------------------------------------------------------------------------
# Marges brute / opérationnelle / nette et atterrissage (définitions provisoires, cf. fiche M11)
# --------------------------------------------------------------------------------------------------
def compute_niveaux_marge(fiscal_year):
    """Trois niveaux de marge réelle sur les écritures comptabilisées.

    brute = produits − charges directes (axes projet / chantier) ; opérationnelle = brute − charges de structure
    (centres de coût, sites, charges sans axe) ; nette = opérationnelle − coût GLOBAL RENTAL (618 isolé, A4).
    """
    from referentiels.models import Account, AnalyticAxis

    qs = _posted_lines_qs(fiscal_year).filter(account__account_class__in=(6, 7))
    is_gr = Q(account__code="618000")
    directs = Q(analytic_account__axis__axis_type__in=(AnalyticAxis.AxisType.PROJET, AnalyticAxis.AxisType.CHANTIER))
    charge = Q(account__account_type=Account.AccountType.EXPENSE) & ~is_gr
    agg = qs.aggregate(
        produits=Sum(_net(Q(account__account_type=Account.AccountType.INCOME), "credit", "debit")),
        directes=Sum(_net(charge & directs, "debit", "credit")),
        structure=Sum(_net(charge & ~directs, "debit", "credit")),
        cout_gr=Sum(_net(is_gr, "debit", "credit")),
    )
    produits, directes, structure, cout_gr = (agg[k] or ZERO for k in ("produits", "directes", "structure", "cout_gr"))
    brute = produits - directes
    operationnelle = brute - structure
    nette = operationnelle - cout_gr

    def taux(m):
        return (m * 100 / produits).quantize(Decimal("0.01")) if produits else None

    return {
        "produits": produits, "charges_directes": directes, "charges_structure": structure, "cout_gr": cout_gr,
        "marge_brute": brute, "marge_operationnelle": operationnelle, "marge_nette": nette,
        "taux_brute": taux(brute), "taux_operationnelle": taux(operationnelle), "taux_nette": taux(nette),
    }


def compute_atterrissage(fiscal_year, today=None):
    """Atterrissage de fin d'exercice par budget : réalisé des périodes écoulées + budget des périodes à venir.

    La marge à terminaison = atterrissage des budgets de produits − atterrissage des budgets de charges.
    """
    from accounting_kernel.models import Period

    from .models import Budget

    today = today or timezone.localdate()
    ecoulees = set(
        Period.objects.filter(fiscal_year_id=fiscal_year, end_date__lt=today).values_list("id", flat=True)
    )
    rows = []
    totaux = {"produit": ZERO, "charge": ZERO}
    budgets = Budget.objects.filter(
        fiscal_year_id=fiscal_year, statut__in=(Budget.Statut.APPROUVE, Budget.Statut.CLOTURE)
    )
    for budget in budgets:
        lignes = compute_variance(budget)["lignes"]
        realise = sum((x["realise"] for x in lignes if x["period"] in ecoulees), ZERO)
        a_venir = sum((x["montant"] for x in lignes if x["period"] not in ecoulees), ZERO)
        total_budget = sum((x["montant"] for x in lignes), ZERO)
        atterrissage = realise + a_venir
        totaux[budget.type_budget] += atterrissage
        rows.append({
            "code": budget.code, "label": budget.label, "type_budget": budget.type_budget,
            "budget": budget.pk, "budget_annuel": total_budget, "realise": realise, "reste_a_venir": a_venir,
            "atterrissage": atterrissage, "ecart_objectif": atterrissage - total_budget,
        })
    return {"rows": rows, "marge_a_terminaison": totaux["produit"] - totaux["charge"], "totaux": totaux}
