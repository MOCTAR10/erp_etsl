"""Clôture M3 Opérations (CDC §6.11) : pointages → paie M9, situations prêtes à facturer M10, capacité finie, dossier archivé."""

import hashlib
import json
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import CapaciteAtelier, DossierOperationnel, OrdreFabrication, PointageChantier


def valider_pointage(pointage, user):
    if pointage.status != PointageChantier.Status.SAISI:
        raise ValidationError("Seul un pointage saisi peut être validé.")
    if user and pointage.created_by_id == user.id:
        raise ValidationError("Séparation des tâches : le saisisseur ne peut pas valider son propre pointage.")
    pointage.status = PointageChantier.Status.VALIDE
    pointage.validated_by = user
    pointage.validated_at = timezone.now()
    pointage.save(update_fields=["status", "validated_by", "validated_at", "updated_at"])
    return pointage


def transferer_paie(pointage):
    """Publie un pointage validé vers M9 (SaisieTemps) — idempotent : un pointage ne produit qu'une saisie."""
    from rh_paie.models import Employe, SaisieTemps

    if pointage.status == PointageChantier.Status.TRANSFERE and pointage.saisie_temps_id:
        return pointage.saisie_temps
    if pointage.status != PointageChantier.Status.VALIDE:
        raise ValidationError("Seul un pointage validé peut être transféré en paie.")
    employe = Employe.objects.filter(user_id=pointage.worker_id).first() if pointage.worker_id else None
    if employe is None:
        raise ValidationError("Opérateur sans fiche salarié : transfert en paie impossible (rattacher le compte à une fiche RH).")
    saisie = SaisieTemps.objects.create(
        employe=employe, date=pointage.date, heures=pointage.hours, type=pointage.hours_type,
        source=f"chantier:{pointage.code}"[:20], statut=SaisieTemps.Statut.TRANSFERE_PAIE,
    )
    pointage.saisie_temps = saisie
    pointage.status = PointageChantier.Status.TRANSFERE
    pointage.save(update_fields=["saisie_temps", "status", "updated_at"])
    from rh_paie.compta_m9b import valoriser_saisie
    from rh_paie.formation_m9c import alerter_depassement_mo

    saisie = valoriser_saisie(saisie)  # coût chargé (contrat + charges patronales) retourné à M3 / M11
    alerter_depassement_mo(pointage.ordre)  # heures pointées > prévues (+ seuil) : alerte opérations
    return saisie


def _weeks(of):
    start = of.planned_start or timezone.localdate()
    end = of.planned_end or start
    monday = start - timedelta(days=start.weekday())
    weeks = []
    while monday <= end:
        weeks.append(monday)
        monday += timedelta(days=7)
    return weeks or [start - timedelta(days=start.weekday())]


def alertes_surcharge():
    """Capacité finie : heures planifiées (réparties uniformément sur les semaines de l'OF) vs capacité hebdomadaire."""
    charge = defaultdict(Decimal)
    actifs = [OrdreFabrication.Status.PREVU, OrdreFabrication.Status.LANCE, OrdreFabrication.Status.EN_COURS]
    for of in OrdreFabrication.objects.filter(status__in=actifs):
        semaines = _weeks(of)
        part = of.calculated_hours / len(semaines)
        for w in semaines:
            charge[(of.scope, w)] += part
    alertes = []
    for cap in CapaciteAtelier.objects.filter(resource=CapaciteAtelier.Resource.RH):
        for (scope, w), heures in sorted(charge.items(), key=lambda kv: kv[0][1]):
            if scope == cap.scope and heures > cap.hours_per_week:
                alertes.append({
                    "scope": scope, "week": w.isoformat(), "planned_hours": float(round(heures, 2)),
                    "capacity": float(cap.hours_per_week), "overload_pct": float(round(heures / cap.hours_per_week * 100 - 100, 1)),
                })
    return alertes


def figer_dossier(of):
    """Dossier opérationnel scellé à la libération de l'OF (une seule fois)."""
    existant = DossierOperationnel.objects.filter(ordre=of).first()
    if existant:
        return existant
    from qualite.models import ControleQualite, NonConformite

    contenu = {
        "ordre": {"code": of.code, "label": of.label, "scope": of.scope, "affaire": of.affaire.code if of.affaire_id else None,
                  "heures_calculees": str(of.calculated_hours), "quantite": str(of.quantity)},
        "pointages": [{"code": p.code, "date": p.date.isoformat(), "heures": str(p.hours), "statut": p.status,
                       "operateur": p.worker_name or (p.worker.email if p.worker_id else "")} for p in of.pointages.all()],
        "controles": [{"code": c.code, "statut": c.statut, "resultat": c.resultat}
                      for c in ControleQualite.objects.filter(ordre=of)],
        "non_conformites": [{"code": n.code, "statut": n.statut} for n in NonConformite.objects.filter(controle__ordre=of)],
        "mouvements_stock": [{"code": m.code, "type": m.type_mouvement} for m in of.mouvements_stock.all()],
        "libere_le": timezone.now().isoformat(),
    }
    empreinte = hashlib.sha256(json.dumps(contenu, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return DossierOperationnel.objects.create(ordre=of, contenu=contenu, sha256=empreinte)
