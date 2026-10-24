"""Écarts M11 — Contrôle de gestion (2026-10-21).

Révision R1-R4 par ligne mensuelle, imputation des charges de structure (clé paramétrable), tables RGM_*,
axes activité / profil, pipe pondéré → budget de produits, plan d'action de sous-activité, reporting par horizon
(PDF archivé GED), KPI KP-M11-01 à 12, PV de validation budgétaire et de revue de performance (P-M11.10) archivés
10 ans, validation de la marge d'affaire, coût de main-d'œuvre par affaire (lecture M9), provision 408.

Toutes les valeurs attendues d'ETSL sont des `ParametreGestion` provisoires (modifiables à l'écran).
"""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from .services import KPI_NOMS, ZERO, _net, _posted_lines_qs, get_param_gestion, parametres_gestion_provisoires
from config.i18n import en_francais, tr

CENT = Decimal("0.01")

TABLES_RGM = ("RGM_PARAM_STRUCTURE", "RGM_TAUX_STRUCTURE", "RGM_POND_PROSPECT")
CODES_STRUCTURE = ("STRUCT_CLE_REPARTITION", "STRUCT_SANS_AXE", "MARGE_NIVEAU_GR")
CODES_POND = ("POND_SIGNE", "POND_EN_COURS", "POND_PROSPECT")
PROFILS = ("marche_travaux", "maintenance", "global_rental", "autre")


def _pct(num, den):
    return (num * 100 / den).quantize(CENT) if den else None


def _s(v):
    return None if v is None else f"{v:.2f}"


# --------------------------------------------------------------------------------------------------
# Axes activité / profil (référentiel analytique multi-axes)
# --------------------------------------------------------------------------------------------------
def profil_affaire(affaire):
    """Profil contractuel d'une affaire : GLOBAL RENTAL (3e profil, provisoire) > contrat CLM > « autre »."""
    if affaire.is_global_rental:
        return "global_rental"
    contrat = next(iter(affaire.contracts.all()), None)
    return contrat.profile if contrat else "autre"


def initialiser_axes():
    """Crée (idempotent) les axes ACTIVITÉ (types d'affaire) et PROFIL (profils contractuels + GLOBAL RENTAL)."""
    from commercial.models import Affaire, Contract
    from referentiels.models import AnalyticAccount, AnalyticAxis

    from .models import AxeAnalytiqueM11

    crees = []
    valeurs = {
        ("AX-ACT", "Activité", "activite"): list(Affaire.AffaireType.choices),
        ("AX-PROF", "Profil contractuel", "profil"): list(Contract.Profile.choices)
        + [("global_rental", "GLOBAL RENTAL"), ("autre", "Autre (sans contrat)")],
    }
    for (code, label, nature), items in valeurs.items():
        # Le référentiel ne connaît pas (encore) les types « activité » / « profil » : l'axe est rangé en « site »
        # (aucune écriture n'y est imputée) et sa nature M11 est portée par `AxeAnalytiqueM11`.
        axe, _ = AnalyticAxis.objects.get_or_create(
            code=code, defaults={"label": label, "axis_type": AnalyticAxis.AxisType.SITE}
        )
        AxeAnalytiqueM11.objects.get_or_create(axis=axe, defaults={"nature": nature})
        for vcode, vlabel in items:
            _, cree = AnalyticAccount.objects.get_or_create(axis=axe, code=vcode, defaults={"label": vlabel})
            if cree:
                crees.append(f"{code}:{vcode}")
    return crees


def analytiques_par_valeur(axis_type, code=None):
    """Comptes analytiques des affaires dont l'activité / le profil vaut `code` (toutes si None)."""
    from commercial.models import Affaire

    ids = []
    for a in Affaire.objects.filter(analytic__isnull=False).prefetch_related("contracts"):
        valeur = a.affaire_type if axis_type == "activite" else profil_affaire(a)
        if code is None or valeur == code:
            ids.append(a.analytic_id)
    return ids


# --------------------------------------------------------------------------------------------------
# Imputation des charges de structure (clé B : heures productives ou CA) — RGM_PARAM / RGM_TAUX_STRUCTURE
# --------------------------------------------------------------------------------------------------
def _heures_par_affaire(fy):
    from operations.models import PointageChantier

    rows = (
        PointageChantier.objects.filter(
            date__gte=fy.start_date, date__lte=fy.end_date, ordre__affaire__isnull=False,
            status__in=(PointageChantier.Status.VALIDE, PointageChantier.Status.TRANSFERE),
        )
        .values("ordre__affaire_id")
        .annotate(h=Sum("hours"))
    )
    return {r["ordre__affaire_id"]: r["h"] or ZERO for r in rows}


def imputer_structure(fiscal_year):
    """Répartit les charges de structure de l'exercice sur les affaires selon la clé paramétrée.

    Clé 1 = heures productives (pointages M3 validés), clé 2 = chiffre d'affaires comptabilisé. Chaque affaire porte
    sa quote-part, sa marge directe, sa marge après structure et son taux réel face au taux standard de son profil.
    """
    from accounting_kernel.models import FiscalYear
    from commercial.models import Affaire

    from .services import compute_marges, compute_niveaux_marge

    fy = FiscalYear.objects.get(pk=fiscal_year)
    structure = compute_niveaux_marge(fy.pk)["charges_structure"]
    cle = int(get_param_gestion("STRUCT_CLE_REPARTITION"))
    marges = {r["analytic"]: r for r in compute_marges(fy.pk)["rows"] if r["analytic"]}
    affaires = list(
        Affaire.objects.exclude(status=Affaire.Status.ARCHIVEE).filter(analytic__isnull=False)
        .select_related("client__partner").prefetch_related("contracts")
    )
    heures = _heures_par_affaire(fy) if cle == 1 else {}
    bases = {}
    for a in affaires:
        m = marges.get(a.analytic_id) or {}
        bases[a.pk] = heures.get(a.pk, ZERO) if cle == 1 else max(m.get("produits") or ZERO, ZERO)
    total = sum(bases.values(), ZERO)
    rows = []
    for a in affaires:
        m = marges.get(a.analytic_id) or {}
        produits, charges = m.get("produits") or ZERO, m.get("charges") or ZERO
        part = (bases[a.pk] / total) if total else ZERO
        impute = (structure * part).quantize(CENT)
        profil = profil_affaire(a)
        standard = get_param_gestion(f"TAUX_STRUCT_{profil.upper()}")
        reel = _pct(impute, produits)
        rows.append({
            "affaire": str(a.pk), "code": a.code, "titre": a.title, "profil": profil,
            "client": a.client.partner.name if a.client_id else "",
            "base": f"{bases[a.pk]:.2f}", "part_pct": f"{part * 100:.2f}",
            "produits": produits, "charges_directes": charges, "marge_directe": produits - charges,
            "structure_imputee": impute, "marge_apres_structure": produits - charges - impute,
            "taux_structure_reel": _s(reel), "taux_structure_standard": _s(standard),
            "ecart_standard": _s(reel - standard) if reel is not None else None,
        })
    rows.sort(key=lambda r: r["code"])
    return {
        "cle": cle, "cle_label": "Heures productives" if cle == 1 else "Chiffre d'affaires",
        "charges_structure": structure, "base_totale": f"{total:.2f}",
        "non_imputees": structure if not total else ZERO, "rows": rows,
        "provisoire": parametres_gestion_provisoires(
            CODES_STRUCTURE + tuple(f"TAUX_STRUCT_{p.upper()}" for p in PROFILS)
        ),
    }


# --------------------------------------------------------------------------------------------------
# Pipe pondéré (RGM_POND_PROSPECT) → proposition de budget de produits
# --------------------------------------------------------------------------------------------------
def _ponderations():
    return {"signe": get_param_gestion("POND_SIGNE"), "en_cours": get_param_gestion("POND_EN_COURS"),
            "prospect": get_param_gestion("POND_PROSPECT")}


def _opportunites_annee(fy):
    from commercial.models import Opportunity
    from commercial.services import PIPE_CATEGORIES, filtre_exercice

    etape_cat = {e: cat for cat, etapes in PIPE_CATEGORIES.items() for e in etapes}
    qs = Opportunity.objects.filter(is_active=True, stage__in=list(etape_cat)).filter(filtre_exercice(fy.year))
    return [(o, etape_cat[o.stage]) for o in qs]


def pipe_pondere_m11(fiscal_year):
    from accounting_kernel.models import FiscalYear

    fy = FiscalYear.objects.get(pk=fiscal_year)
    poids = _ponderations()
    cats = {c: {"categorie": c, "brut": ZERO, "ponderation": poids[c], "pondere": ZERO, "nb": 0} for c in poids}
    for o, cat in _opportunites_annee(fy):
        cats[cat]["brut"] += o.amount or ZERO
        cats[cat]["nb"] += 1
    for c in cats.values():
        c["pondere"] = (c["brut"] * c["ponderation"] / 100).quantize(CENT)
    total = sum((c["pondere"] for c in cats.values()), ZERO)
    return {"annee": fy.year, "categories": list(cats.values()), "total": total,
            "provisoire": parametres_gestion_provisoires(CODES_POND)}


@transaction.atomic
def proposer_budget_pipe(fiscal_year, user=None):
    """Crée un budget de produits BROUILLON = pipe pondéré, ventilé par mois de clôture prévue (sinon 1/12)."""
    from accounting_kernel.models import FiscalYear, Period

    from .models import Budget, BudgetLigne

    fy = FiscalYear.objects.get(pk=fiscal_year)
    periods = {p.start_date.month: p for p in Period.objects.filter(fiscal_year=fy).order_by("number")}
    if not periods:
        raise ValidationError("Exercice sans périodes comptables.")
    poids = _ponderations()
    par_mois = defaultdict(Decimal)
    for o, cat in _opportunites_annee(fy):
        montant = ((o.amount or ZERO) * poids[cat] / 100).quantize(CENT)
        if o.expected_close and o.expected_close.month in periods:
            par_mois[o.expected_close.month] += montant
        else:
            douzieme = (montant / len(periods)).quantize(CENT)
            for i, mois in enumerate(sorted(periods)):
                par_mois[mois] += douzieme if i < len(periods) - 1 else montant - douzieme * (len(periods) - 1)
    total = sum(par_mois.values(), ZERO)
    if not total:
        raise ValidationError("Pipe vide pour cet exercice : aucune opportunité active à pondérer.")
    budget = Budget.objects.create(
        label=f"Budget de produits {fy.year} — pipe pondéré", type_budget=Budget.TypeBudget.PRODUIT,
        fiscal_year=fy, montant=total, created_by=user if getattr(user, "is_authenticated", False) else None,
    )
    for mois, montant in sorted(par_mois.items()):
        BudgetLigne.objects.create(budget=budget, period=periods[mois], montant=montant)
    return budget


# --------------------------------------------------------------------------------------------------
# KPI KP-M11-01 à 12 (formules provisoires, cibles = paramètres KPI_CIBLES)
# --------------------------------------------------------------------------------------------------
# (numéro, sens, formule) ; nom et unité viennent de `services.KPI_NOMS` (mêmes libellés que les cibles).
_KPI_FORMULES = (
    ("01", "min", "Marge brute / produits"),
    ("02", "min", "Marge opérationnelle / produits"),
    ("03", "min", "Marge nette / produits"),
    ("04", "max", "Charges réalisées / budget des périodes écoulées"),
    ("05", "min", "Produits réalisés / budget des périodes écoulées"),
    ("06", "max", "Moyenne des taux de sous-activité des budgets"),
    ("07", "min", "Classes conformes / 3"),
    ("08", "max", "Plus long délai fin de mois → clôture"),
    ("09", "min", "Publications à J+4 / publications"),
    ("10", "min", "Analyses rendues à temps / analyses dues"),
    ("11", "max", "Coût GR / total des charges"),
    ("12", "min", "Pipe pondéré / budget de produits"),
)
KPI_DEFS = tuple((num, KPI_NOMS[num][0], KPI_NOMS[num][1], sens, formule) for num, sens, formule in _KPI_FORMULES)
KPI_CIBLES_DEFAUT = {"01": 25, "02": 12, "03": 8, "04": 100, "05": 95, "06": 5, "07": 100, "08": 4, "09": 100,
                     "10": 100, "11": 15, "12": 100}


def _execution_budgets(fy_id, today):
    from accounting_kernel.models import Period

    from .models import Budget
    from .services import compute_variance

    ecoulees = set(Period.objects.filter(fiscal_year_id=fy_id, end_date__lt=today).values_list("id", flat=True))
    tot = {"charge": [ZERO, ZERO], "produit": [ZERO, ZERO]}
    for b in Budget.objects.filter(fiscal_year_id=fy_id, statut__in=(Budget.Statut.APPROUVE, Budget.Statut.CLOTURE)):
        for x in compute_variance(b)["lignes"]:
            if x["period"] in ecoulees:
                tot[b.type_budget][0] += x["montant"]
                tot[b.type_budget][1] += x["realise"]
    return tot


def compute_kpis(fiscal_year, today=None):
    from .models import AnalyseEcart, Budget, ClotureGestion
    from .services import compute_clotures_stats, compute_doctrine, compute_niveaux_marge, compute_sous_activite

    today = today or timezone.localdate()
    niv = compute_niveaux_marge(fiscal_year)
    exe = _execution_budgets(fiscal_year, today)
    sa = [r["taux_sous_activite"] for r in compute_sous_activite(fiscal_year, today)["rows"]]
    doc = compute_doctrine(fiscal_year)
    conformes = [x["conforme"] for x in doc["lignes"] if x["conforme"] is not None]
    clo = compute_clotures_stats(fiscal_year)
    publiees = [c for c in ClotureGestion.objects.filter(period__fiscal_year_id=fiscal_year, date_publication__isnull=False)
                .select_related("period")]
    analyses = AnalyseEcart.objects.filter(period__fiscal_year_id=fiscal_year)
    rendues_a_temps = sum(1 for a in analyses if a.statut == "analysee" and a.analyse_le
                          and timezone.localdate(a.analyse_le) <= a.echeance)
    dues = sum(1 for a in analyses if a.statut == "analysee" or a.echeance < today)
    charges_tot = niv["charges_directes"] + niv["charges_structure"] + niv["cout_gr"]
    budget_produits = Budget.objects.filter(
        fiscal_year_id=fiscal_year, type_budget="produit", statut__in=("approuve", "cloture")
    ).aggregate(t=Sum("montant"))["t"] or ZERO
    valeurs = {
        "01": niv["taux_brute"], "02": niv["taux_operationnelle"], "03": niv["taux_nette"],
        "04": _pct(exe["charge"][1], exe["charge"][0]), "05": _pct(exe["produit"][1], exe["produit"][0]),
        "06": (sum(sa, ZERO) / len(sa)).quantize(CENT) if sa else None,
        "07": _pct(Decimal(sum(1 for c in conformes if c)), Decimal(3)) if conformes else None,
        "08": Decimal(clo["max_jours_ecoulement"]) if clo["max_jours_ecoulement"] is not None else None,
        "09": _pct(Decimal(sum(1 for c in publiees if c.date_publication <= c.echeance_j4)), Decimal(len(publiees))),
        "10": _pct(Decimal(rendues_a_temps), Decimal(dues)),
        "11": _pct(niv["cout_gr"], charges_tot),
        "12": _pct(pipe_pondere_m11(fiscal_year)["total"], budget_produits),
    }
    sortie = []
    for num, libelle, unite, sens, formule in KPI_DEFS:
        v = valeurs[num]
        cible = get_param_gestion(f"KPI_{num}")
        atteint = None if v is None else (v >= cible if sens == "min" else v <= cible)
        sortie.append({"code": f"KP-M11-{num}", "libelle": libelle, "unite": unite, "sens": sens, "formule": formule,
                       "valeur": _s(v), "cible": _s(cible), "atteint": atteint})
    return {"kpis": sortie, "provisoire": True,
            "cibles_provisoires": parametres_gestion_provisoires(tuple(f"KPI_{n}" for n in KPI_CIBLES_DEFAUT))}


# --------------------------------------------------------------------------------------------------
# PDF et archivage GED (PV budgétaire, reporting, revue de performance) — conservation paramétrée (10 ans)
# --------------------------------------------------------------------------------------------------
def _archiver(contenu, nom, titre, type_code, type_label, reference, objet_type, objet_id, user, mots, note):
    from hse.services import archiver_ged

    return archiver_ged(
        contenu, nom, titre, type_code, type_label, reference, objet_type, objet_id,
        user=user if getattr(user, "is_authenticated", False) else None, mots=mots, module="M11", note=note,
        retention=int(get_param_gestion("CONSERVATION_BUDGET_ANS")),
    )


def _qui(u, le):
    return f"{u.get_full_name() or u.email} le {timezone.localtime(le):%d/%m/%Y %H:%M}" if u and le else "—"


def archiver_pv_budget(obj, user=None):
    """PV de validation (double visa DAF + CG) d'un budget V0 ou d'une révision R1-R4, archivé en GED."""
    from hse.services import _pdf

    from .models import Budget

    conservation = int(get_param_gestion("CONSERVATION_BUDGET_ANS"))
    if isinstance(obj, Budget):
        budget, titre = obj, f"PV de validation budgétaire {obj.code} (version V0)"
        tableau = [["Période", "Montant (FCFA)"]] + [
            [str(l.period), f"{l.montant:,.2f}".replace(",", " ")] for l in obj.lignes.select_related("period")
        ]
        objet_type, montant = "controle_gestion.budget", obj.montant
    else:
        budget, titre = obj.budget, f"PV de validation de la révision R{obj.numero} {obj.code} — budget {obj.budget.code}"
        tableau = [["Période", "Avant", "Après"]] + [
            [str(l.period), f"{l.ancien_montant:.2f}", f"{l.nouveau_montant:.2f}"] for l in obj.lignes.select_related("period")
        ]
        objet_type, montant = "controle_gestion.budgetrevision", obj.nouveau_montant
    blocs = [
        ("Budget", f"{budget.code} — {budget.label} ({budget.get_type_budget_display()})"),
        ("Exercice", budget.fiscal_year.year),
        ("Axe", f"{budget.axis.code if budget.axis_id else '—'} / {budget.analytic.label if budget.analytic_id else '—'}"),
        ("Montant validé (FCFA)", f"{montant:.2f}"),
        ("Visa DAF", _qui(obj.visa_daf_par, obj.visa_daf_le)),
        ("Visa Contrôle de gestion", _qui(obj.visa_cg_par, obj.visa_cg_le)),
        ("Conservation", f"{conservation} ans (paramètre provisoire, à confirmer par ETSL)"),
    ]
    if not isinstance(obj, Budget):
        blocs.insert(3, ("Montant avant révision (FCFA)", f"{obj.ancien_montant:.2f}"))
        blocs.append(("Commentaire", obj.commentaire))
    contenu = _pdf(titre, blocs, tableau if len(tableau) > 1 else None)
    return _archiver(contenu, f"PV-{obj.code}.pdf", titre, "PV_BUDGET", "PV de validation budgétaire", obj.code,
                     objet_type, obj.pk, user, ["budget", "PV", obj.code, budget.code], "PV de validation budgétaire")


def _periodes_reporting(cloture, type_reporting):
    from accounting_kernel.models import Period

    if type_reporting == "j4":
        n = int(get_param_gestion("REPORTING_HORIZON_J4"))
        return list(reversed(Period.objects.filter(end_date__lte=cloture.period.end_date).order_by("-end_date")[:n])), n
    n = int(get_param_gestion("REPORTING_HORIZON_J6"))
    return list(Period.objects.filter(start_date__gte=cloture.period.start_date).order_by("start_date")[:n]), n


def donnees_reporting(cloture, type_reporting):
    """Reporting du mois : J+4 = réalisé vs budget sur les N derniers mois ; J+6 = prévision sur N mois à partir du mois.

    Horizon N = paramètre provisoire (12 / 3 mois). Coût GR (618) isolé.
    """
    from accounting_kernel.models import AccountMove, AccountMoveLine
    from referentiels.models import Account

    from .models import BudgetLigne

    if type_reporting not in ("j4", "j6"):
        raise ValidationError("Type de reporting : « j4 » ou « j6 ».")
    periods, horizon = _periodes_reporting(cloture, type_reporting)
    ids = [p.pk for p in periods]
    is_gr = Q(account__code="618000")
    reel = {
        r["move__period_id"]: r
        for r in AccountMoveLine.objects.filter(
            move__period_id__in=ids, move__status__in=(AccountMove.Status.POSTED, AccountMove.Status.REVERSED)
        ).values("move__period_id").annotate(
            produits=Sum(_net(Q(account__account_type=Account.AccountType.INCOME), "credit", "debit")),
            charges=Sum(_net(Q(account__account_type=Account.AccountType.EXPENSE) & ~is_gr, "debit", "credit")),
            gr=Sum(_net(is_gr, "debit", "credit")),
        )
    }
    bud = defaultdict(Decimal)
    for l in BudgetLigne.objects.filter(period_id__in=ids, budget__statut__in=("approuve", "cloture")).select_related("budget"):
        bud[(l.period_id, l.budget.type_budget)] += l.montant
    rows = []
    for p in periods:
        r = reel.get(p.pk) or {}
        prod, ch, gr = (r.get(k) or ZERO for k in ("produits", "charges", "gr"))
        rows.append({
            "period": p.pk, "period_label": str(p), "budget_produits": _s(bud[(p.pk, "produit")]), "produits": _s(prod),
            "budget_charges": _s(bud[(p.pk, "charge")]), "charges": _s(ch), "cout_gr": _s(gr),
            "marge": _s(prod - ch - gr), "marge_budget": _s(bud[(p.pk, "produit")] - bud[(p.pk, "charge")]),
        })
    return {
        "type": type_reporting, "horizon": horizon, "cloture": cloture.code, "period_label": str(cloture.period),
        "echeance": (cloture.echeance_j4 if type_reporting == "j4" else cloture.echeance_j6).isoformat(),
        "rows": rows,
        "provisoire": parametres_gestion_provisoires(("REPORTING_HORIZON_J4", "REPORTING_HORIZON_J6") + (
            "REPORTING_JOUR_J4", "REPORTING_JOUR_J6")),
    }


def reporting_pdf(cloture, type_reporting):
    from hse.services import _pdf

    d = donnees_reporting(cloture, type_reporting)
    titre = (tr("Reporting de gestion %(period_label)s — %(valeur)s %(horizon)s mois (J+%(valeur2)s)") % {"period_label": d['period_label'], "valeur": 'réalisé' if type_reporting == 'j4' else 'prévision', "horizon": d['horizon'], "valeur2": 4 if type_reporting == 'j4' else 6})
    blocs = [(tr("Clôture"), d["cloture"]), (tr("Échéance de publication"), d["echeance"]),
             (tr("Avertissement"), tr("Horizons et jours de publication provisoires, à confirmer par ETSL.") if d["provisoire"] else "—")]
    tableau = [[tr("Période"), tr("Budget produits"), tr("Produits"), tr("Budget charges"), tr("Charges"), tr("Coût GR"), tr("Marge")]] + [
        [r["period_label"], r["budget_produits"], r["produits"], r["budget_charges"], r["charges"], r["cout_gr"], r["marge"]]
        for r in d["rows"]
    ]
    return _pdf(titre, blocs, tableau), titre


@transaction.atomic
def archiver_reporting(cloture, type_reporting, user=None):
    from .models import ClotureGestion, ReportingArchive

    if cloture.statut != ClotureGestion.Statut.REALISEE:
        raise ValidationError("La clôture de gestion doit être réalisée avant d'archiver le reporting.")
    if ReportingArchive.objects.select_for_update().filter(cloture=cloture, type_reporting=type_reporting).exists():
        raise ValidationError("Reporting déjà archivé pour ce mois et cet horizon.")
    contenu, titre = en_francais(reporting_pdf, cloture, type_reporting)  # archive : français
    echeance = cloture.echeance_j4 if type_reporting == "j4" else cloture.echeance_j6
    document = _archiver(contenu, f"REPORTING-{cloture.code}-{type_reporting.upper()}.pdf", titre, "REPORTING_GESTION",
                         "Reporting de gestion", cloture.code, "controle_gestion.cloturegestion", cloture.pk, user,
                         ["reporting", cloture.code, type_reporting.upper()], "Reporting de gestion archivé")
    _, horizon = _periodes_reporting(cloture, type_reporting)
    return ReportingArchive.objects.create(
        cloture=cloture, type_reporting=type_reporting, horizon=horizon, echeance=echeance,
        a_temps=timezone.localdate() <= echeance, document=document,
        archive_par=user if getattr(user, "is_authenticated", False) else None,
    )


ODJ_REVUE_DEFAUT = (
    "1. Réalisé du mois et cumul face au budget (écarts > 10 %)\n"
    "2. Marges brute, opérationnelle, nette ; coût GLOBAL RENTAL isolé\n"
    "3. KPI KP-M11-01 à 12\n"
    "4. Sous-activité (centres 90 / 91 / 99) et plans d'action\n"
    "5. Atterrissage et reprévision\n"
    "6. Décisions et actions"
)


@transaction.atomic
def tenir_revue(revue, decisions, user=None):
    """Clôt la revue P-M11.10 : KPI figés, PV PDF archivé en GED (conservation paramétrée)."""
    from hse.services import _pdf

    from .models import RevuePerformance

    revue = RevuePerformance.objects.select_for_update(of=("self",)).select_related("period").get(pk=revue.pk)
    if revue.statut != RevuePerformance.Statut.PLANIFIEE:
        raise ValidationError("Revue déjà tenue (PV archivé).")
    if not (decisions or "").strip():
        raise ValidationError({"decisions": "Décisions de la revue obligatoires."})
    kpis = compute_kpis(revue.period.fiscal_year_id)["kpis"]
    revue.decisions = decisions.strip()
    revue.kpis = kpis
    titre = f"PV de revue de performance {revue.code} — {revue.period}"
    blocs = [("Date", f"{revue.date_revue:%d/%m/%Y}"), ("Participants", revue.participants),
             ("Ordre du jour", revue.ordre_du_jour), ("Décisions et actions", revue.decisions)]
    tableau = [["KPI", "Libellé", "Valeur", "Cible", "Atteint"]] + [
        [k["code"], k["libelle"], f"{k['valeur'] or '—'} {k['unite']}", k["cible"],
         "—" if k["atteint"] is None else ("oui" if k["atteint"] else "non")] for k in kpis
    ]
    revue.pv_document = _archiver(_pdf(titre, blocs, tableau), f"PV-{revue.code}.pdf", titre, "PV_REVUE_PERF",
                                  "PV de revue de performance", revue.code, "controle_gestion.revueperformance",
                                  revue.pk, user, ["revue", "P-M11.10", revue.code], "PV de revue de performance")
    revue.statut = RevuePerformance.Statut.TENUE
    revue.tenue_par = user if getattr(user, "is_authenticated", False) else None
    revue.tenue_le = timezone.now()
    revue.save()
    return revue


# --------------------------------------------------------------------------------------------------
# Plan d'action de sous-activité
# --------------------------------------------------------------------------------------------------
def situation_sous_activite(budget):
    """(centre, taux, alerte) actuels du budget (None si aucune période écoulée)."""
    from .models import AlerteSousActivite
    from .services import compute_sous_activite

    row = next((r for r in compute_sous_activite(budget.fiscal_year_id)["rows"] if r["budget"] == budget.pk), None)
    alerte = AlerteSousActivite.objects.filter(budget=budget, centre="99").first()
    return (row["centre"] if row else "", row["taux_sous_activite"] if row else None, alerte)


# --------------------------------------------------------------------------------------------------
# Validation de la marge d'affaire
# --------------------------------------------------------------------------------------------------
def marges_a_valider():
    from commercial.models import Affaire

    from .models import ValidationMarge

    derniere = {}
    for v in ValidationMarge.objects.select_related("par").order_by("le"):
        derniere[v.affaire_id] = v
    rows = []
    for a in Affaire.objects.exclude(status=Affaire.Status.ARCHIVEE).select_related("client__partner").prefetch_related("contracts"):
        v = derniere.get(a.pk)
        a_revalider = bool(v and v.statut == "validee" and (v.ca != a.contract_amount or v.marge != a.margin))
        rows.append({
            "affaire": str(a.pk), "code": a.code, "titre": a.title, "statut_affaire": a.status,
            "client": a.client.partner.name if a.client_id else "", "profil": profil_affaire(a),
            "ca": a.contract_amount, "marge": a.margin, "taux": _s(_pct(a.margin, a.contract_amount)),
            "validation": ("a_revalider" if a_revalider else v.statut) if v else "a_valider",
            "valide_par": (v.par.get_full_name() or v.par.email) if v else None,
            "valide_le": v.le.isoformat() if v else None, "commentaire": v.commentaire if v else "",
        })
    rows.sort(key=lambda r: r["code"])
    return rows


def decider_marge(affaire_id, statut, commentaire, user):
    from commercial.models import Affaire

    from .models import ValidationMarge

    try:
        affaire = Affaire.objects.select_for_update().get(pk=affaire_id)
    except (Affaire.DoesNotExist, ValueError, ValidationError):
        raise ValidationError("Affaire introuvable.")
    if statut == "rejetee" and not (commentaire or "").strip():
        raise ValidationError({"commentaire": "Motif du rejet obligatoire."})
    if statut == "validee" and not affaire.contract_amount:
        raise ValidationError("Affaire sans montant contractuel : marge non validable.")
    return ValidationMarge.objects.create(
        affaire=affaire, ca=affaire.contract_amount, marge=affaire.margin, statut=statut,
        commentaire=(commentaire or "").strip()[:250], par=user,
    )


# --------------------------------------------------------------------------------------------------
# Coût de main-d'œuvre chargé par affaire (lecture M9, PR #49)
# --------------------------------------------------------------------------------------------------
def cout_mo_par_affaire(debut, fin):
    from rh_paie.compta_m9b import cout_main_oeuvre

    par = {}
    for l in cout_main_oeuvre(debut, fin):
        cle = l["affaire"] or "—"
        g = par.setdefault(cle, {"affaire": cle, "ordres": 0, "heures": ZERO, "cout": ZERO, "heures_non_valorisees": ZERO})
        g["ordres"] += 1
        for k in ("heures", "cout", "heures_non_valorisees"):
            g[k] += Decimal(l[k] or "0")
    rows = sorted(par.values(), key=lambda g: g["affaire"])
    for g in rows:
        g["cout_horaire_moyen"] = (g["cout"] / (g["heures"] - g["heures_non_valorisees"])).quantize(CENT) \
            if g["heures"] - g["heures_non_valorisees"] > 0 else None
    return rows


# --------------------------------------------------------------------------------------------------
# Provision des factures non parvenues (408)
# --------------------------------------------------------------------------------------------------
def _compte_fnp():
    from referentiels.models import Account

    code = str(int(get_param_gestion("PROVISION_FNP_COMPTE")))
    compte, _ = Account.objects.get_or_create(
        code=code, defaults={"label": "Fournisseurs, factures non parvenues", "account_class": 4,
                             "account_type": Account.AccountType.LIABILITY},
    )
    return compte


def calculer_fnp(date_arrete):
    """Réceptions validées à la date d'arrêté non couvertes par une facture comptabilisée : quantité × prix du BC."""
    from achats.comptabilisation import _compte
    from achats.models import GoodsReceipt, GoodsReceiptLine, PurchaseInvoice, PurchaseInvoiceLine, PurchaseOrderLine

    recu = {
        r["purchase_order_line"]: r["q"] or ZERO
        for r in GoodsReceiptLine.objects.filter(
            receipt__status=GoodsReceipt.Status.VALIDE, receipt__received_at__lte=date_arrete
        ).values("purchase_order_line").annotate(q=Sum("quantity"))
    }
    facture = {
        r["purchase_order_line"]: r["q"] or ZERO
        for r in PurchaseInvoiceLine.objects.filter(
            invoice__status=PurchaseInvoice.Status.COMPTABILISEE, invoice__invoice_date__lte=date_arrete,
            purchase_order_line_id__in=list(recu),
        ).values("purchase_order_line").annotate(q=Sum("quantity"))
    }
    lignes = []
    pols = PurchaseOrderLine.objects.filter(pk__in=list(recu)).select_related(
        "purchase_order__supplier", "purchase_order__analytic", "article__account"
    )
    for pol in pols:
        reste = recu[pol.pk] - facture.get(pol.pk, ZERO)
        if reste <= 0:
            continue
        bc = pol.purchase_order
        if bc.is_global_rental:
            compte = _compte("618000")
        elif pol.article_id and pol.article.account_id:
            compte = pol.article.account
        else:
            compte = _compte("601000")
        lignes.append({
            "bc": bc.code, "ligne": pol.label, "fournisseur": bc.supplier.name if bc.supplier_id else "",
            "supplier_id": bc.supplier_id, "analytic_id": bc.analytic_id, "compte": compte.code, "compte_id": compte.pk,
            "quantite": f"{reste:.2f}", "prix": f"{pol.unit_price:.2f}", "montant": f"{(reste * pol.unit_price).quantize(CENT):.2f}",
        })
    lignes.sort(key=lambda x: (x["bc"], x["ligne"]))
    return lignes


@transaction.atomic
def provisionner_fnp(date_arrete, user=None):
    from accounting_kernel.models import AccountMove, AccountMoveLine, Journal
    from accounting_kernel.services import period_for_date, post_move

    from .models import ProvisionFnp

    if ProvisionFnp.objects.select_for_update().filter(date_arrete=date_arrete).exists():
        raise ValidationError("Provision déjà passée à cette date d'arrêté.")
    ouverte = ProvisionFnp.objects.filter(statut=ProvisionFnp.Statut.COMPTABILISEE).first()
    if ouverte:
        raise ValidationError(tr("Extournez d'abord la provision %(ouverte_code)s (%(ouverte_date_arrete)s).") % {"ouverte_code": ouverte.code, "ouverte_date_arrete": format(ouverte.date_arrete, '%d/%m/%Y')})
    lignes = calculer_fnp(date_arrete)
    total = sum((Decimal(x["montant"]) for x in lignes), ZERO)
    if not total:
        raise ValidationError("Aucune réception non facturée à cette date : rien à provisionner.")
    try:
        journal = Journal.objects.get(code="OD")
    except Journal.DoesNotExist:
        raise ValidationError("Journal OD absent (seed_accounting).")
    provision = ProvisionFnp.objects.create(
        date_arrete=date_arrete, montant=total, detail=[{k: v for k, v in x.items() if not k.endswith("_id")} for x in lignes],
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )
    move = AccountMove.objects.create(
        journal=journal, period=period_for_date(date_arrete), date=date_arrete, reference=provision.code,
        label=f"Provision factures non parvenues au {date_arrete:%d/%m/%Y}", source="M11", source_ref=provision.code,
        status=AccountMove.Status.DRAFT,
    )
    debits, credits = defaultdict(Decimal), defaultdict(Decimal)
    for x in lignes:
        debits[(x["compte_id"], x["analytic_id"], x["supplier_id"])] += Decimal(x["montant"])
        credits[x["supplier_id"]] += Decimal(x["montant"])
    fnp = _compte_fnp()
    ordre = 0
    for (compte_id, analytic_id, supplier_id), m in debits.items():
        AccountMoveLine.objects.create(move=move, account_id=compte_id, analytic_account_id=analytic_id,
                                       partner_id=supplier_id, label="Réception non facturée", debit=m, credit=0, order=ordre)
        ordre += 1
    for supplier_id, m in credits.items():
        AccountMoveLine.objects.create(move=move, account=fnp, partner_id=supplier_id, label="Facture non parvenue",
                                       debit=0, credit=m, order=ordre)
        ordre += 1
    provision.move = post_move(move, user=user if getattr(user, "is_authenticated", False) else None)
    provision.save(update_fields=["move", "updated_at"])
    return provision


@transaction.atomic
def extourner_fnp(provision, date=None, user=None):
    from accounting_kernel.services import reverse_move

    from .models import ProvisionFnp

    provision = ProvisionFnp.objects.select_for_update(of=("self",)).get(pk=provision.pk)
    if provision.statut != ProvisionFnp.Statut.COMPTABILISEE:
        raise ValidationError("Provision déjà extournée.")
    jour = date or (provision.date_arrete + timedelta(days=1))
    if jour <= provision.date_arrete:
        raise ValidationError("L'extourne doit être datée après la date d'arrêté.")
    provision.extourne = reverse_move(
        provision.move, user=user if getattr(user, "is_authenticated", False) else None, date=jour,
        reference=f"Extourne {provision.code}", label=f"Extourne provision FNP {provision.code}",
    )
    provision.statut = ProvisionFnp.Statut.EXTOURNEE
    provision.save(update_fields=["extourne", "statut", "updated_at"])
    return provision
