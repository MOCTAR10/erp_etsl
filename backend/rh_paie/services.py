"""Droits métier M9 — RH & Paie (RF-ERP-80…83).

RH : cercle personnel (contrats, congés, formations, sanctions, habilitations).
Paie : cercle restreint (bulletins, salaires) — la paie est sensible (RF-33).
Montants (salaire, brut, net) masqués hors rôles autorisés (pattern RF-59).
"""

import calendar
import json
import uuid
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
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


AVERTISSEMENT_PROVISOIRE = (
    "Taux provisoires : ce document utilise des barèmes non confirmés par ETSL / le cabinet de paie "
    "({codes}). Ne pas l'utiliser pour une déclaration officielle avant confirmation."
)


def _instantane(bareme, type_):
    """Photographie d'un barème au moment du calcul (version, valeur, statut)."""
    snap = {
        "type": type_, "id": str(bareme.pk), "code": bareme.code, "date_effet": bareme.date_effet.isoformat(),
        "statut": bareme.statut_valeur,
    }
    if type_ == "cotisation":
        snap.update(taux=str(bareme.taux), plafond=str(bareme.plafond) if bareme.plafond is not None else None)
    elif type_ == "parametre":
        snap.update(valeur=str(bareme.valeur))
    else:
        snap.update(abattement_pct=str(bareme.abattement_pct), tranches=bareme.tranches,
                    abattement_plafond_annuel=None if bareme.abattement_plafond_annuel is None
                    else str(bareme.abattement_plafond_annuel))
    return snap


def avertissement_provisoire(codes):
    """Texte d'avertissement si au moins un barème utilisé est provisoire, sinon chaîne vide."""
    return AVERTISSEMENT_PROVISOIRE.format(codes=", ".join(codes)) if codes else ""


def _etat(obj):
    """Valeurs auditables d'un barème / paramètre (JSON-compatible)."""
    from django.forms.models import model_to_dict

    return json.loads(json.dumps(
        {k: v for k, v in model_to_dict(obj).items() if k not in ("confirme_par",)}, default=str
    ))


def tracer_changement(obj, objet, action, user, avant=None):
    from .models import HistoriqueBareme

    return HistoriqueBareme.objects.create(
        objet=objet, objet_id=obj.pk, code=obj.code, action=action, avant=avant,
        apres=None if action == "suppression" else _etat(obj), par=user if getattr(user, "is_authenticated", False) else None,
    )


def bareme_fige(obj):
    """Vrai si un bulletin non brouillon a été calculé avec ce barème (valeurs à ne plus modifier)."""
    from .models import BulletinPaie

    fige = BulletinPaie.objects.exclude(statut=BulletinPaie.Statut.BROUILLON).exclude(baremes_utilises=[])
    return any(
        str(obj.pk) in [b.get("id") for b in (bul.baremes_utilises or [])] for bul in fige.only("baremes_utilises")
    )


@transaction.atomic
def confirmer_valeur(obj, objet, user):
    """Passe un barème / paramètre à « confirmé » (utilisateur et date posés côté serveur)."""
    avant = _etat(obj)
    obj.statut_valeur = obj.StatutValeur.CONFIRME
    obj.confirme_par = user
    obj.confirme_le = timezone.now()
    obj.save(update_fields=["statut_valeur", "confirme_par", "confirme_le"])
    tracer_changement(obj, objet, "confirmation", user, avant)
    return obj


@transaction.atomic
def reviser_valeur(obj, objet, user, date_effet, champs):
    """Nouvelle version à `date_effet` : l'ancienne est close la veille (conservée pour les bulletins passés)."""
    if date_effet <= obj.date_effet:
        raise ValidationError("La date d'effet de la nouvelle version doit être postérieure à l'actuelle.")
    if obj.date_fin and obj.date_fin < date_effet:
        raise ValidationError("La version actuelle est déjà close avant cette date.")
    avant = _etat(obj)
    nouvelle = type(obj).objects.get(pk=obj.pk)
    nouvelle.pk = None
    nouvelle.id = uuid.uuid4()
    nouvelle._state.adding = True
    for champ, valeur in champs.items():
        setattr(nouvelle, champ, valeur)
    nouvelle.date_effet, nouvelle.date_fin = date_effet, None
    nouvelle.statut_valeur = nouvelle.StatutValeur.PROVISOIRE
    nouvelle.confirme_par, nouvelle.confirme_le = None, None
    nouvelle.full_clean()
    obj.date_fin = date_effet - timedelta(days=1)
    obj.save(update_fields=["date_fin"])
    nouvelle.save()
    tracer_changement(obj, objet, "cloture_version", user, avant)
    tracer_changement(nouvelle, objet, "revision", user)
    return nouvelle


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
    utilises = [s for s in (bulletin.baremes_utilises or []) if s.get("type") == "parametre"]  # paramètres d'intégration temps
    from .paie_m9a import est_expatrie

    expatrie = est_expatrie(bulletin)
    for bareme in baremes_en_vigueur(bulletin.periode):
        if expatrie and bareme.exclure_expatries:
            continue  # cotisation non applicable aux contrats expatriés (paramètre du barème)
        utilises.append(_instantane(bareme, "cotisation"))
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
        utilises.append(_instantane(bareme, "impot"))
        base = gains - (cotisations if bareme.cotisations_deductibles else Decimal("0"))
        abattement = base * bareme.abattement_pct / 100
        if bareme.abattement_plafond_annuel is not None:  # forfait annuel maximal, ramené au mois
            abattement = min(abattement, bareme.abattement_plafond_annuel / 12)
        base = max(base - abattement, Decimal("0"))
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
    bulletin.baremes_utilises = utilises
    bulletin.save(update_fields=["brut", "net", "charges_patronales", "baremes_utilises", "updated_at"])
    # l'instance de l'appelant reflète le résultat (sérialisation de la réponse API)
    for champ in ("brut", "net", "charges_patronales", "baremes_utilises", "updated_at"):
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

    from .compta_m9b import lignes_ecriture_paie

    lignes = lignes_ecriture_paie(bulletin)  # comptes paramétrés (ou défaut), ventilation par affaire
    jour = date(bulletin.periode.year, bulletin.periode.month,
                calendar.monthrange(bulletin.periode.year, bulletin.periode.month)[1])
    move = AccountMove.objects.create(
        journal=journal, period=period_for_date(jour), date=jour,
        reference=bulletin.code, label=f"Paie {bulletin.periode:%m/%Y} — {bulletin.employe.nom_complet}",
        source="M9", source_ref=bulletin.code,
    )
    for ordre, (compte, debit, credit, analytic, libelle) in enumerate(lignes):
        if debit or credit:
            AccountMoveLine.objects.create(
                move=move, account=compte, debit=debit, credit=credit, order=ordre, analytic_account=analytic,
                label=f"Paie {bulletin.code} — {libelle}"[:200],
            )
    posted = post_move(move, user=user)
    bulletin.move = posted
    bulletin.save(update_fields=["move", "updated_at"])
    return posted


# --------------------------------------------------------------------------------------------
# Bulletin PDF archivé en GED (≥ 10 ans) et virement CFONB des salaires (clôture M9)
# --------------------------------------------------------------------------------------------
RETENTION_BULLETIN_ANS = 10
TYPE_GED_BULLETIN = "bulletins_de_paie"


def bulletin_pdf(bulletin):
    """PDF du bulletin (reportlab) — l'avertissement « taux provisoires » y figure tant qu'un barème l'est."""
    import io

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, title=bulletin.code)
    e = bulletin.employe
    fm = lambda v: f"{v:,.0f}".replace(",", " ")  # noqa: E731
    story = [
        Paragraph(f"Bulletin de paie — {bulletin.periode:%m/%Y}", styles["Title"]),
        Paragraph(f"{bulletin.code} · {e.nom_complet} · matricule {e.code} · {e.fonction or e.categorie}", styles["Normal"]),
        Paragraph(f"N° CNSS : {e.numero_securite_sociale or '—'} · CNAMGS : {e.matricule_cnps or '—'} · parts fiscales : {e.parts_fiscales}", styles["Normal"]),
        Spacer(1, 6 * mm),
    ]
    rows = [["Rubrique", "Gains", "Retenues"]]
    for l in bulletin.lignes.select_related("rubrique").order_by("rubrique__nature", "rubrique__ordre"):
        gain = l.rubrique.nature == "gain"
        rows.append([l.libelle, fm(l.montant) if gain else "", "" if gain else fm(l.montant)])
    rows.append(["Brut", fm(bulletin.brut), ""])
    rows.append(["Charges patronales (information)", "", fm(bulletin.charges_patronales)])
    rows.append(["NET À PAYER (FCFA)", fm(bulletin.net), ""])
    table = Table(rows, colWidths=[110 * mm, 35 * mm, 35 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#12308f")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    story.append(table)
    avertissement = avertissement_provisoire(bulletin.baremes_provisoires)
    if avertissement:
        story += [Spacer(1, 6 * mm), Paragraph(f"<font color='#d4142a'><b>AVERTISSEMENT</b> — {avertissement}</font>", styles["Normal"])]
    story += [Spacer(1, 6 * mm), Paragraph("Document à conserver sans limitation de durée (archivage ETSL : 10 ans minimum).", styles["Italic"])]
    doc.build(story)
    return buf.getvalue()


@transaction.atomic
def archiver_bulletin(bulletin, user=None):
    """Scelle le PDF du bulletin en GED (type « bulletins de paie », conservation ≥ 10 ans, accès restreint RH)."""
    import hashlib

    from django.core.files.base import ContentFile

    from documents.models import Document, DocumentType, Version

    from .models import BulletinPaie

    bulletin = BulletinPaie.objects.select_for_update().get(pk=bulletin.pk)
    if bulletin.statut not in (BulletinPaie.Statut.VALIDE, BulletinPaie.Statut.CLOTURE):
        raise ValidationError("Seul un bulletin validé ou clôturé peut être archivé.")
    if bulletin.document_id:
        raise ValidationError("Bulletin déjà archivé en GED (document scellé).")
    type_doc, _ = DocumentType.objects.get_or_create(
        code=TYPE_GED_BULLETIN,
        defaults={"label": "Bulletins de paie", "retention_years": RETENTION_BULLETIN_ANS, "is_restricted_rh": True},
    )
    if (type_doc.retention_years or 0) < RETENTION_BULLETIN_ANS or not type_doc.is_restricted_rh:
        type_doc.retention_years = max(type_doc.retention_years or 0, RETENTION_BULLETIN_ANS)
        type_doc.is_restricted_rh = True
        type_doc.save(update_fields=["retention_years", "is_restricted_rh"])
    contenu = bulletin_pdf(bulletin)
    sha = hashlib.sha256(contenu).hexdigest()
    nom = f"{bulletin.code}_{bulletin.periode:%Y-%m}.pdf"
    document = Document.objects.create(
        title=f"Bulletin de paie {bulletin.periode:%m/%Y} — {bulletin.employe.nom_complet}",
        status=Document.Status.ARCHIVED, archived_at=timezone.now(), type=type_doc,
        document_date=bulletin.periode, counterparty=bulletin.employe.nom_complet, reference=bulletin.code,
        keywords=["paie", "bulletin", bulletin.employe.code], sha256=sha, created_by=user,
    )
    version = Version.objects.create(
        document=document, number=1, file=ContentFile(contenu, name=nom), sha256=sha, size=len(contenu),
        original_filename=nom, created_by=user,
    )
    document.current_version = version
    document.save(update_fields=["current_version"])
    bulletin.document = document
    bulletin.save(update_fields=["document", "updated_at"])
    return bulletin


def _num(valeur, n):
    return str(valeur).zfill(n)[-n:] if str(valeur).isdigit() else str(valeur).ljust(n)[:n]


def _centimes(montant):
    return int((Decimal(montant) * 100).to_integral_value())


def cfonb160(compte, date_execution, lignes):
    """Fichier de virements CFONB 160 : en-tête (03) · un destinataire (06) par salarié · total (08).

    `lignes` = [(référence, nom, domiciliation, banque, guichet, compte, montant, libellé)].
    GABARIT STANDARD à faire valider par la banque d'ETSL (positions exactes variables selon les banques) — réserve M9.
    """

    def ligne(champs):
        buf = [" "] * 160
        for debut, valeur in champs:  # debut = position 1-indexée
            for i, c in enumerate(valeur):
                buf[debut - 1 + i] = c
        return "".join(buf)

    jour = date_execution.strftime("%d%m") + str(date_execution.year)[-1]
    sortie = [ligne([
        (1, "0302"), (13, _num(compte.numero_emetteur, 6)), (25, jour), (30, compte.raison_sociale.upper().ljust(24)[:24]),
        (87, _num(compte.code_guichet, 5)), (92, _num(compte.numero_compte, 11)), (150, _num(compte.code_banque, 5)),
    ])]
    total = 0
    for ref, nom, domic, banque, guichet, cpt, montant, libelle in lignes:
        c = _centimes(montant)
        total += c
        sortie.append(ligne([
            (1, "0602"), (13, _num(compte.numero_emetteur, 6)), (25, ref.ljust(12)[:12]), (37, nom.upper().ljust(24)[:24]),
            (61, domic.upper().ljust(24)[:24]), (87, _num(guichet, 5)), (92, _num(cpt, 11)), (103, str(c).zfill(16)),
            (119, libelle.upper().ljust(31)[:31]), (150, _num(banque, 5)),
        ]))
    sortie.append(ligne([(1, "0802"), (13, _num(compte.numero_emetteur, 6)), (103, str(total).zfill(16))]))
    return "\n".join(sortie) + "\n", Decimal(total) / 100


@transaction.atomic
def generer_virement(periode, compte, date_execution, user=None):
    """Ordre de virement des bulletins validés/clôturés du mois, une seule fois par bulletin (pas de doublon)."""
    import hashlib

    from .models import BulletinPaie, OrdreVirement

    periode = periode.replace(day=1)
    if not compte.actif:
        raise ValidationError("Compte émetteur inactif.")
    bulletins = list(
        BulletinPaie.objects.select_for_update(of=("self",))
        .select_related("employe")
        .filter(periode=periode, statut__in=(BulletinPaie.Statut.VALIDE, BulletinPaie.Statut.CLOTURE),
                ordre_virement__isnull=True, net__gt=0)
        .order_by("employe__nom")
    )
    if not bulletins:
        raise ValidationError("Aucun bulletin validé à virer pour cette période (ou déjà viré).")
    sans_rib = [b.employe.nom_complet for b in bulletins if not b.employe.rib_complet]
    if sans_rib:
        raise ValidationError("RIB incomplet pour : " + ", ".join(sans_rib) + ".")
    contenu, total = cfonb160(compte, date_execution, [
        (b.code, b.employe.nom_complet, b.employe.banque_nom, b.employe.rib_banque, b.employe.rib_guichet,
         b.employe.rib_compte, b.net, f"SALAIRE {periode:%m/%Y}")
        for b in bulletins
    ])
    ordre = OrdreVirement.objects.create(
        periode=periode, compte=compte, date_execution=date_execution, nb_virements=len(bulletins), total=total,
        contenu=contenu, sha256=hashlib.sha256(contenu.encode("ascii", "replace")).hexdigest(), created_by=user,
    )
    BulletinPaie.objects.filter(pk__in=[b.pk for b in bulletins]).update(ordre_virement=ordre)
    return ordre


# --------------------------------------------------------------------------------------------
# Pointages M3 -> heures supplémentaires, déclarations sans ressaisie, reporting RH (clôture M9)
# --------------------------------------------------------------------------------------------
HS_RUBRIQUE = "HS-TEMPS"
HS_PARAMETRES = ("DUREE_LEGALE_HEBDO", "HS_MAJ_1", "HS_MAJ_2", "HS_SEUIL_2", "MAJ_NUIT", "MAJ_ASTREINTE")
#: type de pointage, paramètre (% du taux horaire), rubrique, libellé — valorisés seulement si le taux est saisi.
PRIMES_HORAIRES = (
    ("nuit", "MAJ_NUIT", "NUIT-TEMPS", "Majoration des heures de nuit"),
    ("astreinte", "MAJ_ASTREINTE", "ASTR-TEMPS", "Heures d'astreinte"),
)


def parametre(code, periode):
    """Paramètre de paie en vigueur à `periode` (ParametrePaie versionné) ; absent => erreur explicite."""
    from django.db.models import Q

    from .models import ParametrePaie

    p = (
        ParametrePaie.objects.filter(code=code, date_effet__lte=periode)
        .filter(Q(date_fin__isnull=True) | Q(date_fin__gte=periode))
        .order_by("-date_effet")
        .first()
    )
    if p is None:
        raise ValidationError(f"Paramètre de paie « {code} » absent : à saisir dans le paramétrage de la paie.")
    return p


def heures_supplementaires(employe, periode, salaire_base):
    """Heures sup. du mois depuis les pointages (M3 / saisies), calculées PAR SEMAINE ISO.

    Au-delà de la durée légale (`DUREE_LEGALE_HEBDO`) : tranche 1 majorée de `HS_MAJ_1` % jusqu'au seuil
    `HS_SEUIL_2`, tranche 2 majorée de `HS_MAJ_2` %. Tous les paramètres sont des données (provisoires tant que non
    confirmées). Retourne un dict (heures, montant, paramètres utilisés)."""
    from collections import defaultdict

    from .models import SaisieTemps

    legale = parametre("DUREE_LEGALE_HEBDO", periode)
    maj1, maj2, seuil2 = parametre("HS_MAJ_1", periode), parametre("HS_MAJ_2", periode), parametre("HS_SEUIL_2", periode)
    saisies = SaisieTemps.objects.filter(
        employe=employe, date__year=periode.year, date__month=periode.month,
        type__in=(SaisieTemps.Type.NORMAL, SaisieTemps.Type.SUPPLEMENTAIRE),
    )
    semaines = defaultdict(Decimal)
    for st in saisies:
        semaines[st.date.isocalendar()[:2]] += st.heures
    h1 = h2 = Decimal("0")
    for total in semaines.values():
        h1 += max(Decimal("0"), min(total, seuil2.valeur) - legale.valeur)
        h2 += max(Decimal("0"), total - seuil2.valeur)
    taux_horaire = Decimal(salaire_base) / (legale.valeur * Decimal("52") / Decimal("12"))
    montant = _arrondi(
        h1 * taux_horaire * (1 + maj1.valeur / 100) + h2 * taux_horaire * (1 + maj2.valeur / 100)
    )
    return {
        "heures_tranche_1": h1, "heures_tranche_2": h2, "taux_horaire": _arrondi(taux_horaire), "montant": montant,
        "heures_productives": sum(semaines.values(), Decimal("0")),
        "parametres": [legale, maj1, maj2, seuil2],
        "saisies": list(saisies),
    }


@transaction.atomic
def integrer_temps(bulletin):
    """Intègre les heures sup. des pointages du mois dans le bulletin brouillon (gain `HS-TEMPS`) puis recalcule."""
    from .models import BulletinLigne, BulletinPaie, RubriquePaie, SaisieTemps

    bulletin = BulletinPaie.objects.select_for_update().get(pk=bulletin.pk)
    if bulletin.statut != BulletinPaie.Statut.BROUILLON:
        raise ValidationError("Seul un bulletin brouillon peut recevoir les heures des pointages.")
    res = heures_supplementaires(bulletin.employe, bulletin.periode, bulletin.salaire_base)
    rubrique, _ = RubriquePaie.objects.get_or_create(
        code=HS_RUBRIQUE,
        defaults={"label": "Heures supplémentaires (pointages)", "nature": RubriquePaie.Nature.GAIN, "ordre": 20},
    )
    if res["montant"] > 0:
        h = res["heures_tranche_1"] + res["heures_tranche_2"]
        BulletinLigne.objects.update_or_create(
            bulletin=bulletin, rubrique=rubrique,
            defaults={"libelle": f"Heures supplémentaires ({h} h)", "montant": res["montant"]},
        )
    else:
        bulletin.lignes.filter(rubrique=rubrique).delete()
    primes = _primes_horaires(bulletin, res["taux_horaire"])
    SaisieTemps.objects.filter(pk__in=[s.pk for s in res["saisies"]]).update(statut=SaisieTemps.Statut.TRANSFERE_PAIE)
    snaps = [
        s for s in (bulletin.baremes_utilises or [])
        if not (s.get("type") == "parametre" and s.get("code") in HS_PARAMETRES)
    ]
    bulletin.baremes_utilises = snaps + [_instantane(p, "parametre") for p in res["parametres"] + primes]
    bulletin.save(update_fields=["baremes_utilises", "updated_at"])
    return calculer_bulletin(bulletin), res


def _primes_horaires(bulletin, taux_horaire):
    """Heures de nuit et d'astreinte du mois, valorisées au % du taux horaire si le paramètre existe (sinon ignorées)."""
    from django.db.models import Sum

    from .models import BulletinLigne, RubriquePaie, SaisieTemps

    utilises = []
    for type_, code, rub, label in PRIMES_HORAIRES:
        heures = SaisieTemps.objects.filter(
            employe=bulletin.employe, date__year=bulletin.periode.year, date__month=bulletin.periode.month, type=type_,
        ).aggregate(t=Sum("heures"))["t"] or Decimal("0")
        rubrique, _ = RubriquePaie.objects.get_or_create(
            code=rub, defaults={"label": label, "nature": RubriquePaie.Nature.GAIN, "ordre": 21}
        )
        try:
            taux = parametre(code, bulletin.periode)
        except ValidationError:
            taux = None
        if heures and taux is not None:
            BulletinLigne.objects.update_or_create(
                bulletin=bulletin, rubrique=rubrique,
                defaults={"libelle": f"{label} ({heures} h à {taux.valeur} %)",
                          "montant": _arrondi(heures * taux_horaire * taux.valeur / 100)},
            )
            utilises.append(taux)
        else:
            bulletin.lignes.filter(rubrique=rubrique).delete()
    return utilises


def ventilation_bulletin(bulletin):
    """Cotisations du bulletin ventilées par organisme / nature, recalculées depuis les barèmes de l'instantané."""
    from .models import BaremeCotisation

    ids = [s["id"] for s in (bulletin.baremes_utilises or []) if s.get("type") == "cotisation"]
    sortie = []
    for b in BaremeCotisation.objects.filter(pk__in=ids):
        assiette = bulletin.brut if b.base == b.Base.BRUT else bulletin.salaire_base
        if b.plafond is not None:
            assiette = min(assiette, b.plafond)
        sortie.append({
            "organisme": b.organisme, "nature": b.nature, "code": b.code, "assiette": assiette,
            "montant": _arrondi(assiette * b.taux / 100),
        })
    return sortie


def _impot_bulletin(bulletin):
    return sum((l.montant for l in bulletin.lignes.filter(rubrique__code__startswith=IMP_PREFIX)), Decimal("0"))


def generer_declaration(type_, debut, fin, user=None):
    """Déclaration CNSS / CNAMGS / IRPP (2460) / DADS depuis les bulletins validés ou clôturés de la période."""
    import csv
    import hashlib
    import io

    from .models import BulletinPaie, DeclarationSociale

    debut, fin = debut.replace(day=1), fin.replace(day=1)
    if fin < debut:
        raise ValidationError("La période de fin précède la période de début.")
    if type_ not in DeclarationSociale.Type.values:
        raise ValidationError("Type de déclaration inconnu.")
    bulletins = list(
        BulletinPaie.objects.select_related("employe")
        .prefetch_related("lignes__rubrique")
        .filter(periode__gte=debut, periode__lte=fin, statut__in=(BulletinPaie.Statut.VALIDE, BulletinPaie.Statut.CLOTURE))
        .order_by("employe__nom", "periode")
    )
    if not bulletins:
        raise ValidationError("Aucun bulletin validé sur cette période : rien à déclarer.")
    organisme = {"cnss": "CNSS", "cnamgs": "CNAMGS"}.get(type_)
    prefixe = {"fnh": "FNH", "cfp": "CFP"}.get(type_)  # contributions patronales identifiées par le code du barème
    par_employe = {}
    provisoires = set()
    tot = {"brut": Decimal("0"), "sal": Decimal("0"), "pat": Decimal("0"), "imp": Decimal("0")}
    for b in bulletins:
        provisoires.update(b.baremes_provisoires)
        ligne = par_employe.setdefault(b.employe_id, {"e": b.employe, "brut": Decimal("0"), "assiette": Decimal("0"),
                                                        "sal": Decimal("0"), "pat": Decimal("0"), "imp": Decimal("0"),
                                                        "net": Decimal("0")})
        ligne["brut"] += b.brut
        ligne["net"] += b.net
        impot = _impot_bulletin(b)
        ligne["imp"] += impot
        tot["brut"] += b.brut
        tot["imp"] += impot
        assiettes = []
        for v in ventilation_bulletin(b):
            if organisme and v["organisme"] != organisme:
                continue
            if prefixe and not v["code"].startswith(prefixe):
                continue
            assiettes.append(v["assiette"])
            if v["nature"] == "salariale":
                ligne["sal"] += v["montant"]
            else:
                ligne["pat"] += v["montant"]
        ligne["assiette"] += max(assiettes, default=Decimal("0"))  # assiette comptée une fois par bulletin
    out = io.StringIO()
    w = csv.writer(out, delimiter=";", lineterminator="\n")
    if provisoires:
        out.write("# " + avertissement_provisoire(sorted(provisoires)) + "\n")
    out.write("# GABARIT PROPOSÉ — format officiel du fichier à valider avec l'organisme destinataire.\n")
    if type_ in ("cnss", "cnamgs"):
        w.writerow(["matricule", "nom", "n_affiliation", "brut", "assiette", "cotisation_salariale", "cotisation_patronale"])
    elif type_ == "irpp":
        w.writerow(["matricule", "nom", "parts", "brut", "impot_retenu"])
    elif prefixe:
        w.writerow(["matricule", "nom", "brut", "assiette", "contribution_patronale"])
    else:
        w.writerow(["matricule", "nom", "n_cnss", "brut_annuel", "cotisations_salariales", "impot_retenu", "net_paye"])
    for ligne in par_employe.values():
        e = ligne["e"]
        tot["sal"] += ligne["sal"]
        tot["pat"] += ligne["pat"]
        if type_ == "cnss":
            w.writerow([e.code, e.nom_complet, e.numero_securite_sociale, ligne["brut"], ligne["assiette"], ligne["sal"], ligne["pat"]])
        elif type_ == "cnamgs":
            w.writerow([e.code, e.nom_complet, e.matricule_cnps, ligne["brut"], ligne["assiette"], ligne["sal"], ligne["pat"]])
        elif type_ == "irpp":
            w.writerow([e.code, e.nom_complet, e.parts_fiscales, ligne["brut"], ligne["imp"]])
        elif prefixe:
            w.writerow([e.code, e.nom_complet, ligne["brut"], ligne["assiette"], ligne["pat"]])
        else:
            w.writerow([e.code, e.nom_complet, e.numero_securite_sociale, ligne["brut"], ligne["sal"], ligne["imp"], ligne["net"]])
    contenu = out.getvalue()
    return DeclarationSociale.objects.create(
        type=type_, periode_debut=debut, periode_fin=fin, nb_salaries=len(par_employe), total_brut=tot["brut"],
        total_salarial=tot["sal"], total_patronal=tot["pat"], total_impot=tot["imp"], contenu=contenu,
        sha256=hashlib.sha256(contenu.encode("utf-8")).hexdigest(), baremes_provisoires=sorted(provisoires),
        created_by=user,
    )


def reporting_rh(annee):
    """Turnover et absentéisme de l'année (indicateurs RH)."""
    from .formation_m9c import JOURS_OUVRES_AN_DEFAUT, valeur_parametre
    from .models import Absence, DemandesConge, Employe

    debut, fin = date(annee, 1, 1), date(annee, 12, 31)
    jours_ouvres, jours_ouvres_provisoire = valeur_parametre("JOURS_OUVRES_AN", fin, JOURS_OUVRES_AN_DEFAUT)
    en_poste = lambda jour: Employe.objects.filter(  # noqa: E731
        date_embauche__lte=jour
    ).exclude(date_sortie__lte=jour).count()
    effectif_debut, effectif_fin = en_poste(debut), en_poste(fin)
    entrees = Employe.objects.filter(date_embauche__gt=debut, date_embauche__lte=fin).count()
    sorties = Employe.objects.filter(date_sortie__gte=debut, date_sortie__lte=fin).count()
    moyen = Decimal(effectif_debut + effectif_fin) / 2
    absents = DemandesConge.objects.filter(
        date_debut__year=annee,
        statut__in=(DemandesConge.Statut.APPROUVE, DemandesConge.Statut.VALIDE_RH),
        type__in=(DemandesConge.Type.MALADIE, DemandesConge.Type.SANS_SOLDE, DemandesConge.Type.EXCEPTIONNEL),
    )
    jours = sum(c.nb_jours for c in absents)
    for a in Absence.objects.filter(statut=Absence.Statut.VALIDEE, date_debut__lte=fin, date_fin__gte=debut):
        jours += (min(a.date_fin, fin) - max(a.date_debut, debut)).days + 1  # absences hors congés (M9.2)
    pct = lambda num, den: (str(_arrondi(Decimal(num) * 100 / den)) if den else None)  # noqa: E731
    return {
        "annee": annee, "effectif_debut": effectif_debut, "effectif_fin": effectif_fin, "entrees": entrees,
        "sorties": sorties, "turnover_pct": pct(Decimal(entrees + sorties) / 2, moyen),
        "jours_absence": jours, "jours_ouvres_an": str(jours_ouvres),
        "jours_ouvres_provisoire": jours_ouvres_provisoire,
        "absenteisme_pct": pct(jours, moyen * jours_ouvres),
    }
