"""Écarts M1 (matrice de recette) : scoring 360° et signaux faibles, alertes du funnel, structure de chiffrage et
dérive, échéances J-90 / J-60 / J-30, pipe par profil, calculs des profils contractuels (retenue, pénalités,
indexation, durées), échéanciers types, RAO / RC archivés en GED, besoins d'achat de l'affaire, plan de charge et
habilitations par contrat, indicateurs commerciaux.

Toute valeur qu'ETSL doit fixer est un `ParametreCommercial` provisoire, modifiable à l'écran puis confirmé.
"""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

ZERO = Decimal("0")
CENT = Decimal("100")

PARAMETRES_DEFAUT = {
    # Scoring client 360° (pondérations des 4 composantes, en points).
    "SCORE_POIDS_CA": ("Scoring : poids du chiffre d'affaires gagné", Decimal("30"), "pts"),
    "SCORE_POIDS_CONVERSION": ("Scoring : poids du taux de transformation", Decimal("25"), "pts"),
    "SCORE_POIDS_MARGE": ("Scoring : poids de la marge des affaires", Decimal("25"), "pts"),
    "SCORE_POIDS_RECENCE": ("Scoring : poids de la récence du contact", Decimal("20"), "pts"),
    "SCORE_MARGE_REFERENCE_PCT": ("Scoring : taux de marge donnant la note maximale", Decimal("20"), "%"),
    "SCORE_SEUIL_ALERTE": ("Signal faible : score client en dessous duquel alerter", Decimal("40"), "pts"),
    "CLIENT_RELANCE_JOURS": ("Relance client : jours sans contact avant relance", Decimal("30"), "jours"),
    "CLIENT_INACTIF_JOURS": ("Signal faible : jours sans contact = client inactif", Decimal("90"), "jours"),
    "OPP_INACTIVITE_JOURS": ("Funnel : jours sans mouvement d'une opportunité avant alerte", Decimal("21"), "jours"),
    # Chiffrage.
    "CHIFFRAGE_FRAIS_INDIRECTS_PCT": ("Chiffrage : frais indirects (% du déboursé sec)", Decimal("12"), "%"),
    "CHIFFRAGE_ALEAS_PCT": ("Chiffrage : aléas (% du déboursé sec)", Decimal("5"), "%"),
    "CHIFFRAGE_MARGE_CIBLE_PCT": ("Chiffrage : marge cible (% du prix de revient)", Decimal("15"), "%"),
    "CHIFFRAGE_DERIVE_SEUIL_PCT": ("Dérive : écart coût réel / prévu déclenchant l'alerte", Decimal("10"), "%"),
    # Échéances : paliers communs à tous les modules (`config.echeances.paliers`, paramètre central).
    # Revue d'appel d'offres (Go / No-Go).
    "RAO_SEUIL_GO": ("RAO : note pondérée minimale pour un Go", Decimal("75"), "%"),
    "RAO_SEUIL_RESERVE": ("RAO : note pondérée minimale pour un Go sous réserve", Decimal("50"), "%"),
    # Profils contractuels.
    "RETENUE_GARANTIE_PCT": ("Marché de travaux : taux de retenue de garantie par défaut", Decimal("5"), "%"),
    "GARANTIE_DUREE_MOIS": ("Retenue de garantie : délai de libération après fin de contrat", Decimal("12"), "mois"),
    "PENALITE_JOUR_POUR_MILLE": ("Pénalités de retard : taux journalier", Decimal("1"), "‰ / jour"),
    "PENALITE_PLAFOND_PCT": ("Pénalités de retard : plafond (% du montant)", Decimal("10"), "%"),
    "INDEXATION_PART_FIXE": ("Indexation P = P0 × (a + (1 − a) × I / I0) : part fixe a", Decimal("0.15"), ""),
    "DUREE_TRAVAUX_MIN": ("Durée d'un marché de travaux : minimum", Decimal("18"), "mois"),
    "DUREE_TRAVAUX_MAX": ("Durée d'un marché de travaux : maximum", Decimal("36"), "mois"),
    "DUREE_MAINTENANCE_MIN": ("Durée d'un contrat de maintenance : minimum", Decimal("24"), "mois"),
    "DUREE_MAINTENANCE_MAX": ("Durée d'un contrat de maintenance : maximum", Decimal("60"), "mois"),
    "DUREE_HORS_FOURCHETTE_BLOQUANT": ("Durée hors fourchette : 1 = bloquer, 0 = avertir", Decimal("0"), "0/1"),
}

# Formulaire RAO ENG-PR1-01 : critères provisoires (modèle officiel non fourni par ETSL).
CRITERES_RAO_DEFAUT = [
    {"libelle": "Adéquation technique (savoir-faire, références)", "poids": 25},
    {"libelle": "Capacité et plan de charge (équipes, moyens)", "poids": 20},
    {"libelle": "Rentabilité attendue (marge, conditions de paiement)", "poids": 20},
    {"libelle": "Risques techniques, contractuels et HSE", "poids": 15},
    {"libelle": "Délais et faisabilité du planning", "poids": 10},
    {"libelle": "Intérêt stratégique / relation client", "poids": 10},
]

# Définition provisoire du « BS » (CDC M1 : affaires, jalons, OF, BS).
DEFINITION_BS = "BS = bon de sortie magasin (M5) consommé par un OF de l'affaire — définition provisoire, à confirmer par ETSL."

NATURES_ACHAT = ("fourniture", "sous_traitance", "equipement")

# Ces valeurs sont des DÉFAUTS : la valeur effective est un `ParametreCommercial` (champ `texte`, + `valeur` = poids
# pour un critère RAO), modifiable à l'écran et confirmé par la Direction.
TEXTES_DEFAUT = {
    **{f"RAO_CRITERE_{i}": c["libelle"] for i, c in enumerate(CRITERES_RAO_DEFAUT, start=1)},
    "DEFINITION_BS": DEFINITION_BS,
    "DEFINITION_PRIX_MOYEN": "Moyenne du montant des offres gagnées (option retenue) — définition provisoire.",
    "NOTE_MODELE_PDF": "Modèle provisoire généré par l'ERP — à confirmer ou remplacer par le modèle officiel ETSL.",
}
for _i, _c in enumerate(CRITERES_RAO_DEFAUT, start=1):
    PARAMETRES_DEFAUT[f"RAO_CRITERE_{_i}"] = (
        f"RAO ENG-PR1-01 : critère {_i} (libellé en texte, poids en valeur ; poids 0 = critère retiré)",
        Decimal(_c["poids"]), "pts",
    )
PARAMETRES_DEFAUT["DEFINITION_BS"] = ("Définition du « BS » (affaires, jalons, OF, BS)", ZERO, "texte")
PARAMETRES_DEFAUT["DEFINITION_PRIX_MOYEN"] = ("Reporting : définition du prix moyen des offres", ZERO, "texte")
PARAMETRES_DEFAUT["NOTE_MODELE_PDF"] = ("Mention portée sur les PDF RAO / RC (modèle provisoire)", ZERO, "texte")
CODES_TEXTE_SEUL = ("DEFINITION_BS", "DEFINITION_PRIX_MOYEN", "NOTE_MODELE_PDF")
CODES_CRITERES_RAO = tuple(f"RAO_CRITERE_{i}" for i in range(1, len(CRITERES_RAO_DEFAUT) + 1))


# --------------------------------------------------------------------------------------------- paramètres
def get_param(code):
    from .models import ParametreCommercial

    return _param_obj(code).valeur


def _param_obj(code):
    from .models import ParametreCommercial

    label, valeur, unite = PARAMETRES_DEFAUT[code]
    defaults = {"label": label, "valeur": valeur, "unite": unite, "texte": TEXTES_DEFAUT.get(code, "")}
    return ParametreCommercial.objects.get_or_create(code=code, defaults=defaults)[0]


def get_texte(code):
    """Valeur texte d'un paramètre (définition, libellé de critère) ; le défaut si ETSL l'a vidée."""
    return _param_obj(code).texte or TEXTES_DEFAUT.get(code, "")


def criteres_rao():
    """Critères du formulaire RAO ENG-PR1-01 : paramètres `RAO_CRITERE_n` (poids 0 = critère retiré)."""
    sortie = []
    for code in CODES_CRITERES_RAO:
        p = _param_obj(code)
        if p.valeur > 0:
            poids = int(p.valeur) if p.valeur == p.valeur.to_integral_value() else float(p.valeur)
            sortie.append({"libelle": p.texte or TEXTES_DEFAUT[code], "poids": poids})
    return sortie


def assurer_parametres():
    from .models import ParametreCommercial

    existants = set(ParametreCommercial.objects.values_list("code", flat=True))
    for code in PARAMETRES_DEFAUT:
        if code not in existants:
            get_param(code)


def provisoires(codes):
    from .models import ParametreCommercial

    for code in codes:
        get_param(code)
    return ParametreCommercial.objects.filter(code__in=codes).exclude(statut_valeur="confirme").exists()


def _s(valeur, voir=True):
    if valeur is None or not voir:
        return None
    return str(Decimal(valeur).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def ajouter_mois(d, mois):
    annee, m = divmod(d.month - 1 + int(mois), 12)
    annee += d.year
    m += 1
    jours = [31, 29 if annee % 4 == 0 and (annee % 100 != 0 or annee % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return date(annee, m, min(d.day, jours[m - 1]))


# --------------------------------------------------------------------------------------------- scoring 360°
def _ca_gagne_par_client():
    from .models import Opportunity

    lignes = (
        Opportunity.objects.filter(is_active=True, stage=Opportunity.Stage.GAGNE, client__isnull=False)
        .values("client_id").annotate(t=Sum("amount"))
    )
    return {r["client_id"]: r["t"] or ZERO for r in lignes}


def score_client(client, today=None, ca_par_client=None):
    """Score pondéré 0-100 : CA gagné (relatif au meilleur client), taux de transformation, marge, récence."""
    from .models import Affaire, Opportunity

    today = today or timezone.localdate()
    ca_par_client = ca_par_client if ca_par_client is not None else _ca_gagne_par_client()
    ca_max = max(ca_par_client.values(), default=ZERO)
    ca = ca_par_client.get(client.pk, ZERO)
    s_ca = (ca / ca_max * CENT) if ca_max else ZERO

    opps = Opportunity.objects.filter(client=client, is_active=True)
    gagnees = opps.filter(stage=Opportunity.Stage.GAGNE).count()
    perdues = opps.filter(stage=Opportunity.Stage.PERDU).count()
    s_conv = Decimal(gagnees * 100) / (gagnees + perdues) if gagnees + perdues else Decimal("50")

    aff = Affaire.objects.filter(client=client).exclude(status=Affaire.Status.ARCHIVEE).aggregate(
        m=Sum("margin"), ca=Sum("contract_amount")
    )
    reference = get_param("SCORE_MARGE_REFERENCE_PCT") or Decimal("1")
    if aff["ca"]:
        taux = (aff["m"] or ZERO) / aff["ca"] * CENT
        s_marge = max(ZERO, min(CENT, taux / reference * CENT))
    else:
        s_marge = Decimal("50")

    relance, inactif = get_param("CLIENT_RELANCE_JOURS"), get_param("CLIENT_INACTIF_JOURS")
    if client.last_contact is None:
        s_rec, jours = ZERO, None
    else:
        jours = (today - client.last_contact).days
        if jours <= relance:
            s_rec = CENT
        elif jours >= inactif:
            s_rec = ZERO
        else:
            s_rec = CENT * (inactif - jours) / (inactif - relance)

    poids = {
        "ca": get_param("SCORE_POIDS_CA"), "conversion": get_param("SCORE_POIDS_CONVERSION"),
        "marge": get_param("SCORE_POIDS_MARGE"), "recence": get_param("SCORE_POIDS_RECENCE"),
    }
    notes = {"ca": s_ca, "conversion": s_conv, "marge": s_marge, "recence": s_rec}
    total_poids = sum(poids.values()) or Decimal("1")
    score = int((sum(poids[k] * notes[k] for k in poids) / total_poids).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return {
        "score": max(0, min(100, score)),
        "composantes": [
            {"critere": k, "poids": _s(poids[k]), "note": _s(notes[k])} for k in ("ca", "conversion", "marge", "recence")
        ],
        "jours_sans_contact": jours,
        "gagnees": gagnees,
        "perdues": perdues,
    }


def signaux_client(client, score=None, today=None):
    """Signaux faibles : client inactif, relance due, deux offres perdues d'affilée, score bas, contrat à échéance."""
    from .models import Contract, Estimate

    today = today or timezone.localdate()
    signaux = []
    inactif, relance = get_param("CLIENT_INACTIF_JOURS"), get_param("CLIENT_RELANCE_JOURS")
    jours = (today - client.last_contact).days if client.last_contact else None
    if jours is None or jours > inactif:
        signaux.append({"code": "inactif", "libelle": "Aucun contact depuis plus de %d jours" % int(inactif)})
    if (client.next_contact and client.next_contact <= today) or (
        not client.next_contact and jours is not None and relance <= jours <= inactif
    ):
        signaux.append({"code": "relance", "libelle": "Relance client à faire"})
    decisions = list(
        Estimate.objects.filter(client=client, status__in=[Estimate.Status.GAGNEE, Estimate.Status.PERDUE])
        .order_by("-decision_le", "-created_at").values_list("status", flat=True)[:2]
    )
    if len(decisions) == 2 and all(s == Estimate.Status.PERDUE for s in decisions):
        signaux.append({"code": "pertes", "libelle": "Deux dernières offres perdues"})
    if score is not None and score < get_param("SCORE_SEUIL_ALERTE"):
        signaux.append({"code": "score_bas", "libelle": "Score client sous le seuil d'alerte"})
    horizon = today + timedelta(days=max(paliers(), default=0))
    if Contract.objects.filter(client=client, status=Contract.Status.ACTIF, end_date__isnull=False,
                               end_date__lte=horizon).exists():
        signaux.append({"code": "contrat_echeance", "libelle": "Contrat arrivant à échéance (renouvellement)"})
    return signaux


def recalculer_scores():
    from .models import ClientProfile

    ca = _ca_gagne_par_client()
    modifies = 0
    for client in ClientProfile.objects.filter(is_active=True):
        score = score_client(client, ca_par_client=ca)["score"]
        if client.scoring != score:
            ClientProfile.objects.filter(pk=client.pk).update(scoring=score)
            modifies += 1
    return modifies


def clients_signaux():
    from .models import ClientProfile

    ca = _ca_gagne_par_client()
    lignes = []
    for client in ClientProfile.objects.filter(is_active=True).select_related("partner"):
        detail = score_client(client, ca_par_client=ca)
        lignes.append({
            "id": str(client.pk), "client": client.partner.name, "segment": client.get_segment_display(),
            "score_enregistre": client.scoring, "score_calcule": detail["score"],
            "dernier_contact": client.last_contact, "prochain_contact": client.next_contact,
            "signaux": signaux_client(client, detail["score"]),
        })
    return sorted(lignes, key=lambda x: (-len(x["signaux"]), x["client"]))


def vue_360(client, voir):
    from .models import Affaire, Contract, Estimate, Opportunity

    detail = score_client(client)
    return {
        "id": str(client.pk), "client": client.partner.name, "segment": client.get_segment_display(),
        "contacts": client.contacts, "historique": client.history,
        "dernier_contact": client.last_contact, "prochain_contact": client.next_contact,
        "scoring": detail, "signaux": signaux_client(client, detail["score"]),
        "opportunites": [
            {"code": o.code, "objet": o.subject, "etape": o.get_stage_display(), "montant": _s(o.amount, voir)}
            for o in Opportunity.objects.filter(client=client)[:50]
        ],
        "offres": [
            {"code": e.code, "version": e.version, "titre": e.title, "statut": e.get_status_display(),
             "montant": _s(e.montant_offre, voir)}
            for e in Estimate.objects.filter(client=client).prefetch_related("options", "lines")[:50]
        ],
        "affaires": [
            {"code": a.code, "titre": a.title, "statut": a.get_status_display(), "montant": _s(a.contract_amount, voir)}
            for a in Affaire.objects.filter(client=client)[:50]
        ],
        "contrats": [
            {"code": c.code, "profil": c.get_profile_display(), "statut": c.get_status_display(), "fin": c.end_date}
            for c in Contract.objects.filter(client=client)[:50]
        ],
    }


# --------------------------------------------------------------------------------------------- funnel
def alertes_opportunites(today=None):
    from .models import Opportunity

    today = today or timezone.localdate()
    jours = int(get_param("OPP_INACTIVITE_JOURS"))
    limite = timezone.now() - timedelta(days=jours)
    lignes = []
    ouvertes = Opportunity.objects.filter(is_active=True).exclude(
        stage__in=[Opportunity.Stage.GAGNE, Opportunity.Stage.PERDU]
    ).select_related("client__partner", "owner")
    for o in ouvertes:
        motifs = []
        if o.updated_at < limite:
            motifs.append(f"Sans mouvement depuis {(timezone.now() - o.updated_at).days} jours")
        if o.expected_close and o.expected_close < today:
            motifs.append("Date de clôture prévue dépassée")
        if motifs:
            lignes.append({
                "id": str(o.pk), "code": o.code, "objet": o.subject, "etape": o.get_stage_display(),
                "client": o.client.partner.name if o.client_id else None,
                "responsable": o.owner.email if o.owner_id else None, "motifs": motifs, "owner_id": o.owner_id,
            })
    return lignes


ETAPES_ORDRE = ["prospection", "qualification", "offre", "negociation", "gagne", "perdu"]


def changer_etape(opportunite, etape, motif=""):
    from .models import Opportunity

    if etape not in ETAPES_ORDRE:
        raise ValidationError({"stage": "Étape inconnue."})
    if opportunite.stage in (Opportunity.Stage.GAGNE, Opportunity.Stage.PERDU):
        raise ValidationError({"detail": "Opportunité close (gagnée / perdue) : étape figée."})
    if etape == opportunite.stage:
        raise ValidationError({"stage": "L'opportunité est déjà à cette étape."})
    opportunite.stage = etape
    if etape == Opportunity.Stage.PERDU:
        opportunite.lost_reason = (motif or "Non précisé")[:200]
    opportunite.save()
    return opportunite


# --------------------------------------------------------------------------------------------- pipe par profil
def profil_opportunite(o):
    if o.profil_contractuel:
        return o.profil_contractuel
    for affaire in o.affaires.all():
        if affaire.is_global_rental:
            return "global_rental"
        for contrat in affaire.contracts.all():
            return contrat.profile
    return "non_renseigne"


def pipe_par_profil(voir):
    from .models import PROFILS_PIPE, Opportunity
    from .services import PIPE_CATEGORIES, ponderations_pipe

    poids = ponderations_pipe()
    poids_etape = {e: Decimal(str(poids[c])) for c, etapes in PIPE_CATEGORIES.items() for e in etapes}
    libelles = dict(PROFILS_PIPE) | {"non_renseigne": "Non renseigné"}
    groupes = {}
    for o in Opportunity.objects.filter(is_active=True).prefetch_related("affaires__contracts"):
        cle = profil_opportunite(o)
        g = groupes.setdefault(cle, {"profil": cle, "libelle": libelles.get(cle, cle), "nombre": 0, "montant": ZERO,
                                     "pondere": ZERO, "gagnees": 0, "perdues": 0})
        g["nombre"] += 1
        g["montant"] += o.amount or ZERO
        g["pondere"] += (o.amount or ZERO) * poids_etape.get(o.stage, ZERO)
        g["gagnees"] += o.stage == Opportunity.Stage.GAGNE
        g["perdues"] += o.stage == Opportunity.Stage.PERDU
    lignes = []
    for g in sorted(groupes.values(), key=lambda x: x["profil"]):
        closes = g["gagnees"] + g["perdues"]
        g["conversion_pct"] = _s(Decimal(g["gagnees"] * 100) / closes) if closes else None
        g["montant"], g["pondere"] = _s(g["montant"], voir), _s(g["pondere"], voir)
        lignes.append(g)
    return lignes


# --------------------------------------------------------------------------------------------- chiffrage & dérive
def taux_offre(estimate):
    return {
        "frais_indirects": estimate.taux_frais_indirects if estimate.taux_frais_indirects is not None
        else get_param("CHIFFRAGE_FRAIS_INDIRECTS_PCT"),
        "aleas": estimate.taux_aleas if estimate.taux_aleas is not None else get_param("CHIFFRAGE_ALEAS_PCT"),
        "marge": estimate.taux_marge_cible if estimate.taux_marge_cible is not None
        else get_param("CHIFFRAGE_MARGE_CIBLE_PCT"),
    }


def structure_chiffrage(estimate, voir=True):
    """Déboursé sec (Σ qté × coût, par nature et par lot) + frais indirects + aléas = prix de revient ;
    prix de vente cible = PR × (1 + marge cible) ; comparé au prix de l'offre."""
    from .models import NATURES_COUT

    lignes = list(estimate.lines.all())
    par_nature, par_lot = {}, {}
    ds = ZERO
    for ligne in lignes:
        cout = (ligne.quantity or ZERO) * (ligne.cout_unitaire or ZERO)
        ds += cout
        par_nature[ligne.nature] = par_nature.get(ligne.nature, ZERO) + cout
        lot = ligne.lot or "—"
        par_lot[lot] = par_lot.get(lot, ZERO) + cout
    taux = taux_offre(estimate)
    fi, al = ds * taux["frais_indirects"] / CENT, ds * taux["aleas"] / CENT
    pr = ds + fi + al
    pv = pr * (1 + taux["marge"] / CENT)
    prix_offre = estimate.montant_offre or ZERO
    marge_offre = prix_offre - pr if pr else None
    libelles = dict(NATURES_COUT)
    return {
        "offre": estimate.code, "version": estimate.version, "lignes": len(lignes),
        "taux": {k: _s(v) for k, v in taux.items()},
        "taux_provisoires": provisoires(("CHIFFRAGE_FRAIS_INDIRECTS_PCT", "CHIFFRAGE_ALEAS_PCT", "CHIFFRAGE_MARGE_CIBLE_PCT")),
        "par_nature": [{"nature": k, "libelle": libelles.get(k, k), "montant": _s(v, voir)} for k, v in par_nature.items()],
        "par_lot": [{"lot": k, "montant": _s(v, voir)} for k, v in sorted(par_lot.items())],
        "debourse_sec": _s(ds, voir), "frais_indirects": _s(fi, voir), "aleas": _s(al, voir),
        "prix_revient": _s(pr, voir), "prix_vente_cible": _s(pv, voir), "prix_offre": _s(prix_offre, voir),
        "marge_offre": _s(marge_offre, voir),
        "taux_marge_offre_pct": _s(marge_offre / pr * CENT) if (marge_offre is not None and pr) else None,
        "sous_marge_cible": bool(pr and prix_offre < pv),
    }


def offre_retenue(affaire):
    from .models import Estimate

    if not affaire.opportunity_id:
        return None
    return (Estimate.objects.filter(opportunity_id=affaire.opportunity_id, status=Estimate.Status.GAGNEE)
            .order_by("-version", "-created_at").first())


def _couts_reels(analytic_ids):
    from django.db.models import Case, DecimalField, F, Value, When

    from accounting_kernel.models import AccountMove, AccountMoveLine
    from referentiels.models import Account

    lignes = (
        AccountMoveLine.objects.filter(analytic_account_id__in=analytic_ids,
                                       move__status__in=[AccountMove.Status.POSTED, AccountMove.Status.REVERSED])
        .values("analytic_account_id")
        .annotate(charges=Sum(Case(When(account__account_type=Account.AccountType.EXPENSE, then=F("debit") - F("credit")),
                                   default=Value(ZERO), output_field=DecimalField())))
    )
    return {r["analytic_account_id"]: r["charges"] or ZERO for r in lignes}


def derives_affaires(voir, affaires=None):
    """Coût réel (charges du grand livre sur le compte analytique, 618 inclus) vs coût prévu à l'avancement."""
    from .models import Affaire

    if affaires is None:
        affaires = list(Affaire.objects.filter(status__in=[Affaire.Status.CONFIRMEE, Affaire.Status.EN_COURS,
                                                           Affaire.Status.CLOTUREE])
                        .select_related("client__partner").prefetch_related("milestones"))
    seuil = get_param("CHIFFRAGE_DERIVE_SEUIL_PCT")
    reels = _couts_reels([a.analytic_id for a in affaires if a.analytic_id])
    lignes = []
    for a in affaires:
        offre = offre_retenue(a)
        prevu, source = None, None
        if offre is not None:
            pr = sum(((ligne.quantity or ZERO) * (ligne.cout_unitaire or ZERO) for ligne in offre.lines.all()), ZERO)
            if pr:
                t = taux_offre(offre)
                prevu, source = pr * (1 + (t["frais_indirects"] + t["aleas"]) / CENT), f"offre {offre.code} v{offre.version}"
        if prevu is None and a.contract_amount:
            prevu, source = (a.contract_amount or ZERO) - (a.margin or ZERO), "montant contractuel − marge prévue"
        jalons = list(a.milestones.all())
        avancement = (sum(Decimal(j.progress) for j in jalons) / len(jalons)) if jalons else CENT
        if a.status == Affaire.Status.CLOTUREE:
            avancement = CENT
        reel = reels.get(a.analytic_id, ZERO)
        prevu_date = prevu * avancement / CENT if prevu else None
        derive = ((reel - prevu_date) / prevu_date * CENT) if prevu_date else None
        lignes.append({
            "id": str(a.pk), "code": a.code, "titre": a.title, "statut": a.get_status_display(),
            "source_prevision": source, "avancement_pct": _s(avancement), "cout_prevu": _s(prevu, voir),
            "cout_prevu_a_date": _s(prevu_date, voir), "cout_reel": _s(reel, voir),
            "derive_pct": _s(derive) if voir else None, "alerte": bool(derive is not None and derive > seuil),
            "responsable_id": a.responsable_id,
        })
    return {"seuil_pct": _s(seuil), "provisoire": provisoires(("CHIFFRAGE_DERIVE_SEUIL_PCT",)), "lignes": lignes}


# --------------------------------------------------------------------------------------------- échéances
def paliers():
    """Paliers communs (paramètre central `paliers_notification`, cf. `config.echeances`)."""
    from config.echeances import paliers as paliers_communs

    return list(paliers_communs())


def palier_de(jours, liste):
    if jours < 0:
        return "depassee"
    for p in sorted(liste):
        if jours <= p:
            return f"j{p}"
    return None


def echeances_m1(today=None):
    """Offres soumises (validité), contrats en vigueur (fin), avenants non signés (avant la fin du contrat)."""
    from .models import Avenant, Contract, Estimate

    today = today or timezone.localdate()
    liste = paliers()
    horizon = today + timedelta(days=max(liste))
    items = []

    def ajout(type_, obj, code, libelle, echeance, destinataire_id):
        jours = (echeance - today).days
        items.append({"type": type_, "id": str(obj.pk), "code": code, "libelle": libelle, "date_echeance": echeance,
                      "jours": jours, "palier": palier_de(jours, liste), "destinataire_id": destinataire_id})

    for o in Estimate.objects.filter(status=Estimate.Status.SOUMISE, valid_until__isnull=False, valid_until__lte=horizon):
        ajout("offre", o, f"{o.code} v{o.version}", f"Validité de l'offre « {o.title} »", o.valid_until, o.created_by_id)
    for c in Contract.objects.filter(status__in=[Contract.Status.ACTIF, Contract.Status.SUSPENDU],
                                     end_date__isnull=False, end_date__lte=horizon).select_related("affaire"):
        ajout("contrat", c, c.code, f"Échéance du contrat {c.get_profile_display().lower()}", c.end_date,
              c.affaire.responsable_id if c.affaire_id else None)
    for av in Avenant.objects.filter(statut=Avenant.Statut.BROUILLON, contract__end_date__isnull=False,
                                     contract__end_date__lte=horizon).select_related("contract"):
        ajout("avenant", av, f"{av.contract.code} / av. {av.numero}", f"Avenant non signé : {av.objet}",
              av.contract.end_date, av.created_by_id)
    return sorted(items, key=lambda x: x["jours"])


def _notifier(user, sujet, message, debut_jour):
    from workflow.models import Notification
    from workflow.notifications import notify

    sujet = sujet[:255]
    if Notification.objects.filter(user=user, subject=sujet, created_at__gte=debut_jour).exists():
        return 0
    notify(user, sujet, message, kind="reminder")
    return 1


def relances_commerciales(today=None):
    """Notifications quotidiennes M1 (dédoublonnées par jour) : échéances aux paliers, opportunités inactives,
    clients à relancer / inactifs, dérives de coût. Appelée après la tâche quotidienne des échéances et à la demande."""
    from users.models import User

    today = today or timezone.localdate()
    debut_jour = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    pilotes = list(User.objects.filter(is_active=True, role__in=[User.Role.DIRECTEUR_PROJETS, User.Role.SECRETAIRE_GENERAL]))
    par_id = {u.pk: u for u in User.objects.filter(is_active=True)}
    envoyees = 0

    def destinataires(user_id):
        cibles = list(pilotes)
        if user_id and user_id in par_id and par_id[user_id] not in cibles:
            cibles.append(par_id[user_id])
        return cibles

    liste = paliers()
    for e in echeances_m1(today):
        if e["jours"] not in liste:
            continue
        sujet = f"Échéance J-{e['jours']} : {e['code']} — {e['libelle']}"
        message = f"{e['libelle']} ({e['code']}) : échéance le {e['date_echeance']:%d/%m/%Y}."
        for u in destinataires(e["destinataire_id"]):
            envoyees += _notifier(u, sujet, message, debut_jour)
    for o in alertes_opportunites(today):
        sujet = f"Opportunité à relancer : {o['code']} — {o['objet']}"
        for u in destinataires(o["owner_id"]) if o["owner_id"] else pilotes:
            envoyees += _notifier(u, sujet, " ; ".join(o["motifs"]) + ".", debut_jour)
    for c in clients_signaux():
        codes = {s["code"] for s in c["signaux"]} & {"relance", "inactif"}
        if codes:
            sujet = f"Client à relancer : {c['client']}"
            message = " ; ".join(s["libelle"] for s in c["signaux"]) + "."
            for u in pilotes:
                envoyees += _notifier(u, sujet, message, debut_jour)
    for d in derives_affaires(True)["lignes"]:
        if d["alerte"]:
            sujet = f"Dérive de coût : {d['code']} ({d['derive_pct']} %)"
            for u in destinataires(d["responsable_id"]):
                envoyees += _notifier(u, sujet, f"Coût réel {d['cout_reel']} pour {d['cout_prevu_a_date']} prévus à date.",
                                      debut_jour)
    return envoyees


# --------------------------------------------------------------------------------------------- profils contractuels
def duree_mois(start, end, months):
    if months:
        return int(months)
    if start and end:
        return int(round((end - start).days / 30.44))
    return None


def controle_duree(profile, mois):
    """Message si la durée sort de la fourchette du profil (CDC : travaux 18-36 mois, maintenance 2-5 ans)."""
    if mois is None or not profile:
        return None
    prefixe = "DUREE_TRAVAUX" if profile == "marche_travaux" else "DUREE_MAINTENANCE"
    mini, maxi = int(get_param(f"{prefixe}_MIN")), int(get_param(f"{prefixe}_MAX"))
    if mini <= mois <= maxi:
        return None
    return f"Durée de {mois} mois hors fourchette du profil ({mini}-{maxi} mois)."


def duree_bloquante():
    return get_param("DUREE_HORS_FOURCHETTE_BLOQUANT") >= 1


def taux_retenue(contract):
    if contract.retenue_rate is not None:
        return contract.retenue_rate
    return get_param("RETENUE_GARANTIE_PCT") if contract.profile == "marche_travaux" else ZERO


def controle_profil(contract):
    """Champs obligatoires par profil, vérifiés à l'activation."""
    motifs = []
    if contract.profile == "marche_travaux":
        if not (contract.end_date or contract.months):
            motifs.append("Marché de travaux : date de fin ou durée obligatoire.")
    elif contract.profile == "maintenance":
        if not contract.sla and not contract.services.filter(sla_hours__isnull=False).exists():
            motifs.append("Contrat de maintenance : SLA obligatoire (champ SLA ou prestation avec délai en heures).")
    return motifs


def calculs_contrat(contract, voir, jours_retard=0, indice=None, indice_base=None):
    montant = contract.montant_actuel or ZERO
    taux = taux_retenue(contract)
    retenue = montant * taux / CENT
    pm, plafond = get_param("PENALITE_JOUR_POUR_MILLE"), get_param("PENALITE_PLAFOND_PCT")
    brut = montant * pm / Decimal("1000") * Decimal(jours_retard)
    penalite = min(brut, montant * plafond / CENT)
    indexation = None
    if indice is not None and indice_base:
        a = get_param("INDEXATION_PART_FIXE")
        coef = a + (1 - a) * Decimal(indice) / Decimal(indice_base)
        indexation = {"coefficient": str(coef.quantize(Decimal("0.0001"))), "montant_indexe": _s(montant * coef, voir),
                      "applicable": contract.indexation}
    mois = duree_mois(contract.start_date, contract.end_date, contract.months)
    return {
        "contrat": contract.code, "profil": contract.get_profile_display(), "montant": _s(montant, voir),
        "taux_retenue_pct": _s(taux), "retenue_garantie": _s(retenue, voir), "net_apres_retenue": _s(montant - retenue, voir),
        "jours_retard": jours_retard, "penalites": _s(penalite, voir), "penalites_plafonnees": brut > penalite,
        "indexation": indexation, "duree_mois": mois,
        "alerte_duree": controle_duree(contract.profile, mois), "controle_profil": controle_profil(contract),
        "sla": [{"prestation": s.label, "sla_heures": s.sla_hours} for s in contract.services.all() if s.sla_hours]
        + ([{"prestation": "Contrat", "sla_heures": None, "texte": contract.sla}] if contract.sla else []),
        "provisoire": provisoires(("RETENUE_GARANTIE_PCT", "PENALITE_JOUR_POUR_MILLE", "PENALITE_PLAFOND_PCT",
                                   "INDEXATION_PART_FIXE")),
    }


@transaction.atomic
def generer_echeancier(contract):
    """Échéancier type : une échéance par mois de durée (maintenance : redevance ; travaux : situation mensuelle),
    montant réparti à parts égales — jalons facturables de l'affaire (sortie M10)."""
    from .models import Milestone

    if not contract.affaire_id:
        raise ValidationError({"detail": "Contrat sans affaire : échéancier impossible."})
    prefixe = f"Échéance {contract.code}"
    if contract.affaire.milestones.filter(label__startswith=prefixe).exists():
        raise ValidationError({"detail": "Échéancier déjà généré pour ce contrat."})
    mois = duree_mois(contract.start_date, contract.end_date, contract.months)
    if not mois:
        raise ValidationError({"detail": "Durée du contrat inconnue (fin ou nombre de mois)."})
    mois = min(mois, 120)
    montant = contract.montant_actuel or ZERO
    part = (montant / mois).quantize(Decimal("0.01"))
    nature = "redevance" if contract.profile == "maintenance" else "situation"
    crees = []
    for i in range(1, mois + 1):
        m = part if i < mois else montant - part * (mois - 1)
        crees.append(Milestone.objects.create(
            affaire=contract.affaire, label=f"{prefixe} {i}/{mois} ({nature})",
            planned_date=ajouter_mois(contract.start_date, i), montant=m,
        ))
    return crees


def retenues_contrat(contract, voir):
    """Retenue de garantie sur les factures émises de l'affaire (net des avoirs) et date de libération."""
    from comptabilite.models import FactureClient

    taux = taux_retenue(contract)
    factures = []
    base = ZERO
    if contract.affaire_id:
        for f in FactureClient.objects.filter(affaire_id=contract.affaire_id, statut=FactureClient.Statut.EMISE).order_by("code"):
            signe = -1 if f.nature == FactureClient.Nature.AVOIR else 1
            base += signe * f.montant_ht
            factures.append({"code": f.code, "nature": f.get_nature_display(), "montant_ht": _s(f.montant_ht * signe, voir),
                             "retenue": _s(f.montant_ht * signe * taux / CENT, voir)})
    fin = contract.end_date or (ajouter_mois(contract.start_date, contract.months) if contract.months else None)
    liberation = ajouter_mois(fin, get_param("GARANTIE_DUREE_MOIS")) if fin else None
    return {"contrat": contract.code, "taux_pct": _s(taux), "base_facturee": _s(base, voir),
            "retenue_cumulee": _s(base * taux / CENT, voir), "date_liberation": liberation, "factures": factures,
            "provisoire": provisoires(("RETENUE_GARANTIE_PCT", "GARANTIE_DUREE_MOIS"))}


# --------------------------------------------------------------------------------------------- aval M9 : personnel
def plan_charge(affaire):
    """Plan de charge nominatif : membres des équipes affectées aux OF de l'affaire (M3 → M9)."""
    from operations.models import AffectationEquipe

    lignes = []
    for af in (AffectationEquipe.objects.filter(ordre__affaire=affaire).select_related("equipe", "ordre")
               .prefetch_related("equipe__membres").order_by("date_debut")):
        for e in af.equipe.membres.all():
            lignes.append({"employe_id": str(e.pk), "matricule": e.code, "nom": e.nom_complet, "equipe": af.equipe.label,
                           "ordre": af.ordre.code, "du": af.date_debut, "au": af.date_fin, "statut": af.get_statut_display(),
                           "jours": (af.date_fin - af.date_debut).days + 1})
    return lignes


def mots_requis(contract):
    from .models import HabilitationRequise

    return sorted(set(HabilitationRequise.objects.filter(
        Q(contract=contract) | Q(contract__isnull=True, profile=contract.profile)
    ).values_list("mot_cle", flat=True)))


def conformite_habilitations(contract, today=None):
    from rh_paie.models import Employe

    today = today or timezone.localdate()
    mots = mots_requis(contract)
    personnes = {}
    if contract.affaire_id:
        for ligne in plan_charge(contract.affaire):
            personnes.setdefault(ligne["employe_id"], ligne)
    lignes = []
    for emp_id, ligne in personnes.items():
        employe = Employe.objects.get(pk=emp_id)
        valides = [q.intitule.lower() for q in employe.qualifications.filter(
            Q(date_validite__isnull=True) | Q(date_validite__gte=today))]
        manquantes = [m for m in mots if not any(m.lower() in v for v in valides)]
        lignes.append({"matricule": ligne["matricule"], "nom": ligne["nom"], "equipe": ligne["equipe"],
                       "manquantes": manquantes, "conforme": not manquantes})
    return {"contrat": contract.code, "habilitations_requises": mots, "personnel": lignes,
            "conforme": all(x["conforme"] for x in lignes)}


def controle_habilitations_affaire(affaire):
    """Démarrage : le personnel déjà affecté doit détenir les habilitations exigées par les contrats de l'affaire."""
    for contrat in affaire.contracts.all():
        resultat = conformite_habilitations(contrat)
        ko = [p for p in resultat["personnel"] if not p["conforme"]]
        if ko:
            noms = ", ".join(f"{p['nom']} ({', '.join(p['manquantes'])})" for p in ko[:5])
            return f"Habilitations exigées par le contrat {contrat.code} manquantes : {noms}."
    return None


# --------------------------------------------------------------------------------------------- aval M2 : achats
@transaction.atomic
def generer_besoins_achat(affaire, user):
    """DA brouillon (M2) depuis la fiche affaire : délègue à la règle UNIQUE des Achats (`achats.ecarts.da_depuis_affaire`,
    affaire liée + imputation analytique), en exigeant une offre gagnée et au moins une ligne achetable."""
    from achats.ecarts import da_depuis_affaire

    da, _n = da_depuis_affaire(affaire, user, exiger_lignes=True)
    return da


def achats_affaire(affaire, voir):
    from achats.models import PurchaseOrder, PurchaseRequest

    if not affaire.analytic_id:
        return {"demandes": [], "commandes": []}
    return {
        "demandes": [{"code": d.code, "objet": d.title, "statut": d.get_status_display(), "montant": _s(d.montant_estime, voir)}
                     for d in PurchaseRequest.objects.filter(analytic_id=affaire.analytic_id).prefetch_related("lines")],
        "commandes": [{"code": c.code, "statut": c.get_status_display(), "date": c.order_date}
                      for c in PurchaseOrder.objects.filter(analytic_id=affaire.analytic_id)],
    }


def bons_sortie(affaire):
    from stocks.models import MouvementStock

    return MouvementStock.objects.filter(ordre__affaire=affaire, type_mouvement=MouvementStock.Type.CONSOMMATION).count()


# --------------------------------------------------------------------------------------------- RAO / RC en GED
TYPE_GED_RAO = ("commercial_rao", "Revues d'appel d'offres (RAO)")
TYPE_GED_RC = ("commercial_rc", "Revues de commande (RC)")
RETENTION_ANS = 10


def _pdf(titre, lignes, tableau=None, note=""):
    import io

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, title=titre)
    corps = [Paragraph(titre, styles["Title"]), Spacer(1, 4 * mm)]
    info = Table([[k, v] for k, v in lignes], colWidths=[55 * mm, 125 * mm])
    info.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 9),
                              ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef1f8"))]))
    corps += [info, Spacer(1, 6 * mm)]
    if tableau:
        t = Table(tableau, colWidths=[110 * mm, 35 * mm, 35 * mm])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 9),
                               ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef1f8"))]))
        corps += [t, Spacer(1, 6 * mm)]
    signatures = Table([["Établi par", "Validé par (Direction)"], ["\n\n\n", "\n\n\n"]], colWidths=[90 * mm, 90 * mm])
    signatures.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey)]))
    corps += [signatures, Spacer(1, 4 * mm), Paragraph(note, styles["Italic"])]
    doc.build(corps)
    return buf.getvalue()


NOTE_MODELE = "Modèle provisoire généré par l'ERP — à confirmer ou remplacer par le modèle officiel ETSL."


def pdf_rao(rao):
    decision = dict(rao._meta.get_field("decision_rao").choices).get(rao.decision_rao, "—")
    lignes = [
        ["Formulaire", "ENG-PR1-01 — Revue d'appel d'offres"], ["Appel d'offres", rao.tender_ref or "—"],
        ["Client", rao.client.name if rao.client_id else "—"],
        ["Offre", f"{rao.estimate.code} v{rao.estimate.version}" if rao.estimate_id else "—"],
        ["Date limite de dépôt", f"{rao.bid_deadline:%d/%m/%Y}" if rao.bid_deadline else "—"],
        ["Note pondérée", f"{rao.score} %" if rao.score is not None else "—"], ["Décision", decision],
        ["Justification / suite", rao.decision or "—"], ["Revu par", str(rao.reviewed_by or "—")],
    ]
    tableau = [["Critère", "Poids", "Note /100"]] + [
        [str(c.get("libelle", "")), str(c.get("poids", "")), str(c.get("note", ""))] for c in (rao.criteres or [])
    ]
    return _pdf(f"Revue d'appel d'offres {rao.tender_ref or ''}".strip(), lignes, tableau, get_texte("NOTE_MODELE_PDF"))


def pdf_rc(revue):
    lignes = [
        ["Affaire", f"{revue.affaire.code} — {revue.affaire.title}"],
        ["Montant de l'offre signée", f"{revue.montant_offre}"], ["Montant de la commande", f"{revue.montant_commande}"],
        ["Écart de prix", f"{revue.delta_prix_pct} %"],
        ["Délai offre / commande", f"{revue.delai_offre_jours} j / {revue.delai_commande_jours} j"],
        ["Type de revue", revue.get_type_revue_display()], ["Statut", revue.get_statut_display()],
        ["Commentaire", revue.commentaire or "—"], ["Validée par", str(revue.valide_par or "—")],
        ["Validée le", f"{revue.valide_le:%d/%m/%Y %H:%M}" if revue.valide_le else "—"],
    ]
    return _pdf(f"Revue de commande {revue.affaire.code}", lignes, note=get_texte("NOTE_MODELE_PDF"))


def archiver_rao(rao, user):
    from stocks.services import archiver_piece_ged

    if rao.document_id:
        raise ValidationError({"detail": "Formulaire RAO déjà archivé en GED."})
    ref = rao.tender_ref or str(rao.pk)[:8]
    rao.document = archiver_piece_ged(pdf_rao(rao), f"RAO-{ref}.pdf", f"RAO ENG-PR1-01 {ref}", *TYPE_GED_RAO,
                                      RETENTION_ANS, f"RAO {ref}", user=user, mots=("RAO", "ENG-PR1-01"))
    rao.save(update_fields=["document", "updated_at"])
    return rao.document


def archiver_rc(revue, user):
    from stocks.services import archiver_piece_ged

    if revue.document_id:
        raise ValidationError({"detail": "Revue de commande déjà archivée en GED."})
    code = revue.affaire.code
    revue.document = archiver_piece_ged(pdf_rc(revue), f"RC-{code}.pdf", f"Revue de commande {code}", *TYPE_GED_RC,
                                        RETENTION_ANS, f"RC {code}", user=user, mots=("RC", code))
    revue.save(update_fields=["document", "updated_at"])
    return revue.document


# --------------------------------------------------------------------------------------------- indicateurs
def indicateurs_commerciaux(voir):
    """Reporting commercial (Couche D) : prix moyen des offres gagnées (définition provisoire), par profil ;
    score client moyen et répartition ; taux de transformation des offres."""
    from .models import ClientProfile, Estimate

    gagnees = list(Estimate.objects.filter(status=Estimate.Status.GAGNEE).select_related("opportunity")
                   .prefetch_related("options", "lines", "opportunity__affaires__contracts"))
    perdues = Estimate.objects.filter(status=Estimate.Status.PERDUE).count()
    montants = [e.montant_offre or ZERO for e in gagnees]
    par_profil = {}
    for e in gagnees:
        cle = profil_opportunite(e.opportunity) if e.opportunity_id else "non_renseigne"
        par_profil.setdefault(cle, []).append(e.montant_offre or ZERO)
    scores = list(ClientProfile.objects.filter(is_active=True).values_list("scoring", flat=True))
    seuil = int(get_param("SCORE_SEUIL_ALERTE"))
    return {
        "prix_moyen": _s(sum(montants, ZERO) / len(montants), voir) if montants else None,
        "offres_gagnees": len(gagnees),
        "taux_transformation_pct": _s(Decimal(len(gagnees) * 100) / (len(gagnees) + perdues)) if gagnees or perdues else None,
        "prix_moyen_par_profil": [{"profil": k, "nombre": len(v), "prix_moyen": _s(sum(v, ZERO) / len(v), voir)}
                                  for k, v in sorted(par_profil.items())],
        "score_moyen": _s(Decimal(sum(scores)) / len(scores)) if scores else None,
        "clients_sous_seuil": sum(1 for s in scores if s < seuil),
        "clients_70_plus": sum(1 for s in scores if s >= 70),
        "definition_prix_moyen": get_texte("DEFINITION_PRIX_MOYEN"),
    }
