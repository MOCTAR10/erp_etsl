"""Couche D — cubes OLAP à 6 axes : alimentation idempotente, lecture, archive scellée 10 ans.

Source unique des mesures : le grand livre comptabilisé (écritures POSTED et REVERSED, même base que
`controle_gestion.services.compute_marges`). Produits = crédit − débit (classe 7), charges = débit − crédit
(classe 6) hors 618, coût GLOBAL RENTAL (618000) isolé.
"""

import calendar
import hashlib
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Case, DecimalField, F, Q, Sum, Value, When
from django.utils import timezone

from outbox.models import publish

from .models import CubeArchive, CubeFait, ParametreCube

ZERO = Decimal("0")
AXES = ("affaire", "chantier", "site", "activite", "centre", "periode")
MESURES = ("produits", "charges", "cout_gr")
AXE_PAR_TYPE = {"projet": "affaire", "chantier": "chantier", "site": "site", "centre_cout": "centre"}

PARAMETRES_DEFAUT = {
    "RETENTION_ANS": ("Conservation de l'archive du cube (données Oil & Gas)", Decimal("10"), "ans"),
}


def get_param_cube(code):
    """Valeur du paramètre `code` ; crée le défaut provisoire si absent."""
    label, valeur, unite = PARAMETRES_DEFAUT[code]
    obj, _ = ParametreCube.objects.get_or_create(code=code, defaults={"label": label, "valeur": valeur, "unite": unite})
    return obj.valeur


def parametres_provisoires():
    for code in PARAMETRES_DEFAUT:
        get_param_cube(code)
    return ParametreCube.objects.filter(code__in=PARAMETRES_DEFAUT).exclude(statut_valeur="confirme").exists()


def _bornes(periode):
    """(premier jour, dernier jour) de `periode` AAAA-MM ; ValueError si invalide."""
    try:
        annee, mois = (int(x) for x in str(periode).split("-"))
        debut = date(annee, mois, 1)
    except (ValueError, TypeError):
        raise ValueError("Période invalide : attendu AAAA-MM.") from None
    if len(str(periode)) != 7:
        raise ValueError("Période invalide : attendu AAAA-MM.")
    return debut, date(annee, mois, calendar.monthrange(annee, mois)[1])


def _net(cond, plus, minus):
    return Case(
        When(cond, then=F(plus) - F(minus)),
        default=Value(ZERO),
        output_field=DecimalField(max_digits=18, decimal_places=2),
    )


def _faits_du_grand_livre(debut, fin):
    """Faits agrégés (un dict par combinaison d'axes) du grand livre comptabilisé entre `debut` et `fin`."""
    from accounting_kernel.models import AccountMove, AccountMoveLine
    from commercial.models import Affaire
    from referentiels.models import Account, AnalyticAccount

    posted = AccountMove.objects.filter(
        date__gte=debut, date__lte=fin, status__in=(AccountMove.Status.POSTED, AccountMove.Status.REVERSED)
    ).values_list("id", flat=True)
    lignes = AccountMoveLine.objects.filter(move_id__in=posted, account__account_class__in=(6, 7))
    is_gr = Q(account__code="618000")
    is_income = Q(account__account_type=Account.AccountType.INCOME)
    is_charge = Q(account__account_type=Account.AccountType.EXPENSE) & ~is_gr
    groupes = lignes.values("analytic_account_id").annotate(
        produits=Sum(_net(is_income, "credit", "debit")),
        charges=Sum(_net(is_charge, "debit", "credit")),
        cout_gr=Sum(_net(is_gr, "debit", "credit")),
    )
    analytiques = {
        a.id: a
        for a in AnalyticAccount.objects.filter(id__in=[g["analytic_account_id"] for g in groupes if g["analytic_account_id"]])
        .select_related("axis")
    }
    activites = {
        a["analytic_id"]: ("global_rental" if a["is_global_rental"] else a["affaire_type"])
        for a in Affaire.objects.filter(analytic_id__in=list(analytiques)).values("analytic_id", "affaire_type", "is_global_rental")
    }
    cumul = defaultdict(lambda: {m: ZERO for m in MESURES})
    for g in groupes:
        cle = {a: "" for a in AXES if a != "periode"}
        aid = g["analytic_account_id"]
        if aid in analytiques:
            dim = AXE_PAR_TYPE.get(analytiques[aid].axis.axis_type)
            if dim:
                cle[dim] = analytiques[aid].code
            cle["activite"] = activites.get(aid, "")
        cible = cumul[tuple(cle[a] for a in AXES if a != "periode")]
        for m in MESURES:
            cible[m] += g[m] or ZERO
    return [
        {**dict(zip([a for a in AXES if a != "periode"], cle)), **{m: v[m] for m in MESURES}}
        for cle, v in cumul.items()
        if any(v[m] for m in MESURES)
    ]


@transaction.atomic
def alimenter_cube(periode):
    """Reconstruit les faits de `periode` depuis le grand livre. Idempotent : rejouer donne le même cube."""
    debut, fin = _bornes(periode)
    if CubeArchive.objects.filter(periode=periode).exists():
        raise ValueError(f"Le cube {periode} est archivé : il ne peut plus être recalculé.")
    CubeFait.objects.filter(periode=periode).delete()
    faits = _faits_du_grand_livre(debut, fin)
    CubeFait.objects.bulk_create([CubeFait(periode=periode, **f) for f in faits])
    return len(faits)


def _sceller(faits):
    contenu = json.dumps(faits, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(contenu.encode("utf-8")).hexdigest()


def _serialiser(qs):
    return [
        {**{a: getattr(f, a) for a in AXES if a != "periode"}, **{m: f"{getattr(f, m):.2f}" for m in MESURES}}
        for f in qs.order_by("affaire", "chantier", "site", "activite", "centre")
    ]


def _ajouter_annees(jour, annees):
    annee = jour.year + annees
    return jour.replace(year=annee, day=min(jour.day, calendar.monthrange(annee, jour.month)[1]))


@transaction.atomic
def archiver_cube(periode, user=None, today=None):
    """Fige le cube d'un mois terminé : faits rafraîchis, scellés (SHA-256), conservés N ans, immuables."""
    today = today or timezone.localdate()
    debut, fin = _bornes(periode)
    if fin >= today:
        raise ValueError("La période n'est pas terminée : le cube ne peut être archivé qu'après la fin du mois.")
    if CubeArchive.objects.filter(periode=periode).exists():
        raise ValueError(f"Le cube {periode} est déjà archivé.")
    alimenter_cube(periode)
    faits = _serialiser(CubeFait.objects.filter(periode=periode))
    total = {m: sum((Decimal(f[m]) for f in faits), ZERO) for m in MESURES}
    annees = int(get_param_cube("RETENTION_ANS"))
    archive = CubeArchive.objects.create(
        periode=periode, faits=faits, nb_faits=len(faits), sha256=_sceller(faits),
        conserve_jusqu_au=_ajouter_annees(fin, annees), retention_provisoire=parametres_provisoires(),
        created_by=user, **total,
    )
    publish("analytics.cube.archive", {
        "periode": periode, "sha256": archive.sha256, "conserve_jusqu_au": str(archive.conserve_jusqu_au),
        **{m: str(total[m]) for m in MESURES},
    })
    return archive


def verifier_archive(archive):
    """True si les faits stockés correspondent encore au sceau SHA-256."""
    return _sceller(archive.faits) == archive.sha256


def lire_cube(periodes=None, axes=("periode",), filtres=None):
    """Coupe du cube : mesures agrégées selon `axes` (sous-ensemble des 6 axes), filtrées par `filtres` {axe: valeur}.

    Une période archivée est lue dans l'archive scellée, sinon dans les faits courants.
    """
    for a in axes:
        if a not in AXES:
            raise ValueError(f"Axe inconnu : {a} (attendu : {', '.join(AXES)}).")
    filtres = {k: v for k, v in (filtres or {}).items() if v not in (None, "")}
    for k in filtres:
        if k not in AXES:
            raise ValueError(f"Filtre inconnu : {k}.")
    archives = {a.periode: a for a in CubeArchive.objects.all()}
    qs = CubeFait.objects.all()
    if periodes:
        qs = qs.filter(periode__in=periodes)
    lignes = [
        {"periode": f.periode, **{a: getattr(f, a) for a in AXES if a != "periode"}, **{m: getattr(f, m) for m in MESURES}}
        for f in qs
        if f.periode not in archives
    ]
    for p, arc in archives.items():
        if periodes and p not in periodes:
            continue
        lignes += [{"periode": p, **{k: (Decimal(v) if k in MESURES else v) for k, v in f.items()}} for f in arc.faits]
    lignes = [l for l in lignes if all(l.get(k) == v for k, v in filtres.items())]
    cumul = defaultdict(lambda: {m: ZERO for m in MESURES})
    for l in lignes:
        cible = cumul[tuple(l[a] for a in axes)]
        for m in MESURES:
            cible[m] += l[m]
    rows = [
        {**dict(zip(axes, cle)), **{m: f"{v[m]:.2f}" for m in MESURES}, "marge": f"{v['produits'] - v['charges']:.2f}"}
        for cle, v in sorted(cumul.items())
    ]
    totaux = {m: sum((v[m] for v in cumul.values()), ZERO) for m in MESURES}
    return {
        "axes": list(axes),
        "rows": rows,
        "totaux": {**{m: f"{t:.2f}" for m, t in totaux.items()}, "marge": f"{totaux['produits'] - totaux['charges']:.2f}"},
        "periodes_archivees": sorted(p for p in archives if not periodes or p in periodes),
        "parametres_provisoires": parametres_provisoires(),
    }
