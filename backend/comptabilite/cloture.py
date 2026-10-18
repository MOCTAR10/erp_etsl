"""Clôture mensuelle M10 : contrôles de pré-clôture, chrono (objectif < 2 h), synthèse figée, envoi Direction à J+4.

Objectif et jour d'envoi sont des paramètres ETSL (`ParametreCompta`), provisoires jusqu'à confirmation.
La réception de la paie M9 est un contrôle bloquant : tout bulletin validé du mois doit être comptabilisé.
"""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from accounting_kernel.models import AccountMove, AccountMoveLine, Period
from accounting_kernel.services import close_period, reopen_period
from referentiels.models import Account

from .models import ClotureMensuelle, DeclarationTva, LigneReleve, Paiement
from .services import anomalies_lettrage, get_param

ZERO = Decimal("0")
COMPTABILISEES = (AccountMove.Status.POSTED, AccountMove.Status.REVERSED)


def _ctl(code, label, nb, bloquant, detail=""):
    return {"code": code, "label": label, "nb": nb, "bloquant": bloquant, "detail": detail}


def controles_cloture(period):
    """Liste des contrôles de la période ; `bloquant` + `nb > 0` empêche la clôture."""
    debut, fin = period.start_date, period.end_date
    liste = []

    precedentes = Period.objects.filter(
        fiscal_year=period.fiscal_year, number__lt=period.number, status=Period.Status.OPEN
    ).count()
    liste.append(_ctl("periodes_precedentes", "Périodes précédentes non clôturées", precedentes, True))

    brouillons = AccountMove.objects.filter(period=period, status=AccountMove.Status.DRAFT).count()
    liste.append(_ctl("ecritures_brouillon", "Écritures en brouillon", brouillons, True))

    from rh_paie.models import BulletinPaie

    bulletins = BulletinPaie.objects.filter(
        periode__gte=debut, periode__lte=fin,
        statut__in=(BulletinPaie.Statut.VALIDE, BulletinPaie.Statut.CLOTURE), move__isnull=True,
    ).count()
    liste.append(_ctl("paie_non_comptabilisee", "Bulletins de paie validés non comptabilisés (M9)", bulletins, True))

    paiements = Paiement.objects.filter(statut=Paiement.Statut.BROUILLON, date__gte=debut, date__lte=fin).count()
    liste.append(_ctl("paiements_brouillon", "Paiements / encaissements en brouillon", paiements, True))

    from .models import FactureClient

    factures = FactureClient.objects.filter(statut=FactureClient.Statut.BROUILLON, date__gte=debut, date__lte=fin).count()
    liste.append(_ctl("factures_brouillon", "Factures et avoirs clients en brouillon", factures, True))

    totaux = AccountMoveLine.objects.filter(move__period=period, move__status__in=COMPTABILISEES).aggregate(
        d=Sum("debit"), c=Sum("credit")
    )
    ecart = (totaux["d"] or ZERO) - (totaux["c"] or ZERO)
    liste.append(_ctl("balance_desequilibree", "Balance déséquilibrée de la période", 1 if ecart else 0, True,
                      f"écart {ecart}" if ecart else ""))

    non_rapprochees = LigneReleve.objects.filter(rapprochee=False, date__gte=debut, date__lte=fin).count()
    liste.append(_ctl("releves_non_rapproches", "Lignes de relevé bancaire non rapprochées", non_rapprochees, False))

    anomalies = 0
    for compte in Account.objects.filter(reconcile=True, move_lines__move__period=period).distinct():
        anomalies += len(anomalies_lettrage(compte)[1])
    liste.append(_ctl("lettrage_anomalies", "Lignes non lettrées en anomalie (sans tiers ou anciennes)", anomalies, False))

    tva = DeclarationTva.objects.filter(mois__year=debut.year, mois__month=debut.month).exclude(
        statut=DeclarationTva.Statut.BROUILLON
    ).exists()
    liste.append(_ctl("tva_non_deposee", "Déclaration de TVA du mois non déposée", 0 if tva else 1, False))
    return liste


def _montant(qs, sens):
    agg = qs.aggregate(d=Sum("debit"), c=Sum("credit"))
    d, c = agg["d"] or ZERO, agg["c"] or ZERO
    return (c - d) if sens == "credit" else (d - c)


def build_synthese(period):
    """Chiffres clés de la période pour la Direction (montants en chaînes : JSON)."""
    lignes = AccountMoveLine.objects.filter(move__status__in=COMPTABILISEES)
    periode = lignes.filter(move__period=period)
    produits = _montant(periode.filter(account__account_class=7), "credit")
    charges = _montant(periode.filter(account__account_class=6), "debit")
    cumul = lignes.filter(move__date__lte=period.end_date)
    tva = _montant(periode.filter(account__code__startswith="443"), "credit") - _montant(
        periode.filter(account__code__startswith="445"), "debit"
    )
    synthese = {
        "produits": produits, "charges": charges, "resultat": produits - charges,
        "tresorerie": _montant(cumul.filter(account__account_class=5), "debit"),
        "creances_clients": _montant(cumul.filter(account__code__startswith="411"), "debit"),
        "dettes_fournisseurs": _montant(cumul.filter(account__code__startswith="401"), "credit"),
        "tva_nette": tva,
    }
    synthese = {k: str(v) for k, v in synthese.items()}
    synthese["nb_ecritures"] = periode.values("move").distinct().count()
    return synthese


@transaction.atomic
def demarrer(period, user):
    """Lance le chrono de clôture de la période (une seule fois)."""
    if period.status == Period.Status.CLOSED:
        raise ValidationError("Période déjà clôturée.")
    if ClotureMensuelle.objects.filter(period=period).exists():
        raise ValidationError("La clôture de cette période est déjà démarrée.")
    return ClotureMensuelle.objects.create(period=period, demarree_par=user)


@transaction.atomic
def cloturer(cm, user):
    cm = ClotureMensuelle.objects.select_for_update(of=("self",)).select_related("period").get(pk=cm.pk)
    if cm.statut == ClotureMensuelle.Statut.CLOTUREE:
        raise ValidationError("Période déjà clôturée.")
    liste = controles_cloture(cm.period)
    bloquants = [c for c in liste if c["bloquant"] and c["nb"]]
    if bloquants:
        raise ValidationError(
            "Clôture impossible : " + " ; ".join(f"{c['label']} ({c['nb']})" for c in bloquants) + "."
        )
    close_period(cm.period)
    cm.period.refresh_from_db()
    maintenant = timezone.now()
    objectif = int(get_param("CLOTURE_OBJECTIF_HEURES") * 60)
    duree = Decimal((maintenant - cm.demarree_le).total_seconds()) / Decimal(60)
    cm.statut, cm.cloturee_le, cm.cloturee_par = ClotureMensuelle.Statut.CLOTUREE, maintenant, user
    cm.duree_minutes = duree.quantize(Decimal("0.1"))
    cm.objectif_minutes = objectif
    cm.dans_objectif = duree <= objectif
    cm.echeance_envoi = cm.period.end_date + timedelta(days=int(get_param("CLOTURE_JOUR_ENVOI")))
    cm.controles = liste
    cm.synthese = build_synthese(cm.period)
    cm.save()
    return cm


def _direction():
    from users.models import User

    return list(User.objects.filter(is_active=True, role__in=(User.Role.PDG, User.Role.DGA, User.Role.DIRECTION)))


def _texte_synthese(cm):
    s = cm.synthese
    f = lambda k: f"{Decimal(s[k]):,.0f}".replace(",", " ")  # noqa: E731
    duree = f"{cm.duree_minutes} min (objectif {cm.objectif_minutes} min)" if cm.duree_minutes is not None else "—"
    return (
        f"Clôture de la période {cm.period} terminée en {duree}.\n"
        f"Produits : {f('produits')} F · Charges : {f('charges')} F · Résultat : {f('resultat')} F\n"
        f"Trésorerie : {f('tresorerie')} F · Créances clients : {f('creances_clients')} F · "
        f"Dettes fournisseurs : {f('dettes_fournisseurs')} F · TVA nette : {f('tva_nette')} F\n"
        f"{s['nb_ecritures']} écriture(s) comptabilisée(s)."
    )


@transaction.atomic
def envoyer_direction(cm, user=None):
    """Notifie la Direction (PDG, DGA, Direction) de la synthèse de clôture ; un seul envoi par clôture."""
    from workflow.models import Notification

    cm = ClotureMensuelle.objects.select_for_update(of=("self",)).select_related("period").get(pk=cm.pk)
    if cm.statut != ClotureMensuelle.Statut.CLOTUREE:
        raise ValidationError("La période n'est pas clôturée : rien à envoyer à la Direction.")
    if cm.envoyee_le:
        raise ValidationError("La synthèse a déjà été envoyée à la Direction.")
    destinataires = _direction()
    if not destinataires:
        raise ValidationError("Aucun destinataire Direction (PDG, DGA ou Direction actif).")
    sujet = f"Clôture comptable {cm.period} — synthèse"
    texte = _texte_synthese(cm)
    Notification.objects.bulk_create([
        Notification(user=u, subject=sujet, message=texte, kind="info") for u in destinataires
    ])
    cm.envoyee_le, cm.envoyee_par = timezone.now(), user
    cm.destinataires = [u.email for u in destinataires]
    cm.save(update_fields=["envoyee_le", "envoyee_par", "destinataires"])
    return cm


@transaction.atomic
def rouvrir(cm, user, motif):
    """Réouverture exceptionnelle (motif obligatoire, tracée) : nouveau chrono, nouvel envoi à la prochaine clôture."""
    cm = ClotureMensuelle.objects.select_for_update(of=("self",)).select_related("period").get(pk=cm.pk)
    if cm.statut != ClotureMensuelle.Statut.CLOTUREE:
        raise ValidationError("Seule une période clôturée peut être rouverte.")
    if not (motif or "").strip():
        raise ValidationError("Le motif de réouverture est obligatoire.")
    reopen_period(cm.period)
    cm.period.refresh_from_db()
    cm.reouvertures = cm.reouvertures + [{
        "par": getattr(user, "email", ""), "le": timezone.now().isoformat(), "motif": motif.strip()[:250],
        "envoi_precedent": cm.envoyee_le.isoformat() if cm.envoyee_le else None,
    }]
    cm.statut, cm.demarree_le, cm.demarree_par = ClotureMensuelle.Statut.EN_COURS, timezone.now(), user
    cm.cloturee_le = cm.cloturee_par = cm.duree_minutes = cm.dans_objectif = None
    cm.envoyee_le = cm.envoyee_par = None
    cm.save()
    return cm


def retard_cloture(cm):
    """`cloture_en_retard` (non terminée à J+n) ou `envoi_en_retard` (synthèse non envoyée après l'échéance)."""
    jour = timezone.localdate()
    if cm.statut == ClotureMensuelle.Statut.EN_COURS:
        limite = cm.period.end_date + timedelta(days=int(get_param("CLOTURE_JOUR_ENVOI")))
        return "cloture_en_retard" if jour > limite else None
    if not cm.envoyee_le and cm.echeance_envoi and jour > cm.echeance_envoi:
        return "envoi_en_retard"
    return None
