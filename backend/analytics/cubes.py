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
    "RETENTION_SCELLE_ANS": ("Durée de garde des scellés de marts opérationnels", Decimal("5"), "ans"),
    "BLOCAGE_AVANT_CLOTURE": ("Données financières réservées aux producteurs avant clôture M11 (1 = oui, 0 = non)",
                              Decimal("1"), "0/1"),
    "PALIER_ALERTE_J60": ("Palier d'alerte supplémentaire avant échéance (0 = aucun)", Decimal("60"), "jours"),
    "REVUE_DIRECTION_MOIS": ("Périodicité de la revue de direction", Decimal("12"), "mois"),
    "TRESO_DELAI_ENCAISSEMENT": ("Cash-flow : délai d'encaissement d'une facture sans échéance", Decimal("30"), "jours"),
    "TRESO_DELAI_DECAISSEMENT": ("Cash-flow : délai de décaissement (facture fournisseur, engagement)",
                                 Decimal("30"), "jours"),
    "BUDGET_SEUIL_ALERTE": ("Seuil budgétaire : alerte", Decimal("90"), "%"),
    "BUDGET_SEUIL_ATTEINT": ("Seuil budgétaire : budget atteint", Decimal("100"), "%"),
    "BUDGET_SEUIL_DEPASSE": ("Seuil budgétaire : dépassement (analyse obligatoire)", Decimal("110"), "%"),
}
# Paramètres pouvant valoir 0 (interrupteur ou palier désactivé).
PARAMETRES_ZERO_AUTORISE = ("BLOCAGE_AVANT_CLOTURE", "PALIER_ALERTE_J60")
TYPE_GED_CUBE = "archive-cube-bi"
DOSSIER_GED_CUBE = "Archives BI (Couche D)"


def get_param_cube(code):
    """Valeur du paramètre `code` ; crée le défaut provisoire si absent."""
    label, valeur, unite = PARAMETRES_DEFAUT[code]
    obj, _ = ParametreCube.objects.get_or_create(code=code, defaults={"label": label, "valeur": valeur, "unite": unite})
    return obj.valeur


def param_provisoire(code):
    get_param_cube(code)
    return ParametreCube.objects.filter(code=code).exclude(statut_valeur="confirme").exists()


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
    sha = _sceller(faits)
    archive = CubeArchive.objects.create(
        periode=periode, faits=faits, nb_faits=len(faits), sha256=sha,
        conserve_jusqu_au=_ajouter_annees(fin, annees), retention_provisoire=param_provisoire("RETENTION_ANS"),
        document=_archiver_ged(periode, fin, faits, sha, annees, user), created_by=user, **total,
    )
    publish("analytics.cube.archive", {
        "periode": periode, "sha256": archive.sha256, "conserve_jusqu_au": str(archive.conserve_jusqu_au),
        **{m: str(total[m]) for m in MESURES},
    })
    return archive


def _archiver_ged(periode, fin, faits, sha_faits, annees, user):
    """Dépose le cube figé en GED (CSV, type « archive-cube-bi », conservation N ans), dans un dossier refusé aux
    utilisateurs hors cercle des montants M11 (RF-59)."""
    import csv
    import io

    from django.core.files.base import ContentFile

    from controle_gestion.services import can_see_amount
    from documents.models import Document, DocumentType, Dossier, DossierAccess, Version
    from users.models import User

    type_doc, _ = DocumentType.objects.get_or_create(
        code=TYPE_GED_CUBE, defaults={"label": "Archives BI (cubes Couche D)", "retention_years": annees}
    )
    if type_doc.retention_years != annees:
        type_doc.retention_years = annees
        type_doc.save(update_fields=["retention_years"])
    dossier = Dossier.objects.filter(name=DOSSIER_GED_CUBE, parent__isnull=True).first() or Dossier.objects.create(
        name=DOSSIER_GED_CUBE, created_by=user
    )
    for u in User.objects.filter(is_active=True):
        if not can_see_amount(u):
            DossierAccess.objects.update_or_create(
                dossier=dossier, user=u, defaults={"permission": DossierAccess.Permission.DENY}
            )
    buf = io.StringIO()
    colonnes = [a for a in AXES if a != "periode"] + list(MESURES)
    w = csv.writer(buf, delimiter=";")
    w.writerow(["periode", *colonnes])
    for f in faits:
        w.writerow([periode, *(f[c] for c in colonnes)])
    w.writerow([])
    w.writerow(["sha256_faits", sha_faits])
    contenu = buf.getvalue().encode("utf-8-sig")
    sha = hashlib.sha256(contenu).hexdigest()
    nom = f"cube_{periode}.csv"
    document = Document.objects.create(
        title=f"Cube BI {periode} — archive scellée", status=Document.Status.ARCHIVED, archived_at=timezone.now(),
        type=type_doc, dossier=dossier, document_date=fin, reference=f"CUBE-{periode}",
        keywords=["couche D", "cube", periode], sha256=sha, created_by=user,
    )
    version = Version.objects.create(
        document=document, number=1, file=ContentFile(contenu, name=nom), sha256=sha, size=len(contenu),
        original_filename=nom, created_by=user,
    )
    document.current_version = version
    document.save(update_fields=["current_version"])
    return document


def verifier_archive(archive):
    """True si les faits stockés correspondent encore au sceau SHA-256."""
    return _sceller(archive.faits) == archive.sha256


def lire_cube(periodes=None, axes=("periode",), filtres=None, user=None):
    """Coupe du cube : mesures agrégées selon `axes` (sous-ensemble des 6 axes), filtrées par `filtres` {axe: valeur}.

    Une période archivée est lue dans l'archive scellée, sinon dans les faits courants. Avec `user` consommateur
    (hors producteurs des chiffres) et le blocage actif, seuls les mois dont la clôture M11 est réalisée sont servis.
    """
    from .pilotage import periodes_cloturees, voit_non_cloture

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
    masquees = []
    if not voit_non_cloture(user):
        cloturees = periodes_cloturees()
        masquees = sorted({l["periode"] for l in lignes if l["periode"] not in cloturees})
        lignes = [l for l in lignes if l["periode"] in cloturees]
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
        "periodes_non_publiees": masquees,
        "parametres_provisoires": parametres_provisoires(),
    }
