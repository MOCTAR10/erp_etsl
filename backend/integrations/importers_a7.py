"""Lot a7 : gabarits de reprise complémentaires (CDC §10, plan ETSL-ERP-MIG §4.3) — mêmes règles que les gabarits
de `importers_migration` (CSV / XML, clé métier, à blanc, transaction par fichier, rapport d'anomalies, rejeu).

- habilitations HSE (qualifications RH de type habilitation, lues par le contrôle « aucun départ sans habilitation »
  des permis de travail) ;
- équipements du parc (M4) avec compteur initial historisé, actifs de maintenance (M8) et relevés de compteurs ;
- commandes d'achat ouvertes (BC confirmés / partiellement reçus, une ligne de fichier = une ligne de BC) ;
- factures ouvertes clients et fournisseurs : le SOLDE restant dû est ventilé par tiers et par facture (écriture OD
  « compte collectif sans tiers → compte du tiers », neutre sur le total repris en balance d'ouverture), la facture
  est enregistrée émise / comptabilisée pour l'échéancier, le lettrage et la trésorerie.

Les enregistrements des autres modules sont créés par leurs modèles et services existants, sans les modifier.
"""

import hashlib
from datetime import datetime
from decimal import Decimal

from django.utils import timezone

from .importers_migration import (
    Colonne as C,
    Gabarit,
    LigneErreur,
    _bool,
    _choix,
    _currency,
    _date,
    _dec,
    _partner,
    _req,
    _txt,
    _valider,
)
from config.i18n import tr

NOTE_REPRISE = "[Reprise migration]"
ZERO = Decimal("0")


# --------------------------------------------------------------------------------------------- habilitations HSE
def _habilitations_hse(row, ctx):
    from rh_paie.models import Employe, Qualification

    matricule = _req(row, "matricule", 20)
    employe = Employe.objects.filter(code=matricule).first()
    if employe is None:
        raise LigneErreur(tr("salarié inconnu : %(matricule)s (chargez d'abord le gabarit Salariés).") % {"matricule": matricule})
    intitule = _req(row, "intitule", 180)
    obtention, validite = _date(row, "date_obtention"), _date(row, "date_validite")
    if obtention and validite and validite < obtention:
        raise LigneErreur("date_validite antérieure à date_obtention.")
    existante = Qualification.objects.filter(employe=employe, intitule__iexact=intitule).order_by("-date_validite").first()
    if existante is not None and existante.source != Qualification.Source.RH:
        raise LigneErreur(tr("« %(intitule)s » est synchronisée depuis %(source)s : non modifiable par reprise.") % {"intitule": intitule, "source": existante.get_source_display()})
    valeurs = {
        "type": _choix(row, "type", Qualification.Type.choices, defaut=Qualification.Type.HABILITATION),
        "organisme": _txt(row, "organisme", 120),
        "date_obtention": obtention,
        "date_validite": validite,
        "notes": (NOTE_REPRISE + " " + _txt(row, "notes")).strip(),
    }
    qualif = existante or Qualification(employe=employe, intitule=intitule, source=Qualification.Source.RH)
    for k, v in valeurs.items():
        setattr(qualif, k, v)
    qualif.save()
    return ("maj" if existante else "creee"), f"{matricule}/{intitule}"


# --------------------------------------------------------------------------------------------- parc et maintenance
def _equipements_parc(row, ctx):
    import copy

    from logistique.models import EquipementParc
    from logistique.services import enregistrer_releve_parc, historiser_equipement

    code = _req(row, "code", 20)
    existant = EquipementParc.objects.filter(code=code).first()
    proprietaire = _partner(_txt(row, "proprietaire"))
    gr = _bool(row, "global_rental", False)
    if gr and (proprietaire is None or not proprietaire.is_global_rental):
        raise LigneErreur("équipement GLOBAL RENTAL : le propriétaire doit être un tiers is_global_rental (compte 618).")
    valeurs = {
        "label": _req(row, "libelle", 200),
        "registration": _txt(row, "immatriculation", 40),
        "categorie": _choix(row, "categorie", EquipementParc.Categorie.choices, defaut=EquipementParc.Categorie.ENGIN),
        "compteur_type": _choix(row, "compteur_type", EquipementParc.Compteur.choices, defaut=EquipementParc.Compteur.HEURES),
        "site": _txt(row, "site", 120),
        "plafond_compteur": _dec(row, "plafond_compteur"),
        "is_global_rental": gr,
        "proprietaire": proprietaire,
        "signe_618": _bool(row, "signe_618", gr),
    }
    compteur, jour = _dec(row, "compteur"), _date(row, "date_releve")
    if compteur and not jour:
        raise LigneErreur("date_releve obligatoire quand compteur est renseigné.")
    if existant is None:
        equipement = EquipementParc(
            code=code, statut=_choix(row, "statut", [c for c in EquipementParc.Statut.choices
                                                      if c[0] in ("disponible", "maintenance", "hors_service")],
                                     defaut=EquipementParc.Statut.DISPONIBLE), **valeurs)
        equipement.save()
    else:
        equipement, avant = existant, copy.copy(existant)
        for k, v in valeurs.items():
            setattr(equipement, k, v)
        equipement.save()
        historiser_equipement(avant, equipement, ctx.user)
    if compteur and not equipement.releves.filter(date=jour, valeur=compteur).exists():
        enregistrer_releve_parc(equipement, compteur, jour, ctx.user, commentaire=f"{NOTE_REPRISE} compteur initial")
    return ("maj" if existant else "creee"), code


def _releves_compteurs(row, ctx):
    from logistique.models import EquipementParc
    from logistique.services import enregistrer_releve_parc

    code = _req(row, "equipement", 20)
    equipement = EquipementParc.objects.filter(code=code).first()
    if equipement is None:
        raise LigneErreur(tr("équipement inconnu : %(code)s (chargez d'abord le gabarit Équipements du parc).") % {"code": code})
    jour, valeur = _date(row, "date", obligatoire=True), _dec(row, "valeur", obligatoire=True)
    cle = f"{code}/{jour:%Y-%m-%d}/{valeur}"
    if equipement.releves.filter(date=jour, valeur=valeur).exists():
        return "doublon", cle
    enregistrer_releve_parc(equipement, valeur, jour, ctx.user,
                            commentaire=(f"{NOTE_REPRISE} " + _txt(row, "commentaire", 150)).strip())
    return "creee", cle


def _actifs_maintenance(row, ctx):
    from logistique.models import EquipementParc
    from maintenance.models import Actif

    code = _req(row, "code", 20)
    existant = Actif.objects.filter(code=code).first()
    equipement_gr = None
    if _txt(row, "equipement_gr"):
        equipement_gr = EquipementParc.objects.filter(code=_txt(row, "equipement_gr")).first()
        if equipement_gr is None:
            raise LigneErreur(tr("équipement du parc inconnu : %(txt)s (chargez d'abord le parc).") % {"txt": _txt(row, 'equipement_gr')})
    compteur = _dec(row, "compteur", ZERO)
    if existant is not None and compteur < existant.compteur_value:
        raise LigneErreur(tr("le compteur ne peut baisser (valeur actuelle : %(existant_compteur_value)s).") % {"existant_compteur_value": existant.compteur_value})
    valeurs = {
        "designation": _req(row, "designation", 200),
        "categorie": _choix(row, "categorie", Actif.Categorie.choices, defaut=Actif.Categorie.MACHINE),
        "fabricant": _txt(row, "fabricant", 120),
        "modele": _txt(row, "modele", 120),
        "numero_serie": _txt(row, "numero_serie", 100),
        "site": _txt(row, "site", 120),
        "date_mise_en_service": _date(row, "mise_en_service"),
        "garanti_jusqu": _date(row, "garantie_jusqu"),
        "compteur_type": _choix(row, "compteur_type", Actif.Compteur.choices, defaut=Actif.Compteur.HEURES,
                                alias={"forfait": "aucun", "sans": "aucun"}),
        "compteur_value": compteur,
        "equipement_gr": equipement_gr,
        "is_global_rental": equipement_gr is not None,
        "signe_618": equipement_gr is not None and equipement_gr.signe_618,
    }
    actif = existant or Actif(code=code, statut=_choix(
        row, "statut", [c for c in Actif.Statut.choices if c[0] in ("operationnel", "en_panne", "hors_service")],
        defaut=Actif.Statut.OPERATIONNEL))
    for k, v in valeurs.items():
        setattr(actif, k, v)
    _valider(actif)
    if existant is None:
        actif.notes = NOTE_REPRISE
    actif.save()
    return ("maj" if existant else "creee"), code


# --------------------------------------------------------------------------------------------- commandes ouvertes
def _commandes_ouvertes(row, ctx):
    from achats.models import PurchaseOrder, PurchaseOrderLine, _refresh_purchase_order_status
    from commercial.models import Affaire
    from referentiels.models import Article, UnitOfMeasure

    numero = _req(row, "numero", 20)
    fournisseur = _partner(_req(row, "fournisseur"))
    bc = PurchaseOrder.objects.filter(code=numero).first()
    if bc is not None:
        if not bc.notes.startswith(NOTE_REPRISE):
            raise LigneErreur(tr("BC %(numero)s déjà saisi dans l'ERP : non modifiable par reprise.") % {"numero": numero})
        if bc.receipts.exists() or bc.invoices.exists():
            raise LigneErreur(tr("BC %(numero)s déjà mouvementé dans l'ERP (réception ou facture) : non modifiable.") % {"numero": numero})
        if bc.supplier_id != fournisseur.pk:
            raise LigneErreur(tr("BC %(numero)s : fournisseur différent de celui déjà repris (%(supplier_code)s).") % {"numero": numero, "supplier_code": bc.supplier.code})
    affaire = None
    if _txt(row, "affaire"):
        affaire = Affaire.objects.filter(code=_txt(row, "affaire")).first()
        if affaire is None:
            raise LigneErreur(tr("affaire inconnue : %(txt)s (chargez d'abord le gabarit Affaires).") % {"txt": _txt(row, 'affaire')})
    entete = {
        "supplier": fournisseur,
        "order_date": _date(row, "date", obligatoire=True),
        "expected_date": _date(row, "livraison_prevue"),
        "currency": _currency(_txt(row, "devise")),
        "is_global_rental": _bool(row, "global_rental", False),
        "affaire": affaire,
        "analytic": affaire.analytic if affaire is not None else None,
        "reference_ds": _txt(row, "reference_ds", 40),
    }
    if bc is None:
        bc = PurchaseOrder(code=numero, status=PurchaseOrder.Status.CONFIRMEE,
                           notes=f"{NOTE_REPRISE} commande ouverte reprise du système source.", created_by=ctx.user)
    for k, v in entete.items():
        setattr(bc, k, v)
    _valider(bc)  # BC GLOBAL RENTAL ⇒ fournisseur is_global_rental (compte 618)
    bc.save()

    designation = _req(row, "designation", 200)
    quantite = _dec(row, "quantite", obligatoire=True)
    if quantite <= 0:
        raise LigneErreur("quantite doit être strictement positive.")
    recue = _dec(row, "quantite_recue", ZERO)
    if recue > quantite:
        raise LigneErreur(tr("quantite_recue (%(recue)s) supérieure à la quantité commandée (%(quantite)s).") % {"recue": recue, "quantite": quantite})
    article = None
    if _txt(row, "article"):
        article = Article.objects.filter(code=_txt(row, "article")).first()
        if article is None:
            raise LigneErreur(tr("article inconnu : %(txt)s (chargez d'abord le gabarit Articles).") % {"txt": _txt(row, 'article')})
    unite = None
    if _txt(row, "unite"):
        unite = UnitOfMeasure.objects.filter(code=_txt(row, "unite")).first()
        if unite is None:
            raise LigneErreur(tr("unité inconnue : %(txt)s.") % {"txt": _txt(row, 'unite')})
    ligne = bc.lines.filter(label=designation).first()
    cree = ligne is None
    ligne = ligne or PurchaseOrderLine(purchase_order=bc, label=designation)
    ligne.article, ligne.unit, ligne.quantity, ligne.received_qty = article, unite, quantite, recue
    ligne.unit_price = _dec(row, "prix_unitaire", ZERO)
    ligne.save()
    _refresh_purchase_order_status(bc.pk)  # confirmée / réception partielle selon les quantités reçues
    return ("creee" if cree else "maj"), f"{numero}/{designation}"


# --------------------------------------------------------------------------------------------- factures ouvertes
COMPTES_TIERS = {
    "411000": ("Clients", 4, "asset"),
    "411100": ("Clients intra-groupe GLOBAL RENTAL", 4, "asset"),
    "401000": ("Fournisseurs", 4, "liability"),
    "401100": ("Fournisseurs intra-groupe GLOBAL RENTAL", 4, "liability"),
}


def _date_bascule(ctx):
    try:
        return datetime.strptime((ctx.options.get("date") or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        raise LigneErreur("date de bascule invalide (AAAA-MM-JJ).")


def _solde(row):
    solde = _dec(row, "solde", obligatoire=True)
    if solde <= 0:
        raise LigneErreur("solde (reste dû) doit être strictement positif.")
    return solde


def _conversion(row, ctx, solde):
    """(solde XAF, info devise) : une facture en devise est reprise pour sa contre-valeur XAF au cours connu à la date
    de bascule (`comptabilite.devises.contre_valeur`) ; ligne rejetée si la devise n'a pas de cours à cette date."""
    from django.core.exceptions import ValidationError as DjangoValidationError

    from comptabilite.devises import XAF, contre_valeur

    code = _txt(row, "devise").upper()
    if not code or code == XAF:
        return solde, None
    devise = _currency(code)
    jour = _date_bascule(ctx)
    try:
        xaf, taux, provisoire = contre_valeur(solde, devise, jour)
    except DjangoValidationError as exc:
        raise LigneErreur(tr("devise %(code)s sans cours utilisable au %(jour)s (date de bascule) : %(motif)s")
                          % {"code": code, "jour": f"{jour:%d/%m/%Y}", "motif": " ".join(exc.messages)})
    return xaf, {"devise": devise, "montant": solde, "taux": taux, "provisoire": provisoire}


def _mention_devise(info):
    if not info:
        return ""
    return (f" — reste dû {info['montant']} {info['devise'].code} au cours {info['taux']}"
            + (" (provisoire)" if info["provisoire"] else ""))


def _xaf():
    from referentiels.models import Currency

    return Currency.objects.filter(code="XAF").first()


def _ventiler(ctx, nature, numero, partner, solde, libelle, info=None):
    """Écriture OD de ventilation du solde repris : Dr 411 tiers / Cr 411 (client) ; Dr 401 / Cr 401 tiers
    (fournisseur). Le compte collectif sans tiers porte le total de la balance d'ouverture : l'écriture est neutre
    sur le solde du compte, elle rattache la créance / dette au tiers (balance âgée, lettrage, relances)."""
    from accounting_kernel.models import AccountMove, AccountMoveLine, Journal
    from accounting_kernel.services import period_for_date, post_move
    from comptabilite.devises import compte

    jour = _date_bascule(ctx)
    code = ("411" if nature == "client" else "401") + ("100" if partner.is_global_rental else "000")
    cpt = compte(code, *COMPTES_TIERS[code])
    journal = Journal.objects.filter(code="OD").first()
    if journal is None:
        raise LigneErreur("journal OD (opérations diverses) absent.")
    move = AccountMove.objects.create(
        journal=journal, period=period_for_date(jour), date=jour, reference=f"REPRISE {numero}"[:120],
        label=libelle[:200], source="integrations", source_ref=f"reprise/{nature}/{numero}"[:60], created_by=ctx.user,
    )
    tiers_debit = nature == "client"
    # Facture en devise : la ligne du tiers porte la devise, le reste dû en devise et le cours (réévaluation, lettrage).
    extra = ({"currency": info["devise"], "amount_currency": info["montant"], "exchange_rate": info["taux"]}
             if info else {})
    AccountMoveLine.objects.create(move=move, account=cpt, partner=partner, order=0, label=libelle[:200],
                                   debit=solde if tiers_debit else ZERO, credit=ZERO if tiers_debit else solde, **extra)
    AccountMoveLine.objects.create(move=move, account=cpt, partner=None, order=1, label=libelle[:200],
                                   debit=ZERO if tiers_debit else solde, credit=solde if tiers_debit else ZERO)
    return post_move(move, user=ctx.user)


def _deja_reprise(move, solde, numero, info=None):
    if move is None or not (move.source_ref or "").startswith("reprise/"):
        raise LigneErreur(tr("facture %(numero)s déjà saisie dans l'ERP : non reprise.") % {"numero": numero})
    if info:  # rejeu d'une facture en devise : on compare le reste dû en devise (le cours a pu être corrigé)
        solde = info["montant"]
        total = sum((l.amount_currency or ZERO for l in move.lines.all() if l.currency_id), ZERO)
    else:
        total = sum((l.debit for l in move.lines.all()), ZERO)
    if total != solde:
        raise LigneErreur(tr("facture %(numero)s déjà reprise avec un solde de %(total)s : extournez la reprise avant de la recharger.") % {"numero": numero, "total": total})
    return "doublon"


def _factures_clients(row, ctx):
    from commercial.models import Affaire
    from comptabilite.models import FactureClient

    numero = _req(row, "numero", 20)
    client = _partner(_req(row, "client"))
    solde, info = _conversion(row, ctx, _solde(row))
    jour, echeance = _date(row, "date", obligatoire=True), _date(row, "echeance")
    existante = FactureClient.objects.filter(code=numero).select_related("move").first()
    if existante is not None:
        if existante.client_id != client.pk:
            raise LigneErreur(tr("facture %(numero)s déjà reprise pour un autre client.") % {"numero": numero})
        return _deja_reprise(existante.move, solde, numero, info), numero
    affaire = None
    if _txt(row, "affaire"):
        affaire = Affaire.objects.filter(code=_txt(row, "affaire")).first()
        if affaire is None:
            raise LigneErreur(tr("affaire inconnue : %(txt)s.") % {"txt": _txt(row, 'affaire')})
    origine = _dec(row, "montant_ttc")
    objet = (f"{NOTE_REPRISE} {_txt(row, 'objet')}".strip() + (f" (TTC d'origine {origine})" if origine else "")
             + _mention_devise(info))
    move = _ventiler(ctx, "client", numero, client, solde, f"Reprise facture client {numero} — {client.name}", info)
    FactureClient.objects.create(
        code=numero, nature=FactureClient.Nature.FACTURE, statut=FactureClient.Statut.EMISE, client=client,
        affaire=affaire, objet=objet[:250], date=jour, echeance=echeance, montant_ht=solde, montant_tva=ZERO,
        montant_ttc=solde, move=move, cree_par=ctx.user, emise_par=ctx.user, emise_le=timezone.now(),
    )
    return "creee", numero


def _taux_hors_tva():
    from comptabilite.models import TauxTva

    # Inactif : jamais proposé ni pris par défaut ; porte seulement le solde repris (TVA déjà déclarée dans SAGE).
    return TauxTva.objects.get_or_create(
        code="REPRISE0", defaults={"label": "Hors TVA — solde repris (migration)", "taux": ZERO, "is_active": False}
    )[0]


def _factures_fournisseurs(row, ctx):
    from achats.models import PurchaseInvoice, PurchaseInvoiceLine, PurchaseOrder, PurchaseOrderLine

    numero = _req(row, "numero", 100)
    fournisseur = _partner(_req(row, "fournisseur"))
    solde, info = _conversion(row, ctx, _solde(row))
    jour = _date(row, "date", obligatoire=True)
    existante = PurchaseInvoice.objects.filter(supplier=fournisseur, invoice_ref=numero).select_related("move").first()
    cle = f"{fournisseur.code}/{numero}"
    if existante is not None:
        return _deja_reprise(existante.move, solde, numero, info), cle
    commande = _txt(row, "commande", 40)
    move = _ventiler(ctx, "fournisseur", numero, fournisseur, solde,
                     f"Reprise facture fournisseur {numero} — {fournisseur.name}", info)
    # BC technique (une facture fournisseur est toujours rattachée à un BC) : clôturé, reçu et facturé à 1.
    code_bc = "RPF-" + hashlib.sha1(cle.encode("utf-8")).hexdigest()[:12].upper()
    bc = PurchaseOrder.objects.create(
        code=code_bc, supplier=fournisseur, order_date=jour, status=PurchaseOrder.Status.CLOTUREE,
        # Montants en XAF (contre-valeur à la date de bascule) : la devise d'origine figure dans les notes et l'écriture.
        is_global_rental=fournisseur.is_global_rental, currency=_xaf() if info else _currency(_txt(row, "devise")),
        created_by=ctx.user,
        notes=(f"{NOTE_REPRISE} support technique de la facture {numero}"
               + (f" (commande d'origine {commande})" if commande else "") + _mention_devise(info)),
    )
    ligne_bc = PurchaseOrderLine.objects.create(purchase_order=bc, label=f"Solde repris — facture {numero}"[:200],
                                                quantity=1, unit_price=solde, received_qty=1)
    facture = PurchaseInvoice.objects.create(
        purchase_order=bc, supplier=fournisseur, invoice_ref=numero, invoice_date=jour, currency=bc.currency,
        status=PurchaseInvoice.Status.COMPTABILISEE, move=move, comptabilise_par=ctx.user, comptabilise_le=timezone.now(),
    )
    PurchaseInvoiceLine.objects.create(invoice=facture, purchase_order_line=ligne_bc, quantity=1, unit_price=solde,
                                       taux_tva=_taux_hors_tva())
    return "creee", cle


# --------------------------------------------------------------------------------------------- catalogue
GABARITS_A7 = [
    Gabarit("habilitations_hse", "Habilitations HSE du personnel", "D14", "matricule + intitule", [
        C("matricule", True, "Salarié déjà chargé", "EMP-0042"),
        C("intitule", True, "Doit contenir le mot-clé exigé par le type de permis", "Habilitation travail en hauteur"),
        C("type", False, "habilitation / permis / certificat / diplome", "habilitation"),
        C("organisme", False, "Organisme délivrant", "APAVE Gabon"),
        C("date_obtention", False, "AAAA-MM-JJ", "2025-06-01"), C("date_validite", False, "AAAA-MM-JJ (vide = sans échéance)", "2027-06-01"),
        C("notes"),
    ], _habilitations_hse, cercle="hse",
        note="Lues par le contrôle des permis de travail (aucun départ sans habilitation valide) ; échues = bloquantes."),
    Gabarit("equipements_parc", "Équipements du parc (M4) et compteur initial", "D15", "code", [
        C("code", True, "Code équipement (20 car.)", "PAR-GRUE-01"), C("libelle", True, "", "Grue mobile 50 t"),
        C("immatriculation", False, "Immatriculation / n° série", "GA-1234-AB"),
        C("categorie", False, "engin / levage / transport / atelier / materiel", "levage"),
        C("statut", False, "disponible / maintenance / hors_service (création)", "disponible"),
        C("compteur_type", False, "heures / km / forfait", "heures"), C("compteur", False, "Valeur relevée", "1250"),
        C("date_releve", False, "AAAA-MM-JJ (si compteur)", "2026-12-31"), C("plafond_compteur"), C("site", False, "", "Port-Gentil"),
        C("global_rental", False, "oui / non", "non"), C("proprietaire", False, "Code tiers (GR obligatoire)", ""),
        C("signe_618", False, "oui / non (défaut = global_rental)", ""),
    ], _equipements_parc, cercle="parc",
        note="Le compteur est historisé (jamais à la baisse) ; un équipement GR exige un propriétaire GLOBAL RENTAL (618)."),
    Gabarit("releves_compteurs", "Historique des compteurs du parc", "D15", "equipement + date + valeur", [
        C("equipement", True, "Code équipement du parc", "PAR-GRUE-01"), C("date", True, "AAAA-MM-JJ", "2026-11-30"),
        C("valeur", True, "Heures / km", "1180"), C("commentaire"),
    ], _releves_compteurs, cercle="parc", note="Lignes dans l'ordre chronologique : un relevé plus ancien ou plus bas est refusé."),
    Gabarit("actifs_maintenance", "Actifs de maintenance (machines, engins) et compteurs", "D15", "code", [
        C("code", True, "Code actif (20 car.)", "EQ-POSTE-07"), C("designation", True, "", "Poste de soudage TIG"),
        C("categorie", False, "machine / engin / levage / atelier / chantier / outillage", "machine"),
        C("statut", False, "operationnel / en_panne / hors_service (création)", "operationnel"),
        C("fabricant"), C("modele"), C("numero_serie"), C("site", False, "", "Atelier PG"),
        C("mise_en_service", False, "AAAA-MM-JJ", "2021-03-01"), C("garantie_jusqu", False, "AAAA-MM-JJ", ""),
        C("compteur_type", False, "heures / km / aucun", "heures"), C("compteur", False, "Valeur actuelle", "830"),
        C("equipement_gr", False, "Code équipement du parc GR lié", ""),
    ], _actifs_maintenance, cercle="parc", note="Compteur jamais à la baisse ; un actif lié à un équipement GR lit son compteur en logistique."),
    Gabarit("commandes_ouvertes", "Commandes d'achat ouvertes (BC non soldés)", "D07", "numero + designation", [
        C("numero", True, "N° BC source (20 car.)", "BC-SAGE-0193"), C("fournisseur", True, "Code tiers", "FRS-001"),
        C("date", True, "AAAA-MM-JJ", "2026-11-15"), C("livraison_prevue", False, "AAAA-MM-JJ", ""),
        C("devise", False, "", "XAF"), C("affaire", False, "Code affaire (imputation M11)", ""),
        C("global_rental", False, "oui / non", "non"), C("reference_ds"),
        C("designation", True, "Une ligne de fichier = une ligne de BC", "Tube acier 6 pouces"),
        C("article", False, "Code article", "MAT-TUBE-6"), C("unite"), C("quantite", True, "", "40"),
        C("prix_unitaire", False, "", "125000"), C("quantite_recue", False, "Déjà reçue dans le système source", "10"),
    ], _commandes_ouvertes,
        note="BC confirmé (réception partielle si quantité reçue) ; les réceptions suivantes se font dans l'ERP."),
    Gabarit("factures_clients_ouvertes", "Factures clients ouvertes (créances non soldées)", "D12", "numero", [
        C("numero", True, "N° facture (20 car.)", "FA-2026-0412"), C("client", True, "Code tiers", "CLI-001"),
        C("date", True, "Date de facture AAAA-MM-JJ", "2026-10-20"), C("echeance", False, "AAAA-MM-JJ", "2026-12-19"),
        C("solde", True, "Reste dû TTC, dans la devise de la facture", "2360000"),
        C("montant_ttc", False, "TTC d'origine (information)", "2360000"),
        C("affaire", False, "Code affaire", ""), C("objet"), C("devise", False, "Code devise (vide = XAF)", "XAF"),
    ], _factures_clients, options=("date",),
        note="Date = date de bascule. Solde ventilé 411 sans tiers → 411 du client (neutre sur la balance d'ouverture). "
             "Facture en devise : contre-valeur XAF au cours connu à la date de bascule (Comptabilité → cours de "
             "change) ; ligne rejetée sans cours."),
    Gabarit("factures_fournisseurs_ouvertes", "Factures fournisseurs ouvertes (dettes non soldées)", "D12", "fournisseur + numero", [
        C("numero", True, "N° facture du fournisseur", "F-88213"), C("fournisseur", True, "Code tiers", "FRS-001"),
        C("date", True, "Date de facture AAAA-MM-JJ", "2026-11-02"),
        C("solde", True, "Reste dû TTC, dans la devise de la facture", "1180000"),
        C("commande", False, "N° de commande d'origine (information)", ""),
        C("devise", False, "Code devise (vide = XAF)", "XAF"),
    ], _factures_fournisseurs, options=("date",),
        note="Date = date de bascule. Solde ventilé 401 → 401 du fournisseur ; facture comptabilisée prête au paiement. "
             "Facture en devise : contre-valeur XAF au cours connu à la date de bascule ; ligne rejetée sans cours."),
]
