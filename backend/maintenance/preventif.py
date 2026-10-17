"""Maintenance préventive automatisée (lot 14, CDC M8 §13.4 / §13.11, M4 §12.11).

« Dépassement de seuil compteur → OT de maintenance M8 automatique » et préventif calendaire : chaque plan
échu génère un OT préventif, sans doublon tant qu'un OT du plan reste ouvert. Appelé à chaque relevé de
compteur (M8 ou relevé logistique GR) et chaque jour par la tâche Celery `declencher_plans_preventifs`.
"""

from django.db import transaction
from django.utils import timezone

from .models import Actif, OrdreTravail, PlanPreventif

ACTIFS_INACTIFS = (Actif.Statut.HORS_SERVICE, Actif.Statut.REFORME)


@transaction.atomic
def declencher_plans(actifs=None, today=None, user=None):
    """Génère les OT préventifs des plans échus ; renvoie la liste des OT créés."""
    today = today or timezone.localdate()
    plans = (
        PlanPreventif.objects.select_for_update(of=("self",))
        .select_related("actif", "actif__equipement_gr")
        .filter(en_vigueur=True)
        .exclude(actif__statut__in=ACTIFS_INACTIFS)
    )
    if actifs is not None:
        plans = plans.filter(actif__in=actifs)
    crees = []
    for plan in plans:
        motif = plan.motif_echeance(today)
        if not motif or plan.ordres.exclude(statut__in=OrdreTravail.STATUTS_CLOS).exists():
            continue
        crees.append(
            OrdreTravail.objects.create(
                actif=plan.actif,
                plan=plan,
                type_ot=OrdreTravail.TypeOT.PREVENTIF,
                priorite=plan.priorite,
                description=f"Préventif {plan.code} — {plan.libelle}"
                + (f" ({plan.composant})" if plan.composant else "")
                + f" : {motif}.",
                date_planifiee=plan.prochaine_date if plan.prochaine_date and plan.prochaine_date > today else today,
                created_by=user,
            )
        )
    return crees


def rearmer_plan(ot):
    """Clôture d'un OT issu d'un plan : la prochaine échéance repart de cette exécution."""
    if not ot.plan_id:
        return
    plan = ot.plan
    plan.derniere_date = timezone.localdate(ot.date_fin) if ot.date_fin else timezone.localdate()
    plan.dernier_compteur = ot.actif.compteur_lecture
    plan.save(update_fields=["derniere_date", "dernier_compteur", "updated_at"])
