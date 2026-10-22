"""Écarts M8 (lot m5m8) : centres analytiques maintenance, écriture de coût à la clôture d'OT, cumul annuel → M11.

- Centres analytiques « Maintenance » (axe « Centre de coût » AX-CC, créés au besoin) : atelier / machines,
  engins / levage / chantier, GLOBAL RENTAL. Chaque machine porte un centre (modifiable à l'écran) ; à défaut, il est
  déduit de la catégorie (règle provisoire, centres cibles à confirmer par ETSL).
- Clôture d'OT : écriture au journal OD (source M8), débit du compte d'entretien (624000 paramétrable) ou du 618000
  pour une machine GLOBAL RENTAL, sur le centre analytique ; crédit des comptes de transfert de la main-d'œuvre interne
  et des pièces sorties du stock (paramètres provisoires). Non bloquante : sans journal / période / compte, le motif
  est conservé sur l'OT. Publication outbox `maintenance.ot.cout` pour M11.
- Coûts consolidés par an, mois, machine et centre analytique (`?export=xlsx|pdf`).
"""

from decimal import Decimal

from django.db import transaction

from .services import COMPTE_GR, STATUTS_FAITS, get_param_maintenance

CENT = Decimal("0.01")
CENTRES_MAINTENANCE = (
    ("MAINT-ATL", "Maintenance — atelier et machines"),
    ("MAINT-PARC", "Maintenance — engins, levage et chantier"),
    ("MAINT-GR", "Maintenance — équipements GLOBAL RENTAL"),
)
CENTRE_PAR_CATEGORIE = {
    "machine": "MAINT-ATL", "atelier": "MAINT-ATL", "outillage": "MAINT-ATL",
    "engin": "MAINT-PARC", "levage": "MAINT-PARC", "chantier": "MAINT-PARC",
}


def centres_maintenance():
    """Crée au besoin l'axe « Centre de coût » et les centres maintenance ; idempotent."""
    from referentiels.models import AnalyticAccount, AnalyticAxis

    axe, _ = AnalyticAxis.objects.get_or_create(
        code="AX-CC", defaults={"label": "Centre de coût", "axis_type": AnalyticAxis.AxisType.CENTRE_COUT}
    )
    return [
        AnalyticAccount.objects.get_or_create(axis=axe, code=code, defaults={"label": label})[0]
        for code, label in CENTRES_MAINTENANCE
    ]


def est_gr(actif):
    return bool(actif.is_global_rental or actif.signe_618)


def centre_actif(actif):
    """Centre analytique de la machine : celui saisi, sinon celui déduit de la catégorie (GR → MAINT-GR)."""
    if actif.centre_analytique_id:
        return actif.centre_analytique
    code = "MAINT-GR" if est_gr(actif) else CENTRE_PAR_CATEGORIE.get(actif.categorie, "MAINT-ATL")
    return next(c for c in centres_maintenance() if c.code == code)


def _compte(code_param):
    from referentiels.models import Account

    return Account.objects.get(code=str(int(get_param_maintenance(code_param))))


def comptabiliser_ot(ot, user=None):
    """Écriture du coût de l'OT clôturé (OD, source M8) ; retourne l'écriture ou None (motif conservé)."""
    from django.core.exceptions import ValidationError

    from accounting_kernel.models import AccountMove, AccountMoveLine, Journal
    from accounting_kernel.services import period_for_date, post_move
    from outbox.models import publish
    from referentiels.models import Account, Partner

    mo, pieces = ot.cout_main_oeuvre.quantize(CENT), ot.cout_pieces.quantize(CENT)
    total = mo + pieces
    centre = centre_actif(ot.actif)
    gr = est_gr(ot.actif)
    jour = ot.date_fin.date() if ot.date_fin else ot.date_demande
    move = None
    if total <= 0:
        ot.motif_ecriture = "Aucun coût à comptabiliser."
    else:
        try:
            with transaction.atomic():  # savepoint : jamais d'écriture brouillon partielle
                charge = Account.objects.get(code=COMPTE_GR) if gr else _compte("COMPTE_ENTRETIEN")
                partenaire = Partner.objects.filter(is_global_rental=True).first() if gr else None
                if gr and partenaire is None:
                    raise ValidationError("Compte 618 : aucun partenaire GLOBAL RENTAL au référentiel.")
                brouillon = AccountMove.objects.create(
                    journal=Journal.objects.get(code="OD"), period=period_for_date(jour), date=jour,
                    reference=ot.code, label=f"Coût maintenance {ot.code} — {ot.actif.code}"[:200],
                    source="M8", source_ref=str(ot.pk), status=AccountMove.Status.DRAFT,
                )
                AccountMoveLine.objects.create(
                    move=brouillon, account=charge, partner=partenaire, analytic_account=centre,
                    label=brouillon.label, debit=total, credit=0, order=1,
                )
                ordre = 2
                for montant, param, libelle in ((mo, "COMPTE_CONTREPARTIE_MO", "main-d'œuvre interne"),
                                                (pieces, "COMPTE_CONTREPARTIE_PIECES", "pièces sorties du stock")):
                    if montant > 0:
                        AccountMoveLine.objects.create(
                            move=brouillon, account=_compte(param), label=f"{ot.code} — {libelle}"[:200],
                            debit=0, credit=montant, order=ordre,
                        )
                        ordre += 1
                move = post_move(brouillon, user=user)
            ot.motif_ecriture = ""
        except (Journal.DoesNotExist, Account.DoesNotExist, ValidationError) as exc:
            msg = "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            ot.motif_ecriture = f"Écriture non passée : {msg}"[:255]
    ot.ecriture = move
    ot.save(update_fields=["ecriture", "motif_ecriture", "updated_at"])
    publish("maintenance.ot.cout", {
        "ot": ot.code, "actif": ot.actif.code, "centre": centre.code, "compte": COMPTE_GR if gr else
        str(int(get_param_maintenance("COMPTE_ENTRETIEN"))), "main_oeuvre": str(mo), "pieces": str(pieces),
        "total": str(total), "date": jour.isoformat(), "ecriture": move.number if move else None,
    })
    return move


def couts_annuels(annee):
    """Coûts des OT faits (terminés / clôturés / archivés) de l'année : par mois, par machine, par centre analytique."""
    from .models import OrdreTravail

    zero = Decimal("0")
    mois = [zero] * 12
    machines, centres = {}, {}
    ots = OrdreTravail.objects.filter(statut__in=STATUTS_FAITS, date_fin__year=annee).select_related(
        "actif", "actif__centre_analytique").order_by("actif__code")
    compte_entretien = str(int(get_param_maintenance("COMPTE_ENTRETIEN")))
    for ot in ots:
        m = ot.date_fin.month - 1
        centre = centre_actif(ot.actif)
        gr = est_gr(ot.actif)
        mac = machines.setdefault(ot.actif_id, {
            "actif": ot.actif.code, "designation": ot.actif.designation, "centre": centre.code, "gr": gr,
            "compte": COMPTE_GR if gr else compte_entretien, "nb_ot": 0, "main_oeuvre": zero, "pieces": zero,
            "mois": [zero] * 12, "total": zero,
        })
        cen = centres.setdefault(centre.code, {"centre": centre.code, "libelle": centre.label, "nb_ot": 0,
                                               "mois": [zero] * 12, "total": zero})
        cout = ot.cout_total.quantize(CENT)
        mac["nb_ot"] += 1
        mac["main_oeuvre"] += ot.cout_main_oeuvre.quantize(CENT)
        mac["pieces"] += ot.cout_pieces.quantize(CENT)
        mac["mois"][m] += cout
        mac["total"] += cout
        cen["nb_ot"] += 1
        cen["mois"][m] += cout
        cen["total"] += cout
        mois[m] += cout
    cumul, cumuls = zero, []
    for v in mois:
        cumul += v
        cumuls.append(cumul)
    rows = list(machines.values())
    return {
        "annee": annee, "devise": "XAF", "mois": mois, "cumul": cumuls, "machines": rows,
        "centres": sorted(centres.values(), key=lambda c: c["centre"]),
        "total": cumul,
        "totaux": {"gr_618": sum((r["total"] for r in rows if r["gr"]), zero),
                   "hors_gr": sum((r["total"] for r in rows if not r["gr"]), zero)},
    }
