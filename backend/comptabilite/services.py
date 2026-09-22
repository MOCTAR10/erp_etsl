"""Droits métier M10 — Comptabilité & Trésorerie (RF-ERP-90…94).

Écriture : rôles compte / finance, Secrétariat Général (visa des dépenses,
RF-ERP-W1), Opérations (dépenses atelier), Projets, Direction. Montants masqués
hors rôles autorisés (pattern RF-59). Lecture : tous utilisateurs authentifiés.
Les paiements rapprochent les pièces M2 (factures fournisseurs) ; la
refacturation intra-groupe s'appuie sur le partenaire flaggé `is_global_rental`
et le compte 618 (M4/M5, RF-ERP-93).
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from rest_framework.permissions import BasePermission

from users.models import User

from .models import Paiement

COMPTA_WRITE_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.SECRETAIRE_GENERAL,
    User.Role.DIRECTEUR_PROJETS,
    User.Role.DIRECTEUR_OPERATIONS,
    User.Role.FINANCE,
    User.Role.COMPTABLE,
    User.Role.DIRECTION,
)

COMPTA_AMOUNT_ROLES = (
    User.Role.ADMIN,
    User.Role.PDG,
    User.Role.DGA,
    User.Role.SECRETAIRE_GENERAL,
    User.Role.FINANCE,
    User.Role.COMPTABLE,
    User.Role.DIRECTION,
)


def is_admin_or_staff(user):
    return user.is_authenticated and (
        user.is_staff or user.is_superuser or user.role == User.Role.ADMIN
    )


def can_manage_compta(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in COMPTA_WRITE_ROLES


def can_see_amount(user):
    if is_admin_or_staff(user):
        return True
    return user.is_authenticated and user.role in COMPTA_AMOUNT_ROLES


class CanManageCompta(BasePermission):
    """Lecture authentifiée ; écriture réservée aux rôles comptables / finance."""

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return bool(getattr(request, "user", None) and request.user.is_authenticated)
        return can_manage_compta(getattr(request, "user", None))


class CanValidateCompta(BasePermission):
    """Comptabilisation / validation des paiements : cercle restreint (RF-33)."""

    message = "Rôle non autorisé à comptabiliser un paiement."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return is_admin_or_staff(user) or user.role in COMPTA_AMOUNT_ROLES


def build_paiement_move(paiement, user):
    """Construit et comptabilise l'écriture d'un paiement via le noyau comptable.

    Décaissement : Débit compte dépense (601/602/618…) / Crédit banque (512x).
    Encaissement : Débit banque (512x) / Crédit produit (701/706…) hors TVA 18 %
    restituée via la TVA sur opérations (gestion simplifiée : ligne produit HT,
    FAQ — la TVA est portée par les écritures de facturation M2 via `integrations`).
    Refacturation intra-groupe : compte de dépense 618000 (M4/M5).
    """
    from accounting_kernel.models import Journal, Period
    from accounting_kernel.services import period_for_date, post_move
    from referentiels.models import Account, Partner

    if paiement.move_id:
        raise ValidationError("Paiement déjà comptabilisé.")

    banque = paiement.compte_bancaire.compte_comptable
    journal_codes = {"especes": "CAI", "cheque": "BQ", "virement": "BQ", "cfonb": "BQ", "autre": "OD"}
    journal = Journal.objects.get(code=journal_codes[paiement.mode])
    try:
        period = period_for_date(paiement.date)
    except ValidationError as exc:
        raise ValidationError(str(exc))

    # Détermination des comptes.
    tiers = paiement.tiers
    if paiement.sens == paiement.Sens.SORTIE:
        if paiement.imputation_618:
            compte_depense = Account.objects.get(code="618000")
        elif paiement.engagement_id:
            compte_depense = paiement.engagement.compte_depense
        elif tiers and tiers.kind in (Partner.Kind.FOURNISSEUR, Partner.Kind.BOTH):
            compte_depense = Account.objects.get(
                code="401100" if tiers.is_global_rental else "401000"
            )
        else:
            compte_depense = Account.objects.get(code="601000")
    else:
        compte_depense = Account.objects.get(
            code="411100" if (tiers and tiers.is_global_rental) else "411000"
        )

    montant = Decimal(paiement.montant)
    from accounting_kernel.models import AccountMove, AccountMoveLine

    move = AccountMove.objects.create(
        journal=journal,
        period=period,
        date=paiement.date,
        reference=paiement.reference or paiement.code,
        label=f"{paiement.get_sens_display()} — {paiement.engagement.objet if paiement.engagement_id else (paiement.tiers.name if paiement.tiers_id else '')}",
        source="M10",
        source_ref=paiement.code,
        status=AccountMove.Status.DRAFT,
    )
    AccountMoveLine.objects.create(
        move=move,
        account=compte_depense,
        partner=paiement.tiers,
        label=paiement.engagement.objet if paiement.engagement_id else (paiement.tiers.name if paiement.tiers_id else paiement.get_sens_display()),
        debit=montant if paiement.sens == paiement.Sens.SORTIE else 0,
        credit=montant if paiement.sens == paiement.Sens.ENTREE else 0,
        order=1,
    )
    AccountMoveLine.objects.create(
        move=move,
        account=banque,
        partner=None,
        label=paiement.compte_bancaire.label,
        debit=montant if paiement.sens == paiement.Sens.ENTREE else 0,
        credit=montant if paiement.sens == paiement.Sens.SORTIE else 0,
        order=2,
    )
    posted = post_move(move, user=user)
    paiement.move = posted
    paiement.statut = paiement.Statut.VALIDE
    paiement.save(update_fields=["move", "statut", "updated_at"])
    return posted


def compute_declaration_tva(declaration):
    """Recalcule la TVA d'un mois à partir des paiements validés du mois.

    Base imposable = encaissements produits (entrees) ; TVA collectée = 18 %.
    TVA déductible = 18 % des décaissements hors refacturation intra-groupe.
    (Approche opérationnelle M10 ; la reprise SAGE / comptabilisation exacte
    reste celle du référentiel — SYSCOHADA révisée via `accounting_kernel`.)
    """
    from datetime import date as dt

    start = declaration.mois
    end = dt(start.year, start.month % 12 + 1, 1)
    if start.month == 12:
        end = dt(start.year + 1, 1, 1)

    paiements = Paiement.objects.filter(
        statut=Paiement.Statut.VALIDE, date__gte=start, date__lt=end
    )
    taux = Decimal(declaration.taux_tva.taux) / 100

    base = sum((p.montant for p in paiements.filter(sens=Paiement.Sens.ENTREE)), Decimal("0"))
    collectee = base * taux
    deductible = sum(
        (
            p.montant for p in paiements.filter(sens=Paiement.Sens.SORTIE).exclude(imputation_618=True)
        ),
        Decimal("0"),
    ) * taux

    declaration.base_imposable = base
    declaration.tva_collectee = collectee.quantize(Decimal("0.01"))
    declaration.tva_deductible = deductible.quantize(Decimal("0.01"))
    declaration.net_a_payer = (collectee - deductible).quantize(Decimal("0.01"))
    declaration.save(
        update_fields=[
            "base_imposable",
            "tva_collectee",
            "tva_deductible",
            "net_a_payer",
        ]
    )
    return declaration