"""Écarts M9-B (CDC M9 aval M10 / M11 / M3) : comptes de paie paramétrables par organisme, ventilation analytique de la
paie par affaire, provision des congés payés, coût de main-d'œuvre chargé des pointages."""

from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from .paie_m9a import contrat_en_vigueur, fin_de_mois, grille_en_vigueur
from .services import _arrondi, _compte, _impot_bulletin, baremes_en_vigueur, parametre, ventilation_bulletin
from config.i18n import tr

#: Comptes repris tant qu'aucun compte de paie n'est paramétré (comportement historique : tout organisme en 431000).
COMPTES_DEFAUT = {
    "brut": "661000", "patronal": "664000", "net": "421000", "organismes": "431000", "impot": "431000",
    "autres_retenues": "431000", "provision_charge": "661000",
}


def compte_paie(role, organisme=""):
    """Compte du rôle (et de l'organisme pour les cotisations) : paramétrage d'abord, sinon compte par défaut."""
    from .models import ComptePaie

    if organisme:
        cp = ComptePaie.objects.filter(role=role, organisme=organisme).select_related("compte").first()
        if cp:
            return cp.compte
    cp = ComptePaie.objects.filter(role=role, organisme="").select_related("compte").first()
    if cp:
        return cp.compte
    if role not in COMPTES_DEFAUT:
        raise ValidationError(
            tr("Compte de paie « %(label)s » non paramétré : le renseigner dans les comptes de paie.") % {"label": ComptePaie.Role(role).label}
        )
    return _compte(COMPTES_DEFAUT[role])


def repartition_affaires(employe, periode):
    """[(compte analytique, part)] des heures du mois pointées sur des OF d'affaire, rapportées aux heures du mois."""
    from commercial.models import Affaire
    from operations.models import PointageChantier

    from .models import SaisieTemps

    periode = periode.replace(day=1)
    fin = fin_de_mois(periode)
    total = SaisieTemps.objects.filter(employe=employe, date__gte=periode, date__lte=fin).aggregate(t=Sum("heures"))["t"]
    if not total:
        return []
    lignes = (
        PointageChantier.objects.filter(
            saisie_temps__employe=employe, saisie_temps__date__gte=periode, saisie_temps__date__lte=fin,
            ordre__affaire__isnull=False,
        )
        .values("ordre__affaire")
        .annotate(h=Sum("saisie_temps__heures"))
        .order_by("ordre__affaire")
    )
    return [
        (Affaire.objects.get(pk=l["ordre__affaire"]).assurer_compte_analytique(), Decimal(l["h"]) / Decimal(total))
        for l in lignes
    ]


def _ventiler(montant, parts):
    """Montant réparti par compte analytique ; le reste (heures hors affaire, arrondis) reste sans axe."""
    sortie, reste = [], Decimal(montant)
    for analytic, part in parts:
        m = _arrondi(Decimal(montant) * part)
        if m:
            sortie.append((analytic, m))
            reste -= m
    if reste:
        sortie.append((None, reste))
    return sortie


def lignes_ecriture_paie(bulletin):
    """(compte, débit, crédit, compte analytique, libellé) de l'écriture d'un bulletin, équilibrée par construction.

    Débit brut et charges patronales ventilés par affaire au prorata des heures pointées ; crédit du net, des
    cotisations par organisme (compte paramétré), de l'impôt retenu et des autres retenues.
    """
    brut, net, patronal = bulletin.brut, bulletin.net, bulletin.charges_patronales
    parts = repartition_affaires(bulletin.employe, bulletin.periode)
    lignes = [(compte_paie("brut"), m, 0, a, "Salaires bruts") for a, m in _ventiler(brut, parts)]
    lignes += [(compte_paie("patronal"), m, 0, a, "Charges patronales") for a, m in _ventiler(patronal, parts)]
    lignes.append((compte_paie("net"), 0, net, None, "Net à payer"))
    credits = defaultdict(Decimal)
    for v in ventilation_bulletin(bulletin):
        credits[compte_paie("organismes", v["organisme"])] += v["montant"]
    impot = _impot_bulletin(bulletin)
    if impot:
        credits[compte_paie("impot")] += impot
    ecart = (brut - net) + patronal - sum(credits.values(), Decimal("0"))
    if ecart:  # retenues saisies hors barème (avances, oppositions…) et écarts d'arrondi
        credits[compte_paie("autres_retenues")] += ecart
    for compte, m in credits.items():
        if m > 0:
            lignes.append((compte, 0, m, None, "Cotisations et retenues"))
        elif m < 0:
            lignes.append((compte, -m, 0, None, "Cotisations et retenues"))
    return lignes


@transaction.atomic
def provisionner_conges(periode, user=None):
    """Dotation mensuelle aux provisions pour congés payés (journal PAI), une seule fois par mois.

    Montant = brut des bulletins validés ou clôturés du mois × `PROVISION_CP_TAUX` (paramètre provisoire).
    """
    from accounting_kernel.models import AccountMove, AccountMoveLine, Journal
    from accounting_kernel.services import period_for_date, post_move

    from .models import BulletinPaie, ProvisionConges

    periode = periode.replace(day=1)
    if ProvisionConges.objects.select_for_update().filter(periode=periode).exists():
        raise ValidationError("Provision des congés payés déjà passée pour ce mois.")
    base = BulletinPaie.objects.filter(
        periode=periode, statut__in=(BulletinPaie.Statut.VALIDE, BulletinPaie.Statut.CLOTURE)
    ).aggregate(t=Sum("brut"))["t"]
    if not base:
        raise ValidationError("Aucun bulletin validé ce mois : rien à provisionner.")
    taux = parametre("PROVISION_CP_TAUX", periode)
    montant = _arrondi(base * taux.valeur / 100)
    charge, dette = compte_paie("provision_charge"), compte_paie("provision_dette")
    try:
        journal = Journal.objects.get(code="PAI")
    except Journal.DoesNotExist:
        raise ValidationError("Journal de paie PAI absent (seed_accounting).")
    jour = fin_de_mois(periode)
    move = AccountMove.objects.create(
        journal=journal, period=period_for_date(jour), date=jour, reference=f"PCP-{periode:%Y%m}",
        label=f"Provision congés payés {periode:%m/%Y}", source="M9", source_ref=f"PCP-{periode:%Y%m}",
    )
    AccountMoveLine.objects.create(move=move, account=charge, debit=montant, credit=0, order=0, label="Dotation congés payés")
    AccountMoveLine.objects.create(move=move, account=dette, debit=0, credit=montant, order=1, label="Congés payés à payer")
    move = post_move(move, user=user)
    return ProvisionConges.objects.create(
        periode=periode, base_brut=base, taux=taux.valeur, taux_provisoire=taux.est_provisoire, montant=montant,
        move=move, created_by=user if getattr(user, "is_authenticated", False) else None,
    )


def taux_horaire_charge(employe, jour):
    """Coût horaire chargé : (salaire de référence × (1 + taux patronaux en vigueur)) ÷ heures mensuelles légales.

    Approximation de gestion (plafonds de cotisation ignorés) ; None si contrat ou durée légale absents.
    """
    periode = jour.replace(day=1)
    contrat = contrat_en_vigueur(employe, periode)
    if contrat is None:
        return None
    grille = grille_en_vigueur(contrat.grille, periode) if contrat.grille_id else None
    salaire = grille.salaire_base if grille else contrat.salaire_base
    try:
        legale = parametre("DUREE_LEGALE_HEBDO", periode)
    except ValidationError:
        return None
    expatrie = contrat.type == contrat.Type.EXPATRIE
    patronal = sum(
        (b.taux for b in baremes_en_vigueur(periode)
         if b.nature == b.Nature.PATRONALE and not (expatrie and b.exclure_expatries)),
        Decimal("0"),
    )
    if not salaire or not legale.valeur:
        return None
    return _arrondi(salaire * (1 + patronal / 100) / (legale.valeur * Decimal("52") / Decimal("12")))


def cout_main_oeuvre(debut, fin, ordre=None):
    """Coût chargé des pointages transférés en paie, par OF et affaire (aval M3 / M11)."""
    from operations.models import PointageChantier

    qs = PointageChantier.objects.filter(
        saisie_temps__isnull=False, date__gte=debut, date__lte=fin
    ).select_related("ordre__affaire", "saisie_temps")
    if ordre:
        qs = qs.filter(ordre_id=ordre)
    par_of = {}
    for p in qs:
        ligne = par_of.setdefault(p.ordre_id, {
            "ordre": str(p.ordre_id), "ordre_code": p.ordre.code,
            "affaire": p.ordre.affaire.code if p.ordre.affaire_id else None,
            "heures": Decimal("0"), "cout": Decimal("0"), "heures_non_valorisees": Decimal("0"),
            "heures_prevues": p.ordre.calculated_hours,
        })
        ligne["heures"] += p.saisie_temps.heures
        if p.saisie_temps.cout_charge is None:
            ligne["heures_non_valorisees"] += p.saisie_temps.heures
        else:
            ligne["cout"] += p.saisie_temps.cout_charge
    sortie = sorted(par_of.values(), key=lambda l: l["ordre_code"])
    from operations.models import OrdreFabrication

    from .formation_m9c import depassement_mo

    ordres = OrdreFabrication.objects.in_bulk([l["ordre"] for l in sortie])
    for ligne in sortie:
        ligne["depassement"] = depassement_mo(ordres[ligne["ordre"]]) if ligne["ordre"] in ordres else False
    for ligne in sortie:  # montants en chaînes (pas de flottant JSON)
        for champ in ("heures", "cout", "heures_non_valorisees", "heures_prevues"):
            ligne[champ] = None if ligne[champ] is None else str(ligne[champ])
    return sortie


def valoriser_saisie(saisie):
    """Pose le coût chargé d'une saisie de temps (appelé au transfert du pointage M3 vers la paie)."""
    taux = taux_horaire_charge(saisie.employe, saisie.date)
    if taux is not None:
        saisie.cout_charge = _arrondi(taux * saisie.heures)
        saisie.save(update_fields=["cout_charge", "updated_at"])
    return saisie
