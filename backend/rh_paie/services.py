"""Droits métier M9 — RH & Paie (RF-ERP-80…83).

RH : cercle personnel (contrats, congés, formations, sanctions, habilitations).
Paie : cercle restreint (bulletins, salaires) — la paie est sensible (RF-33).
Montants (salaire, brut, net) masqués hors rôles autorisés (pattern RF-59).
"""

import calendar
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework.permissions import BasePermission

from users.models import User
from users.rbac import can_read_app

RH_WRITE_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.SECRETAIRE_GENERAL,
    User.Role.DIRECTEUR_PROJETS,
    User.Role.DIRECTEUR_OPERATIONS,
    User.Role.RH,
    User.Role.CHEF_ATELIER,
    User.Role.DIRECTION,
)

# Paie = cercle restreint : RH (pivot), Finance/Compta, Direction.
PAIE_WRITE_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.RH,
    User.Role.FINANCE,
    User.Role.DIRECTION,
)

PAIE_AMOUNT_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.RH,
    User.Role.FINANCE,
    User.Role.COMPTABLE,
    User.Role.DIRECTION,
)


def is_admin_or_staff(user):
    return user.is_authenticated and (
        user.is_staff or user.is_superuser or user.role == User.Role.ADMIN
    )


def can_manage_rh(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in RH_WRITE_ROLES


def can_manage_paie(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in PAIE_WRITE_ROLES


def can_see_amount(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in PAIE_AMOUNT_ROLES


class CanManageRh(BasePermission):
    """Lecture authentifiée, écriture réservée au cercle RH (can_manage_rh)."""

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return can_read_app(getattr(request, "user", None), "rh_paie")
        return can_manage_rh(getattr(request, "user", None))


class CanManagePaie(BasePermission):
    """Endpoint paie (bulletins/temps) — cercle restreint RH / Finance / Direction."""

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return can_manage_paie(getattr(request, "user", None))
        return can_manage_paie(getattr(request, "user", None))


CENT = Decimal("0.01")
COT_PREFIX = "COT-"
IMP_PREFIX = "IMP-"


def _arrondi(valeur):
    return Decimal(valeur).quantize(CENT, rounding=ROUND_HALF_UP)


def baremes_en_vigueur(periode):
    """Barèmes applicables au mois `periode` (date d'effet ≤ période ≤ date de fin)."""
    from django.db.models import Q

    from .models import BaremeCotisation

    return BaremeCotisation.objects.filter(date_effet__lte=periode).filter(
        Q(date_fin__isnull=True) | Q(date_fin__gte=periode)
    )


def baremes_impot_en_vigueur(periode):
    from django.db.models import Q

    from .models import BaremeImpot

    return BaremeImpot.objects.filter(date_effet__lte=periode).filter(
        Q(date_fin__isnull=True) | Q(date_fin__gte=periode)
    )


@transaction.atomic
def calculer_bulletin(bulletin):
    """Recalcule brut, cotisations salariales (lignes `COT-*`), charges patronales et net.

    Idempotent : les lignes `COT-*` sont régénérées à chaque calcul ; gains et retenues saisis
    à la main sont conservés. Seul un bulletin brouillon est recalculable.
    """
    from .models import BulletinLigne, BulletinPaie, RubriquePaie

    original = bulletin
    bulletin = BulletinPaie.objects.select_for_update().get(pk=bulletin.pk)
    if bulletin.statut != BulletinPaie.Statut.BROUILLON:
        raise ValidationError("Seul un bulletin brouillon peut être recalculé.")

    bulletin.lignes.filter(rubrique__code__startswith=COT_PREFIX).delete()
    gains = sum(
        (l.montant for l in bulletin.lignes.filter(rubrique__nature=RubriquePaie.Nature.GAIN)), Decimal("0")
    )
    patronal = Decimal("0")
    for bareme in baremes_en_vigueur(bulletin.periode):
        assiette = gains if bareme.base == bareme.Base.BRUT else bulletin.salaire_base
        if bareme.plafond is not None:
            assiette = min(assiette, bareme.plafond)
        montant = _arrondi(assiette * bareme.taux / 100)
        if bareme.nature == bareme.Nature.PATRONALE:
            patronal += montant
            continue
        rubrique, _ = RubriquePaie.objects.get_or_create(
            code=f"{COT_PREFIX}{bareme.code}",
            defaults={"label": bareme.label, "nature": RubriquePaie.Nature.RETENUE, "ordre": 900 + bareme.ordre},
        )
        BulletinLigne.objects.update_or_create(
            bulletin=bulletin, rubrique=rubrique,
            defaults={"libelle": f"{bareme.label} ({bareme.taux} %)", "montant": montant},
        )

    # Impôt sur le revenu progressif (barème versionné) : base nette des cotisations salariales déductibles.
    bulletin.lignes.filter(rubrique__code__startswith=IMP_PREFIX).delete()
    cotisations = sum(
        (l.montant for l in bulletin.lignes.filter(rubrique__code__startswith=COT_PREFIX)), Decimal("0")
    )
    for bareme in baremes_impot_en_vigueur(bulletin.periode):
        base = gains - (cotisations if bareme.cotisations_deductibles else Decimal("0"))
        base = max(base * (Decimal("1") - bareme.abattement_pct / 100), Decimal("0"))
        parts = max(Decimal(bulletin.employe.parts_fiscales or 1), Decimal("1"))
        montant = _arrondi(bareme.impot_par_part(base / parts) * parts)
        rubrique, _ = RubriquePaie.objects.get_or_create(
            code=f"{IMP_PREFIX}{bareme.code}",
            defaults={"label": bareme.label, "nature": RubriquePaie.Nature.RETENUE, "ordre": 950},
        )
        BulletinLigne.objects.update_or_create(
            bulletin=bulletin, rubrique=rubrique,
            defaults={"libelle": f"{bareme.label} ({parts} part(s))", "montant": montant},
        )

    retenues = sum(
        (l.montant for l in bulletin.lignes.filter(rubrique__nature=RubriquePaie.Nature.RETENUE)), Decimal("0")
    )
    bulletin.brut = _arrondi(gains)
    bulletin.net = _arrondi(gains - retenues)
    bulletin.charges_patronales = _arrondi(patronal)
    bulletin.save(update_fields=["brut", "net", "charges_patronales", "updated_at"])
    # l'instance de l'appelant reflète le résultat (sérialisation de la réponse API)
    for champ in ("brut", "net", "charges_patronales", "updated_at"):
        setattr(original, champ, getattr(bulletin, champ))
    return original


def _compte(code):
    from referentiels.models import Account

    try:
        return Account.objects.get(code=code)
    except Account.DoesNotExist:
        raise ValidationError(f"Compte {code} absent du plan comptable (seed_referentiels).")


@transaction.atomic
def comptabiliser_bulletin(bulletin, user=None):
    """Écriture de paie dans le journal PAI (noyau comptable), une par bulletin validé.

    Débit 661000 charges de personnel (brut) · Débit 664000 charges sociales (patronales)
    Crédit 421000 personnel (net à payer) · Crédit 431000 organismes sociaux (retenues + patronales).
    Équilibrée par construction : brut + patronal = net + retenues + patronal.
    """
    from accounting_kernel.models import AccountMove, AccountMoveLine, Journal
    from accounting_kernel.services import period_for_date, post_move

    from .models import BulletinPaie

    bulletin = BulletinPaie.objects.select_for_update().get(pk=bulletin.pk)
    if bulletin.move_id:
        raise ValidationError("Bulletin déjà comptabilisé.")
    if bulletin.statut not in (BulletinPaie.Statut.VALIDE, BulletinPaie.Statut.CLOTURE):
        raise ValidationError("Seul un bulletin validé ou clôturé peut être comptabilisé.")
    try:
        journal = Journal.objects.get(code="PAI")
    except Journal.DoesNotExist:
        raise ValidationError("Journal de paie PAI absent (seed_accounting).")

    brut, net, patronal = bulletin.brut, bulletin.net, bulletin.charges_patronales
    retenues = brut - net
    comptes = {code: _compte(code) for code in ("661000", "664000", "421000", "431000")}
    jour = date(bulletin.periode.year, bulletin.periode.month,
                calendar.monthrange(bulletin.periode.year, bulletin.periode.month)[1])
    move = AccountMove.objects.create(
        journal=journal, period=period_for_date(jour), date=jour,
        reference=bulletin.code, label=f"Paie {bulletin.periode:%m/%Y} — {bulletin.employe.nom_complet}",
        source="M9", source_ref=bulletin.code,
    )
    lignes = [
        (comptes["661000"], brut, 0), (comptes["664000"], patronal, 0),
        (comptes["421000"], 0, net), (comptes["431000"], 0, retenues + patronal),
    ]
    for ordre, (compte, debit, credit) in enumerate(lignes):
        if debit or credit:
            AccountMoveLine.objects.create(
                move=move, account=compte, debit=debit, credit=credit, order=ordre,
                label=f"Paie {bulletin.code}",
            )
    posted = post_move(move, user=user)
    bulletin.move = posted
    bulletin.save(update_fields=["move", "updated_at"])
    return posted
