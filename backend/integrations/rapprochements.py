"""Contrôles de rapprochement C1-C10 du plan de migration (ETSL-ERP-MIG §6.3) — base du PV de migration.

Chaque contrôle calcule la valeur ERP ; la valeur du système source (SAGE, ALAN, inventaire, bordereau) est saisie à
l'écran (paramètre `source_cN`). Statut : conforme (écart nul), ecart, a_saisir (valeur source absente) ou
a_controler (C10 : comparaison champ à champ par le référent sur l'échantillon tiré).
"""

import csv
import io
from decimal import Decimal, InvalidOperation

from django.db.models import Count, Q, Sum

from .importers_migration import GABARITS, echantillon, get_param_reprise
from .models_migration import HistoriquePaie, LigneReprise, LotReprise
from config.i18n import tr

ZERO = Decimal("0")

CONTROLES = [
    ("C1", "Balance d'ouverture = balance SAGE (total débit)", "DAF + commissaire aux comptes"),
    ("C2", "Pièces ouvertes : solde net 401 + 411, total et par tiers", "DAF"),
    ("C3", "Quantités de stock (toutes lignes dépôt × article × lot)", "Responsable magasin"),
    ("C4", "Valeur de stock = comptes de stock (classe 3) en balance", "DAF"),
    ("C5", "Effectifs actifs (en poste + congé / rotation)", "DRH"),
    ("C6", "Paie : nombre de salariés-mois repris", "DRH"),
    ("C7", "Référentiels : tiers + articles chargés", "Référent du domaine"),
    ("C8", "Qualité : WPS / WPQR + qualifications soudeurs", "QA/QC"),
    ("C9", "GED : documents repris (empreinte SHA-256 vérifiée)", "Juridique"),
    ("C10", "Échantillonnage aléatoire par objet", "Référent du domaine"),
]


def _dec(valeur):
    if valeur in (None, ""):
        return None
    try:
        return Decimal(str(valeur).replace(" ", "").replace(",", "."))
    except InvalidOperation:
        return None


def _c1():
    from accounting_kernel.models import AccountMove

    move = (AccountMove.objects.filter(source="integrations", reference__startswith="AN-", status="posted")
            .order_by("-date").prefetch_related("lines").first())
    if move is None:
        return ZERO, "Aucune balance d'ouverture chargée."
    debit, credit = move.total_debit, move.total_credit
    return debit, (f"{move.reference} du {move.date:%d/%m/%Y} : débit {debit} / crédit {credit}, "
                   f"{move.lines.count()} comptes, {'équilibrée' if debit == credit else 'DÉSÉQUILIBRÉE'}.")


def _solde(prefixes):
    from accounting_kernel.models import AccountMoveLine

    filtre = Q()
    for p in prefixes:
        filtre |= Q(account__code__startswith=p)
    agg = AccountMoveLine.objects.filter(filtre, move__status__in=["posted", "reversed"]).aggregate(
        d=Sum("debit"), c=Sum("credit"))
    return (agg["d"] or ZERO) - (agg["c"] or ZERO)


def _soldes_par_tiers():
    """{code tiers: (nom, solde 401 + 411 débit − crédit)} ; clé None = part du compte collectif non ventilée."""
    from accounting_kernel.models import AccountMoveLine

    lignes = (AccountMoveLine.objects.filter(Q(account__code__startswith="411") | Q(account__code__startswith="401"),
                                             move__status__in=["posted", "reversed"])
              .values("partner__code", "partner__name").annotate(d=Sum("debit"), c=Sum("credit")))
    soldes = {}
    for ligne in lignes:
        code = ligne["partner__code"]
        nom, valeur = soldes.get(code, (ligne["partner__name"] or "", ZERO))
        soldes[code] = (nom, valeur + (ligne["d"] or ZERO) - (ligne["c"] or ZERO))
    return soldes


def sources_par_tiers(texte):
    """Soldes par tiers du système source (balance âgée SAGE) : une ligne `CODE;solde` (ou `CODE=solde`, tabulation),
    même convention que l'ERP (débit − crédit : client positif, fournisseur négatif). Lignes illisibles ignorées."""
    sources = {}
    for brut in (texte or "").replace("|", "\n").splitlines():
        for sep in (";", "=", "\t"):
            if sep in brut:
                code, _, montant = brut.partition(sep)
                valeur = _dec(montant)
                if code.strip() and valeur is not None:
                    sources[code.strip().upper()] = sources.get(code.strip().upper(), ZERO) + valeur
                break
    return sources


def _c2(texte_tiers=""):
    s411, s401 = _solde(["411"]), _solde(["401"])
    soldes = _soldes_par_tiers()
    non_ventile = soldes.pop(None, ("", ZERO))[1]
    sources = sources_par_tiers(texte_tiers)
    tiers = []
    for code in sorted(set(soldes) | set(sources)):
        nom, erp = soldes.get(code, ("", ZERO))
        source = sources.get(code.upper())
        if erp == 0 and source is None:
            continue
        tiers.append({"code": code, "nom": nom, "erp": str(erp), "source": None if source is None else str(source),
                      "ecart": None if source is None else str(erp - source)})
    ecarts = [t for t in tiers if t["ecart"] is not None and Decimal(t["ecart"]) != 0]
    detail = (tr("Solde 411 (clients) %(s411)s ; solde 401 (fournisseurs) %(s401)s (débit − crédit). %(nb_tiers)s tiers porteurs d'un solde ; part non ventilée par tiers (compte collectif) %(non_ventile)s.") % {"s411": s411, "s401": s401, "nb_tiers": len(tiers), "non_ventile": non_ventile})
    if sources:
        detail += tr(" Comparaison par tiers : %(nb_ecarts)s tiers en écart.") % {"nb_ecarts": len(ecarts)}
    return s411 + s401, detail, tiers, sources, ecarts


def _c3():
    from stocks.models import StockQuant

    agg = StockQuant.objects.aggregate(q=Sum("quantity"), n=Count("id"))
    return agg["q"] or ZERO, tr("%(n)s lignes de stock (dépôt × article × lot).") % {"n": agg['n']}


def _c4():
    from stocks.models import StockQuant

    valeur = StockQuant.objects.aggregate(v=Sum("stock_value"))["v"] or ZERO
    compta = _solde(["3"])
    return valeur, tr("Valorisation stock %(valeur)s ; solde comptes de stock (classe 3) %(compta)s ; écart %(valeur2)s.") % {"valeur": valeur, "compta": compta, "valeur2": valeur - compta}, compta


def _c5():
    from rh_paie.models import Employe

    actifs = Employe.objects.filter(statut__in=[Employe.Statut.ACTIF, Employe.Statut.CONGE])
    par_cat = ", ".join(f"{c['categorie']} {c['n']}" for c in actifs.values("categorie").annotate(n=Count("id")).order_by("categorie"))
    return Decimal(actifs.count()), tr("Par catégorie : %(valeur)s.") % {"valeur": par_cat or '—'}


def _c6():
    profondeur = int(get_param_reprise("HISTORIQUE_PAIE_MOIS"))
    par_salarie = HistoriquePaie.objects.values("employe").annotate(mois=Count("periode", distinct=True))
    salaries_mois = sum(p["mois"] for p in par_salarie)
    incomplets = sum(1 for p in par_salarie if p["mois"] < profondeur)
    return Decimal(salaries_mois), (tr("%(nb_par_salarie)s salariés repris, %(incomplets)s avec moins de %(profondeur)s mois d'historique.") % {"nb_par_salarie": len(par_salarie), "incomplets": incomplets, "profondeur": profondeur})


def _c7():
    from referentiels.models import Article, Partner

    tiers, articles = Partner.objects.count(), Article.objects.count()
    return Decimal(tiers + articles), tr("%(tiers)s tiers, %(articles)s articles.") % {"tiers": tiers, "articles": articles}


def _c8():
    from django.utils import timezone

    from qualite.models import QualificationSoudeur, Soudeur, WpsWpqr

    wps, qualifs = WpsWpqr.objects.count(), QualificationSoudeur.objects.count()
    expirees = QualificationSoudeur.objects.filter(date_validite__lt=timezone.localdate()).count()
    return Decimal(wps + qualifs), (tr("%(wps)s WPS / WPQR, %(count)s soudeurs, %(qualifs)s qualifications (dont %(expirees)s échues).") % {"wps": wps, "count": Soudeur.objects.count(), "qualifs": qualifs, "expirees": expirees})


def _c9():
    from documents.models import Document

    empreintes = set(LigneReprise.objects.filter(
        lot__gabarit="ged", lot__mode=LotReprise.Mode.REEL, statut="creee").values_list("cle", flat=True))
    docs = Document.objects.filter(sha256__in=empreintes).select_related("current_version")
    nb = docs.count()
    alterees = sum(1 for d in docs if d.current_version is None or d.current_version.sha256 != d.sha256)
    return Decimal(nb), tr("%(nb)s documents repris ; %(alterees)s sans version intègre.") % {"nb": nb, "alterees": alterees}


def rapprochements(sources):
    """`sources` : {"source_c1": "…", …} saisies par les référents. Retourne la liste des contrôles."""
    resultats = []
    calculs = {"C1": _c1, "C2": _c2, "C3": _c3, "C4": _c4, "C5": _c5, "C6": _c6, "C7": _c7, "C8": _c8, "C9": _c9}
    for code, libelle, valideur in CONTROLES:
        if code == "C10":
            taille = get_param_reprise("ECHANTILLON_C10")
            details = []
            for g in GABARITS:
                lot, cles = echantillon(g, taille)
                if lot is not None:
                    details.append(f"{g} ({len(cles)}) : " + ", ".join(cles))
            resultats.append({
                "code": code, "libelle": tr(libelle), "valideur": tr(valideur), "valeur_erp": str(int(taille)),
                "valeur_source": None, "ecart": None, "statut": "a_controler" if details else "a_saisir",
                "detail": " | ".join(details) or "Aucun lot réel chargé.",
            })
            continue
        sortie = _c2(sources.get("source_c2_tiers") or "") if code == "C2" else calculs[code]()
        valeur, detail = sortie[0], sortie[1]
        source = _dec(sources.get(f"source_{code.lower()}"))
        if code == "C4" and source is None:
            source = sortie[2]  # rapprochement interne : stock ↔ comptes de stock
        if code == "C2" and source is None and sortie[3]:
            source = sum(sortie[3].values(), ZERO)  # total source = somme des soldes par tiers saisis
        ecart = None if source is None else valeur - source
        statut = "a_saisir" if source is None else ("conforme" if ecart == 0 else "ecart")
        if code == "C2" and sortie[4]:
            statut = "ecart"  # un total juste peut masquer des écarts entre tiers qui se compensent
        resultats.append({
            "code": code, "libelle": tr(libelle), "valideur": tr(valideur), "valeur_erp": str(valeur),
            "valeur_source": None if source is None else str(source), "ecart": None if ecart is None else str(ecart),
            "statut": statut, "detail": detail,
            **({"tiers": sortie[2]} if code == "C2" else {}),
        })
    return resultats


def synthese_lots():
    """Dernier lot réel par gabarit : taux d'erreur comparé au seuil (plan §6.2)."""
    lignes = []
    for code, g in GABARITS.items():
        lot = LotReprise.objects.filter(gabarit=code, mode=LotReprise.Mode.REEL).exclude(
            statut=LotReprise.Statut.ECHEC).first()
        if lot is None:
            continue
        lignes.append({"gabarit": code, "libelle": g.libelle, "lot": str(lot.pk), "statut": lot.statut,
                       "lignes": lot.lignes, "erreurs": lot.erreurs, "taux_erreur": str(lot.taux_erreur),
                       "seuil": str(lot.seuil_erreur), "le": lot.cree_le.isoformat()})
    return lignes


STATUTS = {"conforme": "Conforme", "ecart": "Écart", "a_saisir": "Valeur source à saisir", "a_controler": "À contrôler"}


def rapprochements_csv(resultats):
    tampon = io.StringIO()
    ecrivain = csv.writer(tampon, delimiter=";")
    ecrivain.writerow([tr("Contrôle"), tr("Libellé"), tr("Valeur ERP"), tr("Valeur source"), tr("Écart"), tr("Statut"), tr("Détail"), tr("Valideur"),
                       tr("Visa")])
    for r in resultats:
        ecrivain.writerow([r["code"], r["libelle"], r["valeur_erp"], r["valeur_source"] or "", r["ecart"] or "",
                           tr(STATUTS[r["statut"]]), r["detail"], r["valideur"], ""])
        for t in r.get("tiers", []):  # C2 : détail par tiers
            ecrivain.writerow([f"{r['code']} / {t['code']}", t["nom"], t["erp"], t["source"] or "", t["ecart"] or "",
                               "", "", "", ""])
    return ("﻿" + tampon.getvalue()).encode("utf-8")
