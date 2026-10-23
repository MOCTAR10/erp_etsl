"""Couche D — écarts de pilotage (CDC Couche D) : cash-flow 13 semaines, pipe → budget, alertes calendaires,
seuils budgétaires planifiés, publication après clôture M11, scellement des marts, purge des archives expirées.

Lecture seule des autres modules (comptabilité, commercial, contrôle de gestion, qualité, maintenance, référentiels) ;
toutes les valeurs attendues d'ETSL sont des `ParametreCube` provisoires modifiables à l'écran.
"""

import calendar
import hashlib
import json
import re
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.db import connection, transaction
from django.db.models import Sum
from django.utils import timezone

from config.echeances import bande
from outbox.models import publish
from users.models import User

from .cubes import get_param_cube
from .models import CubeArchive, ScelleMart
from config.i18n import tr

ZERO = Decimal("0")
HORIZON_JOURS = 90

# ---------------------------------------------------------------------------------------------------------------------
# Publication des données financières après clôture M11
# ---------------------------------------------------------------------------------------------------------------------
# Producteurs des chiffres (préparent la clôture) : voient les mois non clôturés. Les consommateurs (PDG, DGA, SG,
# Direction) ne voient un mois qu'une fois la clôture de gestion M11 réalisée, tant que le blocage est actif.
PRODUCTEURS_FINANCIERS = (User.Role.ADMIN, User.Role.FINANCE, User.Role.COMPTABLE)


def blocage_avant_cloture_actif():
    return int(get_param_cube("BLOCAGE_AVANT_CLOTURE")) != 0


def voit_non_cloture(user):
    if user is None or not blocage_avant_cloture_actif():
        return True
    return bool(user.is_staff or user.is_superuser or user.role in PRODUCTEURS_FINANCIERS)


def periodes_cloturees():
    """Mois (AAAA-MM) dont la clôture de gestion M11 est réalisée."""
    from controle_gestion.models import ClotureGestion

    return {
        d.strftime("%Y-%m")
        for d in ClotureGestion.objects.filter(statut=ClotureGestion.Statut.REALISEE).values_list(
            "period__start_date", flat=True
        )
        if d
    }


# ---------------------------------------------------------------------------------------------------------------------
# Tableau de bord Direction : cash-flow 13 semaines et pipe → budget
# ---------------------------------------------------------------------------------------------------------------------
def cashflow_13_semaines(today=None):
    """Prévision de trésorerie sur 13 semaines glissantes (semaine 1 = semaine en cours, retards inclus).

    Ouverture = soldes initiaux des comptes bancaires actifs + paiements validés (entrées − sorties).
    Encaissements = factures clients émises non lettrées (avoir en moins), à l'échéance ou date + délai paramétré.
    Décaissements = factures fournisseurs comptabilisées non réglées et engagements approuvés non réglés, à la date
    + délai paramétré. Règle provisoire, à confirmer par ETSL.
    """
    from achats.models import PurchaseInvoice
    from comptabilite.models import CompteBancaire, Engagement, FactureClient, LigneLettree, Paiement

    today = today or timezone.localdate()
    lundi = today - timedelta(days=today.weekday())
    delai_enc = int(get_param_cube("TRESO_DELAI_ENCAISSEMENT"))
    delai_dec = int(get_param_cube("TRESO_DELAI_DECAISSEMENT"))

    def semaine(jour):
        i = (jour - lundi).days // 7
        return max(i, 0) if i < 13 else None

    valides = Paiement.objects.filter(statut=Paiement.Statut.VALIDE)
    entrees = valides.filter(sens=Paiement.Sens.ENTREE).aggregate(t=Sum("montant"))["t"] or ZERO
    sorties = valides.filter(sens=Paiement.Sens.SORTIE).aggregate(t=Sum("montant"))["t"] or ZERO
    soldes = CompteBancaire.objects.filter(is_active=True).aggregate(t=Sum("solde_initial"))["t"] or ZERO
    ouverture = soldes + entrees - sorties

    enc = [ZERO] * 13
    dec = [ZERO] * 13
    lettrees = set(
        LigneLettree.objects.values_list("ligne__move_id", flat=True)
    )
    for f in FactureClient.objects.filter(statut=FactureClient.Statut.EMISE):
        if f.move_id and f.move_id in lettrees:
            continue
        i = semaine(f.echeance or (f.date + timedelta(days=delai_enc)))
        if i is not None:
            enc[i] += -f.montant_ttc if f.nature == FactureClient.Nature.AVOIR else f.montant_ttc
    payees = set(valides.filter(facture__isnull=False).values_list("facture_id", flat=True))
    for inv in PurchaseInvoice.objects.filter(
        status__in=(PurchaseInvoice.Status.RAPPROCHEE, PurchaseInvoice.Status.COMPTABILISEE)
    ).annotate(total_lignes=Sum("lines__price_total")):  # pas `total` : propriété du modèle (non affectable)
        if inv.pk in payees:
            continue
        i = semaine(inv.invoice_date + timedelta(days=delai_dec))
        if i is not None:
            dec[i] += inv.total_lignes or ZERO
    regle_eng = dict(
        valides.filter(engagement__isnull=False).values("engagement_id").annotate(t=Sum("montant")).values_list("engagement_id", "t")
    )
    for e in Engagement.objects.filter(statut=Engagement.Statut.APPROUVE):
        reste = e.montant - (regle_eng.get(e.pk) or ZERO)
        if reste <= 0:
            continue
        depart = e.date_engagement or timezone.localdate(e.created_at)
        i = semaine(depart + timedelta(days=delai_dec))
        if i is not None:
            dec[i] += reste

    solde = ouverture
    semaines = []
    for i in range(13):
        debut = lundi + timedelta(weeks=i)
        solde = solde + enc[i] - dec[i]
        semaines.append({
            "semaine": i + 1, "debut": debut.isoformat(), "fin": (debut + timedelta(days=6)).isoformat(),
            "encaissements": f"{enc[i]:.2f}", "decaissements": f"{dec[i]:.2f}",
            "flux_net": f"{enc[i] - dec[i]:.2f}", "solde_fin": f"{solde:.2f}",
        })
    return {
        "ouverture": f"{ouverture:.2f}",
        "semaines": semaines,
        "total_encaissements": f"{sum(enc, ZERO):.2f}",
        "total_decaissements": f"{sum(dec, ZERO):.2f}",
        "solde_final": f"{solde:.2f}",
        "semaines_tension": [s["semaine"] for s in semaines if Decimal(s["solde_fin"]) < 0],
    }


def pipe_vers_budget(annee=None):
    """Couverture du budget de produits de l'exercice : réalisé (grand livre) + pipe pondéré (M1) vs budget (M11)."""
    from accounting_kernel.models import FiscalYear
    from commercial.services import pipe_pondere
    from controle_gestion.models import Budget
    from controle_gestion.services import compute_marges

    annee = annee or timezone.localdate().year
    fy = FiscalYear.objects.filter(year=annee).first()
    budget = ZERO
    realise = ZERO
    if fy:
        budget = Budget.objects.filter(
            fiscal_year=fy, type_budget=Budget.TypeBudget.PRODUIT,
            statut__in=(Budget.Statut.APPROUVE, Budget.Statut.CLOTURE),
        ).aggregate(t=Sum("montant"))["t"] or ZERO
        realise = compute_marges(fy.pk)["totals"]["produits"] or ZERO
    pipe = pipe_pondere()
    pipe_dec = {k: Decimal(str(pipe[k])) for k in ("signe", "en_cours", "prospect", "total")}
    atterrissage = realise + pipe_dec["total"]
    return {
        "annee": annee,
        "budget_produits": f"{budget:.2f}",
        "realise": f"{realise:.2f}",
        "pipe_pondere": {k: f"{v:.2f}" for k, v in pipe_dec.items()},
        "ponderations": pipe.get("ponderations"),
        "atterrissage": f"{atterrissage:.2f}",
        "reste_a_couvrir": f"{budget - atterrissage:.2f}",
        "couverture_pct": f"{(atterrissage * 100 / budget):.1f}" if budget else None,
    }


# ---------------------------------------------------------------------------------------------------------------------
# Alertes calendaires : garantie, agrément fournisseur / matière, audit interne, revue de direction
# ---------------------------------------------------------------------------------------------------------------------
# Défauts seulement : la valeur effective est le paramètre `DEST_*` (cubes.destinataires_famille).
DESTINATAIRES_CALENDAIRES = {
    "garantie": (User.Role.MAINTENANCE, User.Role.DIRECTEUR_OPERATIONS),
    "agrement_fournisseur": (User.Role.QAQC, User.Role.HSE),
    "audit_interne": (User.Role.QAQC,),
    "revue_direction": (User.Role.QAQC, User.Role.PDG, User.Role.DGA),
}


def _ajouter_mois(jour, mois):
    total = jour.month - 1 + mois
    annee, m = jour.year + total // 12, total % 12 + 1
    return jour.replace(year=annee, month=m, day=min(jour.day, calendar.monthrange(annee, m)[1]))


def alertes_calendaires(user=None, today=None):
    """Échéances des 4 familles calendaires du CDC Couche D, à 90 jours (retards de moins de 30 jours inclus)."""
    from users.rbac import can_read_app

    def autorise(app):
        return user is None or can_read_app(user, app)

    today = today or timezone.localdate()
    horizon = today + timedelta(days=HORIZON_JOURS)
    plancher = today - timedelta(days=30)
    items = []

    def ajouter(type_, code, libelle, echeance, statut="active"):
        jours = (echeance - today).days
        items.append({
            "type": type_, "code": code, "libelle": libelle, "date_echeance": echeance,
            "bande": bande(jours), "jours": jours, "statut": "expiree" if jours < 0 else statut,
        })

    if autorise("maintenance"):
        from maintenance.models import Actif

        for a in Actif.objects.filter(garanti_jusqu__gte=plancher, garanti_jusqu__lte=horizon):
            ajouter("garantie", a.code, f"Garantie constructeur — {a.designation}", a.garanti_jusqu)
    if autorise("achats") or autorise("qualite"):
        from referentiels.models import Partner

        for p in Partner.objects.filter(is_active=True, is_global_rental=False):
            for champ, libelle in (("agree_qualite_jusqu", "qualité"), ("agree_hse_jusqu", "HSE")):
                fin = getattr(p, champ)
                if fin and plancher <= fin <= horizon:
                    ajouter("agrement_fournisseur", p.code, f"Agrément {libelle} fournisseur — {p.name}", fin)
    if autorise("qualite"):
        from qualite.models import AuditQualite, RevueDirectionQualite

        for audit in AuditQualite.objects.filter(
            type_audit=AuditQualite.TypeAudit.INTERNE, statut=AuditQualite.Statut.PLANIFIE,
            date_prevue__gte=plancher, date_prevue__lte=horizon,
        ):
            ajouter("audit_interne", audit.code, f"Audit interne — {audit.perimetre}", audit.date_prevue, "planifie")
        brouillon = RevueDirectionQualite.objects.filter(
            statut=RevueDirectionQualite.Statut.BROUILLON, date_revue__gte=plancher
        ).order_by("date_revue").first()
        if brouillon:
            prochaine, code = brouillon.date_revue, brouillon.code
        else:
            derniere = RevueDirectionQualite.objects.filter(
                statut=RevueDirectionQualite.Statut.VALIDEE
            ).order_by("-date_revue").first()
            mois = int(get_param_cube("REVUE_DIRECTION_MOIS"))
            prochaine = _ajouter_mois(derniere.date_revue, mois) if derniere else today.replace(month=12, day=31)
            code = "REVUE-DIRECTION"
        if plancher <= prochaine <= horizon:
            ajouter("revue_direction", code, "Revue de direction (système qualité)", prochaine, "planifiee")
    return sorted(items, key=lambda i: i["date_echeance"])


def paliers_notification():
    """Paliers J-n notifiés : paramètre central commun à tous les modules (J-90 / 60 / 30 / 15 / 0 par défaut)."""
    from config.echeances import paliers

    return set(paliers())


# ---------------------------------------------------------------------------------------------------------------------
# Seuils budgétaires 90 / 100 / 110 % contrôlés chaque jour (tâche existante `alimenter_cubes`)
# ---------------------------------------------------------------------------------------------------------------------
DESTINATAIRES_BUDGET = (User.Role.FINANCE, User.Role.PDG, User.Role.DGA)


def seuils_budgetaires():
    """Consommation des budgets de charges approuvés et seuil franchi (alerte / atteint / dépassé)."""
    from controle_gestion.models import Budget
    from controle_gestion.services import compute_variance

    seuils = [
        ("depasse", get_param_cube("BUDGET_SEUIL_DEPASSE")),
        ("atteint", get_param_cube("BUDGET_SEUIL_ATTEINT")),
        ("alerte", get_param_cube("BUDGET_SEUIL_ALERTE")),
    ]
    lignes = []
    for b in Budget.objects.filter(statut=Budget.Statut.APPROUVE, type_budget=Budget.TypeBudget.CHARGE).order_by("code"):
        tot = compute_variance(b)["totals"]
        if not tot["montant"]:
            continue
        taux = (tot["realise"] * 100 / tot["montant"]).quantize(Decimal("0.1"))
        niveau, seuil = next(((n, s) for n, s in seuils if taux >= s), (None, None))
        lignes.append({
            "budget": b.code, "libelle": b.label, "montant": f"{tot['montant']:.2f}", "realise": f"{tot['realise']:.2f}",
            "taux_pct": f"{taux}", "niveau": niveau, "seuil_pct": f"{seuil:.0f}" if seuil is not None else None,
        })
    return lignes


def controler_seuils_budgetaires():
    """Notifie (interne + e-mail) une fois par budget et par seuil franchi ; au-delà du seuil de dépassement, une
    analyse d'écart est exigée."""
    from workflow.models import Notification
    from workflow.notifications import notify

    destinataires = list(User.objects.filter(role__in=DESTINATAIRES_BUDGET, is_active=True))
    envoyees = 0
    for ligne in seuils_budgetaires():
        if not ligne["niveau"]:
            continue
        sujet = f"Budget {ligne['budget']} : seuil {ligne['seuil_pct']} % franchi ({ligne['taux_pct']} %)"
        prefixe = f"Budget {ligne['budget']} : seuil {ligne['seuil_pct']} % franchi"
        message = f"Le budget « {ligne['libelle']} » est consommé à {ligne['taux_pct']} %."
        if ligne["niveau"] == "depasse":
            message += " Dépassement : une analyse d'écart est obligatoire avant toute nouvelle dépense."
        for user in destinataires:
            if Notification.objects.filter(user=user, subject__startswith=prefixe).exists():
                continue
            notify(user, sujet[:255], message, kind="reminder")
            envoyees += 1
    return envoyees


# ---------------------------------------------------------------------------------------------------------------------
# Scellement des marts dbt (empreinte SHA-256 par exécution) et purge des archives expirées
# ---------------------------------------------------------------------------------------------------------------------
DBT_MODELS = Path(__file__).resolve().parents[2] / "dbt" / "models"
# Date d'exécution recalculée à chaque passage : exclue de l'empreinte (sinon une version par jour).
COLONNES_VOLATILES = {"as_of_date", "rafraichi_le"}
MARTS_FINANCIERS = {"dm_couts_m10", "dm_marges_m11", "dm_pipe_affaires"}
_SOURCE = re.compile(r'\{\{\s*source\(\s*["\']etls_replica["\']\s*,\s*["\'](\w+)["\']\s*\)\s*\}\}')
_REF = re.compile(r'\{\{\s*ref\(\s*["\'](\w+)["\']\s*\)\s*\}\}')


def _sans_commentaires(sql):
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
    return "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--")).strip().rstrip(";")


def _modele(nom, dossier):
    for sous in ("staging", "marts"):
        f = dossier / sous / f"{nom}.sql"
        if f.exists():
            return _sans_commentaires(_SOURCE.sub(r"\1", f.read_text(encoding="utf-8")))
    raise FileNotFoundError(tr("Modèle dbt introuvable : %(nom)s") % {"nom": nom})


def rendre_sql_mart(nom, dossier=None):
    """SQL exécutable d'un mart dbt : sources → tables de la base, `ref()` (staging ou mart) → CTE, dépendances
    d'abord (équivalent de `dbt compile` pour un modèle et ses ancêtres)."""
    dossier = dossier or DBT_MODELS
    ordre, vus = [], set()

    def visiter(n):
        if n in vus:
            return
        vus.add(n)
        sql = _modele(n, dossier)
        for r in dict.fromkeys(_REF.findall(sql)):
            visiter(r)
        ordre.append((n, _REF.sub(r"\1", sql)))

    visiter(nom)
    *deps, (_, sql) = ordre
    if not deps:
        return sql
    ctes = ", ".join(f"{n} as ({s})" for n, s in deps)
    if sql[:5].lower() == "with ":
        return f"with {ctes}, {sql[5:]}"
    return f"with {ctes} {sql}"


def marts_disponibles(dossier=None):
    dossier = dossier or DBT_MODELS
    return sorted(p.stem for p in (dossier / "marts").glob("dm_*.sql")) if (dossier / "marts").is_dir() else []


def _lire_mart(nom):
    """Lignes du mart : table `marts.<nom>` si présente (réplica alimenté par dbt), sinon SQL rendu."""
    with connection.cursor() as cur:
        cur.execute("select to_regclass(%s)", [f"marts.{nom}"])
        if cur.fetchone()[0]:
            cur.execute(f'select * from marts."{nom}"')
            source = "table_mart"
        else:
            cur.execute(rendre_sql_mart(nom))
            source = "sql_rendu"
        noms = [c[0] for c in cur.description]
        garder = [i for i, c in enumerate(noms) if c not in COLONNES_VOLATILES]
        colonnes = [noms[i] for i in garder]
        lignes = [[None if row[i] is None else str(row[i]) for i in garder] for row in cur.fetchall()]
    return colonnes, sorted(lignes, key=lambda r: json.dumps(r)), source


def _empreinte(colonnes, lignes):
    contenu = json.dumps({"colonnes": colonnes, "lignes": lignes}, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(contenu.encode("utf-8")).hexdigest()


def verifier_scelle(scelle):
    return _empreinte(scelle.colonnes, scelle.lignes) == scelle.sha256


def sceller_marts(user=None, noms=None, today=None):
    """Fige chaque mart (contenu + SHA-256), conservé 10 ans (financier) ou 5 ans (opérationnel), immuable."""
    from .cubes import _ajouter_annees

    today = today or timezone.localdate()
    resultats = []
    for nom in noms or marts_disponibles():
        try:
            with transaction.atomic():
                colonnes, lignes, source = _lire_mart(nom)
        except Exception as exc:  # mart non exécutable sur cette base : signalé, jamais scellé à vide
            resultats.append({"mart": nom, "erreur": str(exc).splitlines()[0][:200]})
            continue
        sha = _empreinte(colonnes, lignes)
        dernier = ScelleMart.objects.filter(mart=nom).order_by("-created_at").first()
        if dernier and dernier.sha256 == sha:
            resultats.append({"mart": nom, "sha256": sha, "nb_lignes": len(lignes), "inchange": True})
            continue  # version déjà scellée : pas de doublon
        financier = nom in MARTS_FINANCIERS
        annees = int(get_param_cube("RETENTION_ANS" if financier else "RETENTION_SCELLE_ANS"))
        scelle = ScelleMart.objects.create(
            mart=nom, type_donnees="financier" if financier else "operationnel", source=source,
            colonnes=colonnes, lignes=lignes, nb_lignes=len(lignes), sha256=sha,
            conserve_jusqu_au=_ajouter_annees(today, annees), created_by=user,
        )
        resultats.append({"mart": nom, "sha256": scelle.sha256, "nb_lignes": scelle.nb_lignes})
    nouveaux = [r["mart"] for r in resultats if "sha256" in r and not r.get("inchange")]
    if nouveaux:
        publish("analytics.marts.scelles", {"marts": nouveaux})
    return resultats


def purger_archives_expirees(today=None):
    """Supprime les archives de cubes et scellés de marts dont la durée de conservation est échue (trace outbox)."""
    today = today or timezone.localdate()
    cubes_qs = CubeArchive.objects.filter(conserve_jusqu_au__lt=today)
    scelles_qs = ScelleMart.objects.filter(conserve_jusqu_au__lt=today)
    periodes = list(cubes_qs.values_list("periode", flat=True))
    nb_scelles = scelles_qs.count()
    if periodes or nb_scelles:
        # Suppression en masse (QuerySet) : `delete()` du modèle reste interdit avant la fin de conservation.
        cubes_qs.delete()
        scelles_qs.delete()
        publish("analytics.archives.purgees", {"cubes": periodes, "scelles": nb_scelles, "date": str(today)})
    return {"cubes": periodes, "scelles": nb_scelles}


def etat_retention():
    """Synthèse de conservation par type de données (écran Direction)."""
    par_type = defaultdict(int)
    for t in ScelleMart.objects.values_list("type_donnees", flat=True):
        par_type[t] += 1
    return {
        "cubes": CubeArchive.objects.count(),
        "scelles": dict(par_type),
        "retention_financier_ans": str(get_param_cube("RETENTION_ANS")),
        "retention_operationnel_ans": str(get_param_cube("RETENTION_SCELLE_ANS")),
    }
