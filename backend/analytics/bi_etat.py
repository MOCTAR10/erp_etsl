"""Couche D — état des datamarts (écarts a4) : fraîcheur de l'ETL horaire, CAPA qualité / HSE, inventaire dbt.

* `indicateurs_capa` porte la règle du mart `dm_capa` (le test `analytics/test_ecarts_a4.py` exécute le SQL du mart
  et le compare à cette fonction : une dérive fait échouer la CI).
* `fraicheur_couche_d` lit `marts.dm_fraicheur_bi`, réécrit à chaque `dbt build` par le planificateur horaire du
  compose de production ; au-delà du paramètre provisoire `BI_FRAICHEUR_MAX_MIN`, l'écran signale le retard.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import connection
from django.utils import timezone

from users.rbac import can_read_app

from .cubes import _param_obj, get_param_cube
from .models import ParametreCube
from .pilotage import DBT_MODELS, marts_disponibles

ORIGINES_CAPA = ("qualite", "hse")


def _modeles_capa():
    from hse.models import ActionHse
    from qualite.models import ActionCorrective

    return {"qualite": ActionCorrective, "hse": ActionHse}


def _arrondi(valeur):
    return None if valeur is None else Decimal(valeur).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def indicateurs_capa(origines=ORIGINES_CAPA, today=None):
    """Une ligne par origine (qualité M6, HSE M7) : mêmes colonnes que le mart `dm_capa`."""
    today = today or timezone.localdate()
    modeles = _modeles_capa()
    lignes = []
    for origine in origines:
        actions = list(modeles[origine].objects.values("statut", "echeance", "efficace", "created_at", "closed_at"))
        ouvertes = [a for a in actions if a["statut"] != "cloturee"]
        cloturees = [a for a in actions if a["statut"] == "cloturee"]
        delais = [(a["closed_at"] - a["created_at"]).total_seconds() / 86400 for a in cloturees if a["closed_at"]]
        verifiees = [a for a in actions if a["efficace"] is not None]
        efficaces = [a for a in verifiees if a["efficace"]]
        lignes.append({
            "origine": origine,
            "total": len(actions),
            "ouvertes": len(ouvertes),
            "echues": sum(1 for a in ouvertes if a["echeance"] and a["echeance"] < today),
            "cloturees": len(cloturees),
            "delai_moyen_cloture_jours": _arrondi(sum(delais) / len(delais)) if delais else None,
            "efficacite_verifiee": len(verifiees),
            "efficaces": len(efficaces),
            "taux_efficacite_pct": _arrondi(Decimal(100 * len(efficaces)) / len(verifiees)) if verifiees else None,
        })
    return lignes


def fraicheur_couche_d(now=None):
    """Dernier rafraîchissement des datamarts (table `marts.dm_fraicheur_bi`) comparé au seuil provisoire."""
    seuil = int(get_param_cube("BI_FRAICHEUR_MAX_MIN"))
    now = now or timezone.now()
    with connection.cursor() as cur:
        cur.execute("select to_regclass(%s)", ["marts.dm_fraicheur_bi"])
        rafraichi = None
        if cur.fetchone()[0]:
            cur.execute('select max(rafraichi_le) from marts."dm_fraicheur_bi"')
            rafraichi = cur.fetchone()[0]
    if rafraichi is None:
        return {"statut": "jamais", "rafraichi_le": None, "age_minutes": None, "seuil_minutes": seuil}
    age = int((now - rafraichi).total_seconds() // 60)
    return {
        "statut": "a_jour" if age <= seuil else "en_retard",
        "rafraichi_le": rafraichi.isoformat(),
        "age_minutes": age,
        "seuil_minutes": seuil,
    }


def modeles_staging():
    dossier = DBT_MODELS / "staging"
    return sorted(p.stem for p in dossier.glob("stg_*.sql")) if dossier.is_dir() else []


def etat_couche_d(user):
    """Synthèse de l'écran Direction / BI : fraîcheur, CAPA (selon la lecture M6 / M7 du rôle), modèles dbt."""
    origines = tuple(o for o in ORIGINES_CAPA if can_read_app(user, o))
    capa = [
        {k: (str(v) if isinstance(v, Decimal) else v) for k, v in ligne.items()}
        for ligne in indicateurs_capa(origines)
    ]
    param = _param_obj("BI_FRAICHEUR_MAX_MIN")
    return {
        "fraicheur": fraicheur_couche_d(),
        "fraicheur_provisoire": param.statut_valeur != ParametreCube.StatutValeur.CONFIRME,
        "capa": capa,
        "marts": marts_disponibles(),
        "staging": modeles_staging(),
    }
