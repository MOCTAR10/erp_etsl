"""Multi-devises (EX-G-04) : cours datés, contre-valeur XAF, écarts de change réalisés et latents.

- Cours : table `referentiels.TauxChange` (XAF pour 1 unité), saisie manuelle ou import CSV `date;devise;taux`.
  Chaque cours est PROVISOIRE tant qu'ETSL ne l'a pas confirmé (source BEAC / banque à arrêter). Le cours applicable
  à une date est le dernier connu à cette date, refusé s'il a plus de `DEVISE_ANCIENNETE_MAX_JOURS` jours.
- Pièce en devise (`OperationDevise`) : débit / crédit en XAF (contre-valeur arrondie au franc), la ligne de tiers
  porte la devise, le montant en devise et le cours (`AccountMoveLine.currency / amount_currency / exchange_rate`).
- Règlement : contre-valeur au cours du jour ; l'écart avec la contre-valeur d'origine est passé en 666 (perte de
  change) ou 766 (gain de change).
- Réévaluation à une date de clôture : écart de conversion latent en 478 (actif, perte latente) ou 479 (passif, gain
  latent), contre le compte de tiers ; extournée à la réévaluation suivante ou au règlement.
- Provision (lot a7) : à la réévaluation de clôture (`reevaluer_tout`), si les écarts latents font apparaître une perte
  nette, une provision pour risque de change est dotée (Dr 697 / Cr 499, prudence SYSCOHADA) ; elle est contre-passée
  au calcul suivant. Paramètre provisoire `DEVISE_PROVISION_PERTE` (1 = activé, défaut).
"""

import csv
import io
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError as DRFValidationError

XAF = "XAF"
ZERO = Decimal("0")
UNITE = Decimal("1")

COMPTES = {
    "411000": ("Clients", 4, "asset"),
    "401000": ("Fournisseurs", 4, "liability"),
    "512000": ("Banques", 5, "asset"),
    "666000": ("Pertes de change", 6, "expense"),
    "766000": ("Gains de change", 7, "income"),
    "478000": ("Écarts de conversion — actif (perte latente)", 4, "asset"),
    "479000": ("Écarts de conversion — passif (gain latent)", 4, "liability"),
    "697000": ("Dotations aux provisions financières — perte de change latente", 6, "expense"),
    "499000": ("Provisions pour risques à court terme — perte de change", 4, "liability"),
}


def compte(code, label=None, classe=None, type_=None):
    """Compte du plan, créé à la volée s'il manque (comptes SYSCOHADA de change absents du plan de démarrage)."""
    from referentiels.models import Account

    obj = Account.objects.filter(code=code).first()
    if obj is None:
        defaut = COMPTES.get(code)
        if defaut is None and label is None:
            raise ValidationError(f"Compte {code} absent du plan comptable.")
        label, classe, type_ = (label, classe, type_) if label else defaut
        obj = Account.objects.create(code=code, label=label, account_class=classe, account_type=type_,
                                     reconcile=classe == 4)
    return obj


def _param(code):
    from .services import get_param

    return get_param(code)


def arrondi(montant):
    """Contre-valeur XAF : le franc CFA n'a pas de subdivision."""
    return Decimal(montant).quantize(UNITE, ROUND_HALF_UP)


def taux_du(devise, jour):
    """Cours applicable (`TauxChange`) de `devise` à `jour` ; None pour le XAF. Erreur claire si absent ou trop ancien."""
    from referentiels.models import Currency, TauxChange

    if isinstance(devise, str):
        devise = Currency.objects.filter(code=devise.upper()).first()
        if devise is None:
            raise ValidationError("Devise inconnue.")
    if devise.code == XAF:
        return None
    cours = TauxChange.objects.filter(devise=devise, date__lte=jour).order_by("-date").first()
    if cours is None:
        raise ValidationError(f"Aucun cours {devise.code} connu au {jour:%d/%m/%Y} : saisissez-le (Comptabilité → cours de change).")
    max_jours = int(_param("DEVISE_ANCIENNETE_MAX_JOURS"))
    if max_jours and (jour - cours.date).days > max_jours:
        raise ValidationError(
            f"Dernier cours {devise.code} du {cours.date:%d/%m/%Y} : plus de {max_jours} jours avant le "
            f"{jour:%d/%m/%Y}. Saisissez le cours du jour."
        )
    return cours


def contre_valeur(montant_devise, devise, jour):
    """(contre-valeur XAF, cours, provisoire) d'un montant en devise à une date."""
    cours = taux_du(devise, jour)
    if cours is None:
        return arrondi(montant_devise), UNITE, False
    return arrondi(Decimal(montant_devise) * cours.taux), cours.taux, cours.est_provisoire


# ------------------------------------------------------------------------------------------------ cours
def _decimal(texte, champ):
    try:
        valeur = Decimal(str(texte).strip().replace(" ", "").replace(",", "."))
    except (InvalidOperation, ValueError):
        raise ValidationError({champ: f"Nombre invalide : {texte!r}."})
    return valeur


@transaction.atomic
def enregistrer_taux(devise_code, jour, taux, user, source="manuel"):
    """Crée ou met à jour (si encore provisoire) le cours d'une devise à une date."""
    from referentiels.models import Currency, TauxChange

    devise = Currency.objects.filter(code=(devise_code or "").strip().upper()).first()
    if devise is None:
        raise ValidationError({"devise": f"Devise inconnue : {devise_code!r}."})
    if devise.code == XAF:
        raise ValidationError({"devise": "Le XAF est la devise de tenue : pas de cours."})
    taux = _decimal(taux, "taux")
    if taux <= 0:
        raise ValidationError({"taux": "Le cours doit être strictement positif."})
    existant = TauxChange.objects.select_for_update().filter(devise=devise, date=jour).first()
    if existant:
        if not existant.est_provisoire:
            raise ValidationError(f"Cours {devise.code} du {jour:%d/%m/%Y} déjà confirmé : non modifiable.")
        existant.taux, existant.source, existant.saisi_par = taux, source, user
        existant.save(update_fields=["taux", "source", "saisi_par"])
        return existant, False
    try:
        with transaction.atomic():
            return TauxChange.objects.create(devise=devise, date=jour, taux=taux, source=source, saisi_par=user), True
    except IntegrityError:
        raise ValidationError(f"Cours {devise.code} du {jour:%d/%m/%Y} déjà saisi.")


def importer_taux(texte, user):
    """Import CSV `date;devise;taux` (en-tête facultatif, séparateur ; ou ,) — idempotent : un cours provisoire
    existant est mis à jour, un cours confirmé est laissé tel quel (signalé)."""
    from config.inputs import date_input

    texte = (texte or "").strip()
    if not texte:
        raise ValidationError({"contenu": "Fichier vide."})
    sep = ";" if ";" in texte.splitlines()[0] else ","
    crees = maj = 0
    erreurs = []
    for n, row in enumerate(csv.reader(io.StringIO(texte), delimiter=sep), start=1):
        if not row or not "".join(row).strip():
            continue
        if n == 1 and row[0].strip().lower() in ("date", "jour"):
            continue
        if len(row) < 3:
            erreurs.append(f"ligne {n} : 3 colonnes attendues (date;devise;taux)")
            continue
        try:
            jour = date_input(row[0].strip(), "date")
            _, cree = enregistrer_taux(row[1], jour, row[2], user, source="import")
            crees += int(cree)
            maj += int(not cree)
        except (ValidationError, DRFValidationError) as exc:  # ligne rejetée, le reste du fichier est importé
            detail = exc.messages if isinstance(exc, ValidationError) else exc.detail
            erreurs.append(f"ligne {n} : {detail}")
    return {"crees": crees, "mis_a_jour": maj, "erreurs": erreurs}


# ------------------------------------------------------------------------------------------------ pièces
def _journal(code):
    from accounting_kernel.models import Journal

    return Journal.objects.filter(code=code).first() or Journal.objects.get(code="OD")


def _ecriture(journal, jour, reference, label, op, lignes, user):
    """Écriture comptabilisée ; `lignes` = (compte, débit, crédit, partenaire, en_devise[, analytique])."""
    from accounting_kernel.models import AccountMove, AccountMoveLine
    from accounting_kernel.services import period_for_date, post_move

    move = AccountMove.objects.create(
        journal=_journal(journal), period=period_for_date(jour), date=jour, reference=reference[:120],
        label=label[:200], source="M10", source_ref=f"DEV/{op.code}", created_by=user,
    )
    for i, (cpt, debit, credit, partner, devise_info) in enumerate(lignes):
        extra = {}
        if devise_info:
            extra = {"currency": op.devise, "amount_currency": devise_info[0], "exchange_rate": devise_info[1]}
        AccountMoveLine.objects.create(
            move=move, account=cpt, partner=partner, debit=debit, credit=credit, order=i, label=label[:200],
            analytic_account=(op.affaire.analytic if (op.affaire_id and str(cpt.code)[:1] in "67") else None), **extra,
        )
    return post_move(move, user=user)


def _compte_tiers(op):
    return compte("411000") if op.sens == op.Sens.CREANCE else compte("401000")


def _verrou(op):
    from .models import OperationDevise

    return OperationDevise.objects.select_for_update(of=("self",)).get(pk=op.pk)


def preparer(op):
    """Cours et contre-valeur à la date de la pièce (création / brouillon)."""
    if op.montant_devise is None or op.montant_devise <= 0:
        raise ValidationError({"montant_devise": "Le montant en devise doit être strictement positif."})
    if op.devise.code == XAF:
        raise ValidationError({"devise": "Pièce en XAF : saisissez-la dans les modules habituels (pas d'écart de change)."})
    op.contre_valeur, op.taux_origine, op.taux_provisoire = contre_valeur(op.montant_devise, op.devise, op.date)
    return op


@transaction.atomic
def comptabiliser(op, user):
    """Écriture d'origine : créance Dr 411 / Cr produit ; dette Dr charge / Cr 401 — au cours du jour de la pièce."""
    op = _verrou(op)
    if op.statut != op.Statut.BROUILLON:
        raise ValidationError("Opération déjà comptabilisée.")
    preparer(op)
    cv, tiers, info = op.contre_valeur, _compte_tiers(op), (op.montant_devise, op.taux_origine)
    label = f"{op.libelle} ({op.montant_devise} {op.devise.code} à {op.taux_origine})"
    if op.sens == op.Sens.CREANCE:
        lignes = [(tiers, cv, ZERO, op.partner, info), (op.compte_contrepartie, ZERO, cv, None, None)]
        journal = "VTE"
    else:
        lignes = [(op.compte_contrepartie, cv, ZERO, None, None), (tiers, ZERO, cv, op.partner, info)]
        journal = "ACH"
    op.move = _ecriture(journal, op.date, op.reference or op.code, label, op, lignes, user)
    op.statut = op.Statut.COMPTABILISEE
    op.save()
    return op


def _extourner_reevaluation(op, jour, user):
    from accounting_kernel.services import reverse_move

    if op.move_reevaluation_id and op.move_reevaluation.status == op.move_reevaluation.Status.POSTED:
        reverse_move(op.move_reevaluation, user=user, date=jour,
                     reference=f"Extourne réévaluation {op.code}", label=f"Extourne réévaluation {op.code}")


@transaction.atomic
def regler(op, jour, user, compte_tresorerie="512000"):
    """Règlement intégral au cours du jour : tiers soldé à la contre-valeur d'origine, banque à la contre-valeur
    du jour, écart réalisé en 666 (perte) ou 766 (gain)."""
    op = _verrou(op)
    if op.statut != op.Statut.COMPTABILISEE:
        raise ValidationError("Seule une opération comptabilisée et non réglée peut être réglée.")
    if jour < op.date:
        raise ValidationError({"date": "Le règlement ne peut précéder la pièce."})
    cv_jour, taux, _prov = contre_valeur(op.montant_devise, op.devise, jour)
    _extourner_reevaluation(op, jour, user)
    banque, tiers, info = compte(compte_tresorerie), _compte_tiers(op), (op.montant_devise, taux)
    # Gain : la créance rapporte plus de XAF que prévu / la dette en coûte moins.
    gain = (cv_jour - op.contre_valeur) if op.sens == op.Sens.CREANCE else (op.contre_valeur - cv_jour)
    if op.sens == op.Sens.CREANCE:
        lignes = [(banque, cv_jour, ZERO, None, None), (tiers, ZERO, op.contre_valeur, op.partner, info)]
    else:
        lignes = [(tiers, op.contre_valeur, ZERO, op.partner, info), (banque, ZERO, cv_jour, None, None)]
    if gain > 0:
        lignes.append((compte("766000"), ZERO, gain, None, None))
    elif gain < 0:
        lignes.append((compte("666000"), -gain, ZERO, None, None))
    label = f"Règlement {op.code} ({op.montant_devise} {op.devise.code} à {taux})"
    op.move_reglement = _ecriture("BQ", jour, f"REG-{op.code}", label, op, lignes, user)
    op.date_reglement, op.taux_reglement, op.contre_valeur_reglement, op.ecart_change = jour, taux, cv_jour, gain
    op.statut = op.Statut.REGLEE
    op.save()
    return op


@transaction.atomic
def reevaluer(op, jour, user):
    """Réévaluation au cours de clôture : perte latente Dr 478 / Cr tiers (créance) ou Dr 478 / Cr 401 (dette) ;
    gain latent Dr tiers / Cr 479. La réévaluation précédente est extournée (une seule position latente)."""
    op = _verrou(op)
    if op.statut != op.Statut.COMPTABILISEE:
        raise ValidationError("Seule une opération comptabilisée et non réglée se réévalue.")
    if jour < op.date:
        raise ValidationError({"date": "La date de réévaluation ne peut précéder la pièce."})
    cv_jour, taux, _prov = contre_valeur(op.montant_devise, op.devise, jour)
    _extourner_reevaluation(op, jour, user)
    gain = (cv_jour - op.contre_valeur) if op.sens == op.Sens.CREANCE else (op.contre_valeur - cv_jour)
    tiers = _compte_tiers(op)
    op.move_reevaluation = None
    if gain:
        montant = abs(gain)
        # Variation du tiers : créance + gain → débit tiers ; dette + gain → débit tiers (dette diminue).
        if gain > 0:
            lignes = [(tiers, montant, ZERO, op.partner, None), (compte("479000"), ZERO, montant, None, None)]
        else:
            lignes = [(compte("478000"), montant, ZERO, None, None), (tiers, ZERO, montant, op.partner, None)]
        label = f"Écart de conversion {op.code} au {jour:%d/%m/%Y} ({op.devise.code} à {taux})"
        op.move_reevaluation = _ecriture("OD", jour, f"ECV-{op.code}", label, op, lignes, user)
    op.date_reevaluation, op.taux_reevaluation, op.ecart_latent = jour, taux, gain
    op.save()
    return op


def reevaluer_tout(jour, user):
    """Réévalue toutes les opérations en devise ouvertes à la date de clôture (cours manquant = signalé), puis
    contre-passe la provision précédente et dote la nouvelle si la perte latente nette l'exige (lot a7)."""
    from .models import OperationDevise, ProvisionChange

    derniere = ProvisionChange.objects.filter(statut=ProvisionChange.Statut.ACTIVE).order_by("-date_cloture").first()
    if derniere is not None and jour < derniere.date_cloture:
        raise ValidationError(
            f"Une provision pour perte de change existe au {derniere.date_cloture:%d/%m/%Y} : la réévaluation de clôture "
            "ne peut pas être antérieure."
        )
    faites, erreurs = 0, []
    for op in OperationDevise.objects.filter(statut=OperationDevise.Statut.COMPTABILISEE, date__lte=jour):
        try:
            reevaluer(op, jour, user)
            faites += 1
        except ValidationError as exc:
            erreurs.append(f"{op.code} : {exc.messages[0]}")
    resultat = {"reevaluees": faites, "erreurs": erreurs}
    resultat.update(provisionner(jour, user))
    return resultat


def _provision_dict(p):
    if p is None:
        return None
    return {
        "id": str(p.pk), "date_cloture": p.date_cloture.isoformat(), "montant": str(p.montant),
        "perte_latente": str(p.perte_latente), "gain_latent": str(p.gain_latent), "statut": p.statut,
        "move_number": p.move.number if p.move_id else None,
    }


@transaction.atomic
def provisionner(jour, user):
    """Contre-passe la provision active (Dr 499 / Cr 697 à `jour`) puis, si le paramètre est activé et que la
    position de change latente à `jour` est une perte nette, dote la nouvelle provision Dr 697 / Cr 499.

    Position = écarts latents des opérations ouvertes réévaluées à `jour` (pertes − gains)."""
    from accounting_kernel.services import reverse_move
    from django.db.models import Q, Sum

    from .models import OperationDevise, ProvisionChange

    contre_passee = None
    for ancienne in ProvisionChange.objects.select_for_update(of=("self",)).filter(statut=ProvisionChange.Statut.ACTIVE):
        if ancienne.move.status == ancienne.move.Status.POSTED:
            ancienne.move_contre_passation = reverse_move(
                ancienne.move, user=user, date=jour, reference=f"Contre-passation provision change {ancienne.date_cloture}",
                label=f"Contre-passation de la provision pour perte de change du {ancienne.date_cloture:%d/%m/%Y}",
            )
        ancienne.statut, ancienne.date_contre_passation = ProvisionChange.Statut.CONTRE_PASSEE, jour
        ancienne.save(update_fields=["statut", "move_contre_passation", "date_contre_passation"])
        contre_passee = ancienne

    ouvertes = OperationDevise.objects.filter(statut=OperationDevise.Statut.COMPTABILISEE, date_reevaluation=jour)
    agg = ouvertes.aggregate(
        pertes=Sum("ecart_latent", filter=Q(ecart_latent__lt=0)), gains=Sum("ecart_latent", filter=Q(ecart_latent__gt=0))
    )
    pertes, gains = -(agg["pertes"] or ZERO), agg["gains"] or ZERO
    nette = pertes - gains
    nouvelle = None
    active = bool(_param("DEVISE_PROVISION_PERTE"))
    if active and nette > 0:
        from accounting_kernel.models import AccountMove, AccountMoveLine
        from accounting_kernel.services import period_for_date, post_move

        label = f"Provision pour perte de change latente au {jour:%d/%m/%Y}"
        move = AccountMove.objects.create(
            journal=_journal("OD"), period=period_for_date(jour), date=jour, reference=f"PRV-CHANGE-{jour:%Y%m%d}",
            label=label, source="M10", source_ref=f"DEV/PROVISION/{jour:%Y%m%d}", created_by=user,
        )
        AccountMoveLine.objects.create(move=move, account=compte("697000"), debit=nette, credit=ZERO, order=0, label=label)
        AccountMoveLine.objects.create(move=move, account=compte("499000"), debit=ZERO, credit=nette, order=1, label=label)
        nouvelle = ProvisionChange.objects.create(
            date_cloture=jour, perte_latente=pertes, gain_latent=gains, montant=nette, operations=ouvertes.count(),
            move=post_move(move, user=user), cree_par=user,
        )
    return {
        "provision": _provision_dict(nouvelle),
        "provision_contre_passee": _provision_dict(contre_passee),
        "position_latente": str(gains - pertes),
        "provision_active": active,
    }


def anciennete_cours():
    """Par devise active : dernier cours connu, son âge et son statut (bandeau « cours manquant / ancien »)."""
    from referentiels.models import Currency, TauxChange

    jour = timezone.localdate()
    max_jours = int(_param("DEVISE_ANCIENNETE_MAX_JOURS"))
    sortie = []
    for dev in Currency.objects.filter(is_active=True).exclude(code=XAF):
        dernier = TauxChange.objects.filter(devise=dev).order_by("-date").first()
        age = (jour - dernier.date).days if dernier else None
        sortie.append({
            "devise": dev.code, "date": dernier.date.isoformat() if dernier else None,
            "taux": str(dernier.taux) if dernier else None, "provisoire": dernier.est_provisoire if dernier else True,
            "age_jours": age, "a_jour": bool(dernier) and (not max_jours or age <= max_jours),
        })
    return sortie

