"""Contrôle budgétaire des engagements (CDC Couche D §2.4, M2 RG-M2.08, M11 §4.7).

Règle client : budget consommé ≥ 90 % → alerte (Finance / Direction) ; > 100 % → blocage de la demande d'achat ;
> 110 % → aucun engagement possible (confirmation de BC) ; dépassement critique levé uniquement par un visa
exceptionnel du DG, motivé et tracé.

« Consommé » = BC engagés (confirmés, partiellement reçus, clôturés) + DA approuvées non encore converties en BC,
sur le compte analytique du budget de charge approuvé de l'exercice. Sans budget approuvé pour le compte, aucune
mesure n'est possible : le contrôle ne s'applique pas (le montant reste suivi en analytique).
"""

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import F, Sum

SEUIL_ALERTE = Decimal("0.90")
SEUIL_DA = Decimal("1.00")
SEUIL_ENGAGEMENT = Decimal("1.10")


@dataclass
class SituationBudget:
    budget: object
    montant: Decimal
    consomme: Decimal

    def taux(self, supplement=Decimal("0")):
        return (self.consomme + supplement) / self.montant if self.montant else Decimal("0")


def situation(analytic, jour):
    """Budget de charge approuvé couvrant `jour` pour le compte analytique, avec sa consommation."""
    from achats.models import PurchaseOrder, PurchaseOrderLine, PurchaseRequest, PurchaseRequestLine

    from .models import Budget

    if analytic is None:
        return None
    budget = (
        Budget.objects.filter(
            analytic=analytic, type_budget=Budget.TypeBudget.CHARGE, statut=Budget.Statut.APPROUVE,
            fiscal_year__start_date__lte=jour, fiscal_year__end_date__gte=jour,
        )
        .select_related("fiscal_year")
        .first()
    )
    if budget is None or not budget.montant:
        return None
    fy = budget.fiscal_year
    engages = (
        PurchaseOrderLine.objects.filter(
            purchase_order__analytic=analytic,
            purchase_order__status__in=[
                PurchaseOrder.Status.CONFIRMEE, PurchaseOrder.Status.PARTIELLE, PurchaseOrder.Status.CLOTUREE,
            ],
            purchase_order__order_date__range=(fy.start_date, fy.end_date),
        ).aggregate(s=Sum("price_total"))["s"]
        or Decimal("0")
    )
    da_approuvees = (
        PurchaseRequestLine.objects.filter(
            request__analytic=analytic, request__status=PurchaseRequest.Status.APPROUVEE,
            request__created_at__date__range=(fy.start_date, fy.end_date),
        ).aggregate(s=Sum(F("quantity") * F("estimated_price")))["s"]
        or Decimal("0")
    )
    return SituationBudget(budget=budget, montant=budget.montant, consomme=engages + da_approuvees)


def controler(analytic, jour, supplement, seuil, objet, visa_dg=False):
    """Retourne le message de blocage (str) si `supplement` fait dépasser `seuil`, sinon None.

    Déclenche l'alerte ≥ 90 % (notification Finance / Direction) dès que le seuil d'alerte est franchi.
    """
    sit = situation(analytic, jour)
    if sit is None:
        return None
    taux = sit.taux(supplement)
    if taux >= SEUIL_ALERTE:
        alerter(sit, taux, objet)
    if taux > seuil and not visa_dg:
        return (
            f"Budget {sit.budget.code} ({analytic.code}) : {objet} porterait la consommation à "
            f"{taux * 100:.1f} % (seuil {seuil * 100:.0f} %, RG-M2.08). Visa exceptionnel du DG requis."
        )
    return None


def alerter(sit, taux, objet):
    from users.models import User
    from workflow.models import Notification

    destinataires = User.objects.filter(
        is_active=True, role__in=[User.Role.FINANCE, User.Role.DGA, User.Role.DIRECTION, User.Role.PDG]
    )
    sujet = f"Alerte budget {sit.budget.code} : {taux * 100:.0f} % consommé"
    message = (
        f"{objet} porte la consommation du budget {sit.budget.code} « {sit.budget.label} » à {taux * 100:.1f} % "
        f"({sit.consomme:.0f} engagé sur {sit.montant:.0f}). Seuils CDC : 90 % alerte, 100 % blocage DA, "
        f"110 % blocage des engagements."
    )
    Notification.objects.bulk_create(
        [Notification(user=u, subject=sujet, message=message, kind="escalation") for u in destinataires]
    )
