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
    employe = pointage.employe or (Employe.objects.filter(user_id=pointage.worker_id).first() if pointage.worker_id else None)
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
    """Capacité finie : heures planifiées (réparties uniformément sur les semaines de l'OF) vs capacité hebdomadaire,
    pour la main-d'œuvre (heures de gamme) et les machines (heures machine de gamme)."""
    from .ecarts import heures_machine, param

    charge = defaultdict(Decimal)
    actifs = [OrdreFabrication.Status.PREVU, OrdreFabrication.Status.LANCE, OrdreFabrication.Status.EN_COURS]
    for of in OrdreFabrication.objects.filter(status__in=actifs).select_related("gamme"):
        semaines = _weeks(of)
        for ressource, total in (("rh", of.calculated_hours), ("machine", heures_machine(of))):
            part = total / len(semaines)
            for w in semaines:
                charge[(of.scope, ressource, w)] += part
    seuil = param("SEUIL_ESCALADE_GR_PCT")
    alertes = []
    for cap in CapaciteAtelier.objects.all():
        for (scope, ressource, w), heures in sorted(charge.items(), key=lambda kv: kv[0][2]):
            if scope == cap.scope and ressource == cap.resource and heures > cap.hours_per_week:
                surcharge = round(heures / cap.hours_per_week * 100 - 100, 1)
                alertes.append({
                    "scope": scope, "resource": ressource, "week": w.isoformat(), "planned_hours": float(round(heures, 2)),
                    "capacity": float(cap.hours_per_week), "overload_pct": float(surcharge),
                    "escalade_gr": surcharge > seuil,
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
        # Écarts M3-08 : situations, rapports, transferts, attachements, fiches de contrôle et documents GED liés.
        "situations": [{"code": s.code, "statut": s.status, "avancement": s.progress, "periode_fin": s.period_end.isoformat()}
                       for s in of.situations.all()],
        "rapports": [{"code": r.code, "type": r.type, "date": r.date.isoformat(), "realise": str(r.quantite_realisee),
                      "rebut": str(r.quantite_rebut), "statut": r.statut} for r in of.rapports.all()],
        "transferts": [{"code": t.code, "type": t.type, "destination": t.destination, "statut": t.statut} for t in of.transferts.all()],
        "attachements": [{"code": a.code, "designation": a.designation, "quantite": str(a.quantite), "unite": a.unite,
                          "statut": a.statut} for a in of.attachements.all()],
        "fiches_controle": [{"code": f.code, "objet": f.objet, "conforme": f.conforme} for f in of.fiches_controle.all()],
        "documents_ged": documents_ged_of(of),
        "libere_le": timezone.now().isoformat(),
    }
    from .ecarts import param

    empreinte = hashlib.sha256(json.dumps(contenu, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return DossierOperationnel.objects.create(
        ordre=of, contenu=contenu, sha256=empreinte, retention_years=int(param("RETENTION_OPERATIONS_ANS"))
    )


def documents_ged_of(of):
    """Documents GED liés à l'OF (liens métier M12) : titre, référence, empreinte."""
    from juridique.models import LienDocument

    return [
        {"document": str(l.document_id), "titre": l.document.title, "reference": l.document.reference,
         "sha256": l.document.sha256, "lie_le": l.created_at.isoformat()}
        for l in LienDocument.objects.filter(objet_type="operations.ordrefabrication", objet_id=str(of.pk)).select_related("document")
    ]
