"""Écarts M9-C : plan de formation (catalogue, budget, coût, ROI), qualifications délivrées, matrice
habilitation ↔ poste, synchronisation des qualifications soudeur (M6), signature des bulletins, alerte de
dépassement de main-d'œuvre vers M3."""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

JOURS_OUVRES_AN_DEFAUT = Decimal("220")


def _arrondi(v):
    return Decimal(v).quantize(Decimal("0.01"))


def _ajouter_mois(jour, mois):
    an, m = divmod(jour.month - 1 + mois, 12)
    an += jour.year
    m += 1
    import calendar

    return jour.replace(year=an, month=m, day=min(jour.day, calendar.monthrange(an, m)[1]))


def valeur_parametre(code, periode, defaut):
    """Valeur d'un paramètre de paie en vigueur, ou `defaut` s'il n'est pas saisi (et son caractère provisoire)."""
    from .services import parametre

    try:
        p = parametre(code, periode)
    except ValidationError:
        return defaut, True
    return p.valeur, p.est_provisoire


# --------------------------------------------------------------------------------------------
# Plan de formation : budget, coût, ROI
# --------------------------------------------------------------------------------------------
def engage_plan(plan, exclure=None):
    """Coût engagé d'un plan : coût réel des sessions réalisées, coût prévu des sessions prévues."""
    from .models import Formation

    qs = plan.formations.exclude(type=Formation.Type.ANNULEE)
    if exclure is not None:
        qs = qs.exclude(pk=exclure)
    total = Decimal("0")
    for f in qs.only("type", "cout_prevu", "cout_reel"):
        total += f.cout_reel if f.type == Formation.Type.REALISEE and f.cout_reel is not None else f.cout_prevu
    return total


def controler_budget(plan, cout, exclure=None):
    """Une session ne peut être inscrite au plan au-delà du budget annuel voté."""
    if plan is None or not plan.budget:
        return
    engage = engage_plan(plan, exclure=exclure)
    if engage + (cout or 0) > plan.budget:
        raise ValidationError(
            f"Budget du plan {plan.annee} dépassé : {_arrondi(engage + (cout or 0))} F engagés pour "
            f"{_arrondi(plan.budget)} F votés."
        )


def roi_pct(cout, gain):
    """ROI (méthode provisoire) = (gain estimé − coût) ÷ coût × 100 ; None si l'un manque."""
    if gain is None or not cout:
        return None
    return _arrondi((Decimal(gain) - Decimal(cout)) * 100 / Decimal(cout))


def synthese_plan(plan):
    from .models import Formation

    sessions = list(plan.formations.exclude(type=Formation.Type.ANNULEE).prefetch_related("participants"))
    realisees = [f for f in sessions if f.type == Formation.Type.REALISEE]
    cout_realise = sum((f.cout_reel or Decimal("0") for f in realisees), Decimal("0"))
    heures = sum((f.duree_heures * f.participants.count() for f in realisees), Decimal("0"))
    avec_gain = [f for f in realisees if f.gain_estime is not None and f.cout_reel]
    cout_roi = sum((f.cout_reel for f in avec_gain), Decimal("0"))
    gain = sum((f.gain_estime for f in avec_gain), Decimal("0"))
    engage = engage_plan(plan)
    return {
        "budget": str(_arrondi(plan.budget)),
        "engage": str(_arrondi(engage)),
        "realise": str(_arrondi(cout_realise)),
        "reste": str(_arrondi(plan.budget - engage)),
        "sessions": len(sessions),
        "sessions_realisees": len(realisees),
        "taux_realisation_pct": str(_arrondi(Decimal(len(realisees)) * 100 / len(sessions))) if sessions else None,
        "heures_stagiaires": str(_arrondi(heures)),
        "cout_heure_stagiaire": str(_arrondi(cout_realise / heures)) if heures else None,
        "roi_pct": str(roi_pct(cout_roi, gain)) if avec_gain else None,
    }


@transaction.atomic
def realiser_formation(formation, evaluation="", cout_reel=None, gain_estime=None, note=None):
    """Marque la session réalisée et délivre la qualification du catalogue à chaque participant."""
    from .models import Formation

    formation = Formation.objects.select_for_update(of=("self",)).get(pk=formation.pk)
    if formation.type != Formation.Type.PLANIFIE:
        raise ValidationError("Seule une formation prévue peut être marquée réalisée.")
    formation.type = Formation.Type.REALISEE
    if evaluation:
        formation.evaluation = evaluation
    formation.cout_reel = formation.cout_prevu if cout_reel is None else cout_reel
    if gain_estime is not None:
        formation.gain_estime = gain_estime
    if note is not None:
        formation.note_evaluation = note
    if formation.plan_id:
        controler_budget(formation.plan, formation.cout_reel, exclure=formation.pk)
    formation.save()
    delivrer_qualifications(formation)
    return formation


def delivrer_qualifications(formation):
    """Qualification délivrée à la réalisation (type et validité portés par le catalogue)."""
    from .models import Qualification

    cat = formation.catalogue
    if cat is None or not cat.qualification_type:
        return []
    validite = _ajouter_mois(formation.date_session, cat.validite_mois) if cat.validite_mois else None
    sortie = []
    for employe in formation.participants.all():
        q, _ = Qualification.objects.update_or_create(
            source=Qualification.Source.FORMATION, source_ref=f"{formation.pk}:{employe.pk}",
            defaults={
                "employe": employe, "type": cat.qualification_type, "intitule": cat.intitule[:180],
                "organisme": (formation.organisme or cat.organisme)[:120], "date_obtention": formation.date_session,
                "date_validite": validite, "formation": formation,
            },
        )
        sortie.append(q)
    return sortie


# --------------------------------------------------------------------------------------------
# Amont M6 : qualifications soudeur recopiées dans le dossier RH
# --------------------------------------------------------------------------------------------
def synchroniser_qualification_soudeur(qs):
    from qualite.models import QualificationSoudeur

    from .models import Qualification

    ref = str(qs.pk)
    employe_id = qs.soudeur.employe_id
    if not employe_id:
        Qualification.objects.filter(source=Qualification.Source.M6, source_ref=ref).delete()
        return None
    validite = qs.date_validite
    if qs.statut != QualificationSoudeur.Statut.VALIDE:  # suspendue / expirée : plus valable dès aujourd'hui
        validite = min(validite, timezone.localdate() - timedelta(days=1))
    intitule = f"Soudeur {qs.get_norme_display()} — {qs.get_procede_display()}"
    if qs.position:
        intitule += f" — {qs.position}"
    q, _ = Qualification.objects.update_or_create(
        source=Qualification.Source.M6, source_ref=ref,
        defaults={
            "employe_id": employe_id, "type": Qualification.Type.CERTIFICAT, "intitule": intitule[:180],
            "organisme": "Qualification soudeur (M6)", "date_obtention": qs.date_qualification,
            "date_validite": validite, "notes": f"Certificat {qs.certificat or qs.code} — synchronisé depuis M6",
        },
    )
    return q


def synchroniser_soudeur(soudeur):
    for qs in soudeur.qualifications.all():
        synchroniser_qualification_soudeur(qs)


# --------------------------------------------------------------------------------------------
# Matrice habilitation ↔ poste (départ chantier)
# --------------------------------------------------------------------------------------------
def habilitations_manquantes(employe, ordre, jour):
    """Mots-clés exigés par les postes de la gamme de l'OF et non couverts par une qualification valide."""
    from .models import HabilitationPoste, Qualification

    if ordre is None or not ordre.gamme_id:
        return []
    postes = set(ordre.gamme.operations.values_list("poste", flat=True))
    exigences = HabilitationPoste.objects.filter(actif=True, poste__in=postes)
    valides = Qualification.objects.filter(employe=employe).filter(
        Q(date_obtention__isnull=True) | Q(date_obtention__lte=jour)
    ).filter(Q(date_validite__isnull=True) | Q(date_validite__gte=jour))
    return [
        f"{e.get_poste_display()} : {e.mot_cle}"
        for e in exigences
        if not valides.filter(intitule__icontains=e.mot_cle).exists()
    ]


# --------------------------------------------------------------------------------------------
# Signature électronique des bulletins (circuit avancé de la GED)
# --------------------------------------------------------------------------------------------
def statut_signature(bulletin):
    if not bulletin.document_id or not bulletin.document.current_version_id:
        return None
    req = bulletin.document.current_version.signature_requests.order_by("-created_at").first()
    return req.status if req else None


@transaction.atomic
def demander_signature_bulletin(bulletin, user, signataire=None):
    """Soumet le PDF archivé du bulletin à la signature avancée (OTP + sceau chaîné) du signataire de la paie."""
    from documents.models import SignatureRequest
    from documents.signatures import create_request

    from .models import BulletinPaie
    from .services import archiver_bulletin

    bulletin = BulletinPaie.objects.select_for_update(of=("self",)).get(pk=bulletin.pk)
    if not bulletin.document_id:
        archiver_bulletin(bulletin, user=user)
        bulletin.refresh_from_db()
    version = bulletin.document.current_version
    if version.signature_requests.filter(
        status__in=(SignatureRequest.Status.PENDING, SignatureRequest.Status.COMPLETED)
    ).exists():
        raise ValidationError("Bulletin déjà signé ou en cours de signature.")
    return create_request(
        version, [signataire or user], created_by=user,
        title=f"Bulletin de paie {bulletin.periode:%m/%Y} — {bulletin.employe.nom_complet}",
    )


# --------------------------------------------------------------------------------------------
# Aval M3 : alerte de dépassement des heures de main-d'œuvre
# --------------------------------------------------------------------------------------------
def heures_transferees(ordre):
    from operations.models import PointageChantier

    return PointageChantier.objects.filter(ordre=ordre, saisie_temps__isnull=False).aggregate(
        h=Sum("saisie_temps__heures")
    )["h"] or Decimal("0")


def depassement_mo(ordre, heures=None):
    """Heures pointées au-delà des heures prévues de l'OF majorées du seuil `ALERTE_MO_SEUIL` (%)."""
    if not ordre.calculated_hours:
        return False
    seuil, _ = valeur_parametre("ALERTE_MO_SEUIL", timezone.localdate(), Decimal("0"))
    heures = heures_transferees(ordre) if heures is None else heures
    return heures > ordre.calculated_hours * (1 + Decimal(seuil) / 100)


def alerter_depassement_mo(ordre):
    """Une seule notification par OF : responsable de l'OF, à défaut chefs d'atelier et directeurs des opérations."""
    from django.contrib.auth import get_user_model

    from workflow.notifications import notify

    if ordre.alerte_mo_le or not depassement_mo(ordre):
        return False
    heures = heures_transferees(ordre)
    destinataires = [ordre.responsible] if ordre.responsible_id else list(
        get_user_model().objects.filter(is_active=True, role__in=("chef_atelier", "directeur_operations"))
    )
    for user in destinataires:
        notify(
            user, f"Dépassement de main-d'œuvre — {ordre.code}",
            f"{_arrondi(heures)} h pointées pour {_arrondi(ordre.calculated_hours)} h prévues sur l'OF {ordre.code}.",
            kind="escalation",
        )
    ordre.alerte_mo_le = timezone.now()
    ordre.save(update_fields=["alerte_mo_le", "updated_at"])
    return True
