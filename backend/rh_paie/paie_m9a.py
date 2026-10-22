"""Écarts M9-A (CDC M9.1-M9.3) : bulletin préparé depuis le contrat (grille, éléments fixes, prorata, absences),
historique de carrière, calendrier des déclarations sociales et fiscales."""

import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .services import _arrondi, _instantane, calculer_bulletin, integrer_temps, parametre
from config.i18n import tr

RUBRIQUE_SALAIRE = "SAL-BASE"
RUBRIQUE_ABSENCES = "ABS-NP"
PARAM_JOURS = "JOURS_PAIE_MOIS"


def fin_de_mois(jour):
    return date(jour.year, jour.month, calendar.monthrange(jour.year, jour.month)[1])


def _ajouter_mois(jour, n):
    annee, mois = divmod(jour.month - 1 + n, 12)
    return date(jour.year + annee, mois + 1, 1)


def contrat_en_vigueur(employe, periode):
    """Contrat actif (ou en période d'essai) couvrant au moins un jour du mois `periode`."""
    from .models import ContratTravail

    debut, fin = periode.replace(day=1), fin_de_mois(periode)
    return (
        ContratTravail.objects.filter(
            employe=employe, date_debut__lte=fin,
            statut__in=(ContratTravail.Statut.ACTIF, ContratTravail.Statut.EN_PERIODE_ESSAI),
        )
        .filter(Q(date_fin__isnull=True) | Q(date_fin__gte=debut))
        .select_related("grille")
        .order_by("-date_debut")
        .first()
    )


def est_expatrie(bulletin):
    contrat = contrat_en_vigueur(bulletin.employe, bulletin.periode)
    return bool(contrat and contrat.type == contrat.Type.EXPATRIE)


def grille_en_vigueur(grille, periode):
    """Version de la position de grille (convention, catégorie, classe, échelon) en vigueur au mois `periode`."""
    from .models import GrilleSalaire

    return (
        GrilleSalaire.objects.filter(
            convention=grille.convention, categorie=grille.categorie, classe=grille.classe, echelon=grille.echelon,
            date_effet__lte=periode,
        )
        .filter(Q(date_fin__isnull=True) | Q(date_fin__gte=periode))
        .order_by("-date_effet")
        .first()
    ) or grille


def _chevauchement(debut, fin, periode):
    a, b = max(debut, periode), min(fin, fin_de_mois(periode))
    return max(0, (b - a).days + 1)


def jours_non_remuneres(employe, periode):
    """Jours calendaires non payés du mois : absences validées non rémunérées + congés sans solde accordés."""
    from .models import Absence, DemandesConge

    periode = periode.replace(day=1)
    fin = fin_de_mois(periode)
    detail = [
        (a.code, _chevauchement(a.date_debut, a.date_fin, periode))
        for a in Absence.objects.filter(
            employe=employe, statut=Absence.Statut.VALIDEE, remuneree=False, date_debut__lte=fin, date_fin__gte=periode
        )
    ] + [
        (c.code, _chevauchement(c.date_debut, c.date_fin, periode))
        for c in DemandesConge.objects.filter(
            employe=employe, type=DemandesConge.Type.SANS_SOLDE, date_debut__lte=fin, date_fin__gte=periode,
            statut__in=(DemandesConge.Statut.APPROUVE, DemandesConge.Statut.VALIDE_RH),
        )
    ]
    return sum(j for _, j in detail), detail


@transaction.atomic
def preparer_bulletin(bulletin):
    """Construit le brut depuis le contrat en vigueur puis calcule le bulletin brouillon (idempotent).

    Salaire de base = grille en vigueur (si le contrat y est positionné) sinon salaire du contrat, proratisé en cas
    d'entrée ou de sortie dans le mois ; primes et indemnités récurrentes du contrat ; retenue des jours non
    rémunérés (diviseur `JOURS_PAIE_MOIS`) ; heures supplémentaires des pointages si la durée légale est paramétrée.
    Les autres lignes saisies à la main sont conservées.
    """
    from .models import BulletinLigne, BulletinPaie, ElementFixe, ParametrePaie, RubriquePaie

    bulletin = BulletinPaie.objects.select_for_update().select_related("employe").get(pk=bulletin.pk)
    if bulletin.statut != BulletinPaie.Statut.BROUILLON:
        raise ValidationError("Seul un bulletin brouillon peut être préparé.")
    periode, fin = bulletin.periode, fin_de_mois(bulletin.periode)
    contrat = contrat_en_vigueur(bulletin.employe, periode)
    if contrat is None:
        raise ValidationError(
            tr("Aucun contrat actif de %(employe_nom_complet)s sur %(periode)s : bulletin non préparable.") % {"employe_nom_complet": bulletin.employe.nom_complet, "periode": format(periode, '%m/%Y')}
        )
    grille = grille_en_vigueur(contrat.grille, periode) if contrat.grille_id else None
    salaire = grille.salaire_base if grille else contrat.salaire_base
    if not salaire or salaire <= 0:
        raise ValidationError("Salaire de base nul : renseigner le contrat ou sa position dans la grille de salaires.")

    presence = _chevauchement(contrat.date_debut, contrat.date_fin or fin, periode)
    base = salaire if presence >= fin.day else _arrondi(salaire * presence / fin.day)
    libelle = "Salaire de base" + (f" (grille {grille.code})" if grille else "")
    if presence < fin.day:
        libelle += f" — prorata {presence}/{fin.day} j"
    rubrique, _ = RubriquePaie.objects.get_or_create(
        code=RUBRIQUE_SALAIRE, defaults={"label": "Salaire de base", "nature": RubriquePaie.Nature.GAIN, "ordre": 1}
    )
    BulletinLigne.objects.update_or_create(
        bulletin=bulletin, rubrique=rubrique, defaults={"libelle": libelle[:150], "montant": base}
    )

    elements = ElementFixe.objects.filter(contrat=contrat)
    bulletin.lignes.filter(rubrique_id__in=elements.values("rubrique_id")).delete()
    cumul = {}
    for ef in elements.filter(date_debut__lte=fin).filter(
        Q(date_fin__isnull=True) | Q(date_fin__gte=periode)
    ).select_related("rubrique"):
        montant = ef.montant if ef.montant is not None else salaire * ef.taux / 100
        r, total = cumul.get(ef.rubrique_id, (ef.rubrique, Decimal("0")))
        cumul[ef.rubrique_id] = (r, total + montant)
    for r, total in cumul.values():
        BulletinLigne.objects.create(bulletin=bulletin, rubrique=r, libelle=r.label, montant=_arrondi(total))

    jours, detail = jours_non_remuneres(bulletin.employe, periode)
    rub_abs, _ = RubriquePaie.objects.get_or_create(
        code=RUBRIQUE_ABSENCES,
        defaults={"label": "Absences non rémunérées", "nature": RubriquePaie.Nature.GAIN, "ordre": 2},
    )
    snaps = []
    if jours:
        diviseur = parametre(PARAM_JOURS, periode)
        retenue = min(_arrondi(salaire * jours / diviseur.valeur), base)
        BulletinLigne.objects.update_or_create(
            bulletin=bulletin, rubrique=rub_abs,
            defaults={
                "libelle": f"Absences non rémunérées ({jours} j : {', '.join(c for c, _ in detail)})"[:150],
                "montant": -retenue,
            },
        )
        snaps.append(_instantane(diviseur, "parametre"))
    else:
        bulletin.lignes.filter(rubrique=rub_abs).delete()

    bulletin.salaire_base = salaire
    bulletin.baremes_utilises = [
        s for s in (bulletin.baremes_utilises or []) if not (s.get("type") == "parametre" and s.get("code") == PARAM_JOURS)
    ] + snaps
    bulletin.save(update_fields=["salaire_base", "baremes_utilises", "updated_at"])
    if ParametrePaie.objects.filter(code="DUREE_LEGALE_HEBDO", date_effet__lte=periode).exists():
        bulletin, _ = integrer_temps(bulletin)
        return bulletin
    return calculer_bulletin(bulletin)


@transaction.atomic
def enregistrer_evenement(employe, type_, date_effet, user, *, categorie="", fonction="", grille=None, salaire=None,
                          motif=""):
    """Événement de carrière : photographie avant / après et application à la fiche et au contrat en vigueur."""
    from .models import Employe, EvenementCarriere

    employe = Employe.objects.select_for_update().get(pk=employe.pk)
    contrat = contrat_en_vigueur(employe, date_effet)
    if (grille is not None or salaire is not None) and contrat is None:
        raise ValidationError("Aucun contrat en vigueur à cette date : la grille ou le salaire ne peut être appliqué.")
    ev = EvenementCarriere(
        employe=employe, contrat=contrat, type=type_, date_effet=date_effet, motif=motif,
        cree_par=user if getattr(user, "is_authenticated", False) else None,
        categorie_avant=employe.categorie, fonction_avant=employe.fonction,
        grille_avant=contrat.grille if contrat else None, salaire_avant=contrat.salaire_base if contrat else None,
    )
    if grille is not None and not categorie:
        categorie = grille.categorie
    if categorie:
        employe.categorie = categorie
    if fonction:
        employe.fonction = fonction
    employe.save(update_fields=["categorie", "fonction", "updated_at"])
    if contrat is not None:
        champs = []
        if grille is not None:
            contrat.grille, contrat.salaire_base = grille, grille.salaire_base
            champs = ["grille", "salaire_base"]
        elif salaire is not None:
            contrat.salaire_base = salaire
            champs = ["salaire_base"]
        if champs:
            contrat.save(update_fields=champs + ["updated_at"])
    ev.categorie_apres, ev.fonction_apres = employe.categorie, employe.fonction
    ev.grille_apres = contrat.grille if contrat else None
    ev.salaire_apres = contrat.salaire_base if contrat else None
    ev.save()
    return ev


# --------------------------------------------------------------------------------------------
# Calendrier des déclarations sociales et fiscales (dates limites paramétrables, alertes)
# --------------------------------------------------------------------------------------------
def date_limite(echeance, periode_fin):
    """Date limite de dépôt pour une période dont le dernier mois est `periode_fin` (1er du mois)."""
    if echeance.periodicite == echeance.Periodicite.ANNUELLE:
        annee, mois = periode_fin.year + 1, echeance.mois or 1
    else:
        suivant = _ajouter_mois(periode_fin, 1)
        annee, mois = suivant.year, suivant.month
    return date(annee, mois, min(echeance.jour, calendar.monthrange(annee, mois)[1]))


def periodes_echeance(echeance, aujourdhui, retard=90, horizon=90):
    """(début, fin, date limite) des périodes dont la date limite tombe dans [aujourd'hui - retard, + horizon]."""
    duree = {"mensuelle": 0, "trimestrielle": 2, "annuelle": 11}[echeance.periodicite]
    origine = _ajouter_mois(aujourdhui.replace(day=1), -27)
    sortie = []
    for i in range(30):
        debut = _ajouter_mois(origine, i)
        if (duree == 2 and debut.month % 3 != 1) or (duree == 11 and debut.month != 1):
            continue
        fin = _ajouter_mois(debut, duree)
        limite = date_limite(echeance, fin)
        if aujourdhui - timedelta(days=retard) <= limite <= aujourdhui + timedelta(days=horizon):
            sortie.append((debut, fin, limite))
    return sortie


def calendrier_declarations(aujourdhui=None, horizon=90):
    """Échéances déclaratives proches ou dépassées, avec l'état de dépôt (déclaration générée couvrant la période)."""
    from .models import DeclarationSociale, EcheanceDeclaration

    aujourdhui = aujourdhui or timezone.localdate()
    items = []
    for ech in EcheanceDeclaration.objects.filter(actif=True):
        for debut, fin, limite in periodes_echeance(ech, aujourdhui, horizon=horizon):
            items.append({
                "echeance": str(ech.pk), "code": ech.code, "type": ech.type_declaration, "libelle": ech.libelle,
                "periode_debut": debut, "periode_fin": fin, "date_limite": limite,
                "jours": (limite - aujourdhui).days, "provisoire": ech.est_provisoire,
                "deposee": DeclarationSociale.objects.filter(
                    type=ech.type_declaration, periode_debut__lte=debut, periode_fin__gte=fin
                ).exists(),
            })
    return sorted(items, key=lambda i: (i["date_limite"], i["code"]))


def alertes_echeances_declarations(band):
    """Alertes du tableau des échéances : déclarations non déposées à J-90 … en retard."""
    sortie = []
    for i in calendrier_declarations():
        if i["deposee"]:
            continue
        periode = f"{i['periode_debut']:%m/%Y}"
        if i["periode_fin"] != i["periode_debut"]:
            periode += f" à {i['periode_fin']:%m/%Y}"
        sortie.append({
            "type": "declaration_paie", "code": i["code"], "libelle": f"{i['libelle']} — période {periode}",
            "date_echeance": i["date_limite"], "bande": band(i["jours"]), "jours": i["jours"],
            "statut": "en_retard" if i["jours"] < 0 else "a_deposer",
        })
    return sortie
