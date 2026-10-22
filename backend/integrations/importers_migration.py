"""Gabarits de reprise de données (CDC §10, plan ETSL-ERP-MIG §4.3) — fichiers CSV / XML (H-04 : aucune API).

Chaque gabarit : colonnes documentées, clé métier (idempotence ligne à ligne), rapport d'anomalies ligne par ligne,
mode « à blanc » (tout est exécuté puis annulé : validation sans écriture) et transaction atomique par fichier
(au-delà du taux d'erreur toléré — paramètre provisoire ETSL — RIEN n'est écrit). Un fichier déjà chargé
réellement (même SHA-256) est reconnu et rejoué sans réinsertion, sauf demande explicite.

Les enregistrements des autres modules sont créés par leurs modèles et services existants (ORM), sans les modifier.
"""

import csv
import hashlib
import io
import random
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Callable

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone

from .models_migration import HistoriquePaie, LigneReprise, LotReprise, ParametreReprise

MASQUE = "•••"

# --------------------------------------------------------------------------------------------------
# Paramètres provisoires (à confirmer ou modifier par ETSL — écran d'import, section Paramètres)
# --------------------------------------------------------------------------------------------------
PARAMETRES_REPRISE_DEFAUT = {
    "TAUX_ERREUR_MAX": ("Taux d'erreur maximal toléré par fichier (au-delà, rien n'est écrit)", Decimal("0"), "%"),
    "ECHANTILLON_C10": ("Taille de l'échantillon de contrôle C10 par objet", Decimal("20"), "enregistrements"),
    "HISTORIQUE_PAIE_MOIS": ("Profondeur de l'historique de paie à reprendre", Decimal("12"), "mois"),
    "TAILLE_MAX_FICHIER_MO": ("Taille maximale d'un fichier CSV / XML", Decimal("20"), "Mo"),
    "TAILLE_MAX_LOT_GED_MO": ("Taille maximale d'un lot GED (ZIP décompressé)", Decimal("500"), "Mo"),
}


def get_param_reprise(code):
    label, valeur, unite = PARAMETRES_REPRISE_DEFAUT[code]
    obj, _ = ParametreReprise.objects.get_or_create(code=code, defaults={"label": label, "valeur": valeur, "unite": unite})
    return obj.valeur


def assurer_parametres():
    for code in PARAMETRES_REPRISE_DEFAUT:
        get_param_reprise(code)


class LigneErreur(Exception):
    """Anomalie d'une seule ligne (rapport d'anomalies)."""


class FichierErreur(Exception):
    """Fichier inexploitable (format, en-têtes, taille) : lot en échec, rien n'est écrit."""


# --------------------------------------------------------------------------------------------------
# Lecture CSV / XML
# --------------------------------------------------------------------------------------------------
def _decoder(contenu: bytes) -> str:
    try:
        return contenu.decode("utf-8-sig")
    except UnicodeDecodeError:
        return contenu.decode("cp1252")  # export Excel / SAGE Windows


def lire_csv(contenu: bytes):
    texte = _decoder(contenu)
    premiere = texte.split("\n", 1)[0]
    sep = ";" if premiere.count(";") > premiere.count(",") else ","
    lecteur = csv.DictReader(io.StringIO(texte), delimiter=sep)
    lignes = [{(k or "").strip(): (v or "").strip() if isinstance(v, str) else "" for k, v in r.items()} for r in lecteur]
    return lignes, [(c or "").strip() for c in (lecteur.fieldnames or [])]


def lire_xml(contenu: bytes):
    """`<lignes><ligne><code>…</code>…</ligne>…</lignes>` : chaque enfant de la racine est une ligne, ses sous-éléments
    (ou attributs) sont les colonnes. DTD et entités refusées (XXE / expansion d'entités)."""
    entete = contenu[:4096].upper()
    if b"<!DOCTYPE" in entete or b"<!ENTITY" in contenu.upper():
        raise FichierErreur("XML refusé : DTD / entités interdites.")
    try:
        racine = ET.fromstring(contenu)
    except ET.ParseError as exc:
        raise FichierErreur(f"XML illisible : {exc}.")
    lignes, colonnes = [], []
    for element in racine:
        ligne = {k.strip(): (v or "").strip() for k, v in element.attrib.items()}
        for enfant in element:
            ligne[enfant.tag.strip()] = (enfant.text or "").strip()
        for k in ligne:
            if k not in colonnes:
                colonnes.append(k)
        lignes.append(ligne)
    return lignes, colonnes


def lire_fichier(nom: str, contenu: bytes):
    """Retourne (format, lignes, colonnes) — XML reconnu par l'extension ou le prologue."""
    debut = contenu.lstrip()[:5]
    if nom.lower().endswith(".xml") or debut.startswith(b"<?xml") or debut.startswith(b"<"):
        return ("xml",) + lire_xml(contenu)
    return ("csv",) + lire_csv(contenu)


# --------------------------------------------------------------------------------------------------
# Conversions de champs (une anomalie = une ligne en erreur, jamais une 500)
# --------------------------------------------------------------------------------------------------
def _txt(row, cle, longueur=None):
    valeur = (row.get(cle) or "").strip()
    if longueur and len(valeur) > longueur:
        raise LigneErreur(f"{cle} : {longueur} caractères maximum ({len(valeur)}).")
    return valeur


def _req(row, cle, longueur=None):
    valeur = _txt(row, cle, longueur)
    if not valeur:
        raise LigneErreur(f"{cle} obligatoire.")
    return valeur


def _date(row, cle, obligatoire=False):
    valeur = _txt(row, cle)
    if not valeur:
        if obligatoire:
            raise LigneErreur(f"{cle} obligatoire (AAAA-MM-JJ).")
        return None
    try:
        return datetime.strptime(valeur, "%Y-%m-%d").date()
    except ValueError:
        raise LigneErreur(f"{cle} invalide (attendu AAAA-MM-JJ) : {valeur}.")


def _dec(row, cle, defaut=None, obligatoire=False, positif=True):
    valeur = _txt(row, cle).replace(" ", "").replace(" ", "").replace(",", ".")
    if not valeur:
        if obligatoire:
            raise LigneErreur(f"{cle} obligatoire.")
        return defaut
    try:
        nombre = Decimal(valeur)
    except InvalidOperation:
        raise LigneErreur(f"{cle} : nombre invalide ({valeur}).")
    if not nombre.is_finite():
        raise LigneErreur(f"{cle} : nombre invalide ({valeur}).")
    if positif and nombre < 0:
        raise LigneErreur(f"{cle} : valeur négative interdite ({valeur}).")
    return nombre


def _bool(row, cle, defaut=False):
    valeur = _txt(row, cle).lower()
    if not valeur:
        return defaut
    if valeur in ("1", "true", "oui", "yes", "o", "vrai", "x"):
        return True
    if valeur in ("0", "false", "non", "no", "n", "faux"):
        return False
    raise LigneErreur(f"{cle} : booléen attendu (oui / non), reçu {valeur}.")


def _norm(texte):
    import unicodedata

    texte = unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", texte)


def _choix(row, cle, choices, defaut=None, alias=None):
    """Valeur d'une liste fermée : code ou libellé (accents / casse ignorés), alias éventuels."""
    valeur = _txt(row, cle)
    if not valeur:
        if defaut is None:
            raise LigneErreur(f"{cle} obligatoire ({', '.join(v for v, _ in choices)}).")
        return defaut
    cible = _norm(valeur)
    for code, libelle in choices:
        if cible in (_norm(code), _norm(libelle)):
            return code
    for k, code in (alias or {}).items():
        if cible == _norm(k):
            return code
    raise LigneErreur(f"{cle} invalide : {valeur} (attendu : {', '.join(v for v, _ in choices)}).")


def _valider(obj):
    """Appelle `clean()` du modèle (règles métier) et convertit l'erreur en anomalie de ligne."""
    try:
        obj.clean()
    except DjangoValidationError as exc:
        raise LigneErreur(" ".join(exc.messages))


def _partner(code):
    from referentiels.models import Partner

    if not code:
        return None
    partner = Partner.objects.filter(code=code).first()
    if partner is None:
        raise LigneErreur(f"tiers inconnu : {code} (chargez d'abord le gabarit Tiers).")
    return partner


def _currency(code):
    from referentiels.models import Currency

    if not code:
        return None
    devise = Currency.objects.filter(code=code.upper()).first()
    if devise is None:
        raise LigneErreur(f"devise inconnue : {code}.")
    return devise


# --------------------------------------------------------------------------------------------------
# Gabarits
# --------------------------------------------------------------------------------------------------
@dataclass
class Colonne:
    nom: str
    obligatoire: bool = False
    aide: str = ""
    exemple: str = ""


@dataclass
class Gabarit:
    code: str
    libelle: str
    objet: str  # référence du plan de migration (D04, D09…)
    cle: str
    colonnes: list
    traiter: Callable
    cercle: str = "compta"  # compta | rh | paie | qualite
    sensibles: tuple = ()
    formats: tuple = ("csv", "xml")
    fichier_entier: bool = False
    options: tuple = ()  # champs complémentaires du formulaire (balance d'ouverture)
    note: str = ""


@dataclass
class Contexte:
    user: object
    blanc: bool
    options: dict = field(default_factory=dict)
    archive: object = None  # zipfile.ZipFile (gabarit GED)
    lot_id: object = None


def _tiers(row, ctx):
    from .importers import PartnerConnector, RowError

    try:
        kind, _ = PartnerConnector().handle_row(row)
    except RowError as exc:
        raise LigneErreur(str(exc))
    return ("creee" if kind == "created" else "maj"), row.get("code", "")


def _articles(row, ctx):
    from referentiels.models import Account, Article, UnitOfMeasure

    code = _req(row, "code", 30)
    defaults = {
        "label": _req(row, "libelle", 200),
        "article_type": _choix(row, "type", Article.ArticleType.choices, defaut=Article.ArticleType.MATIERE),
        "purchase_price": _dec(row, "prix_achat", Decimal("0")),
        "sale_price": _dec(row, "prix_vente", Decimal("0")),
        "is_stockable": _bool(row, "stockable", False),
        "is_active": _bool(row, "actif", True),
    }
    unite = _txt(row, "unite")
    if unite:
        defaults["unit"] = UnitOfMeasure.objects.filter(code=unite).first()
        if defaults["unit"] is None:
            raise LigneErreur(f"unité inconnue : {unite}.")
    compte = _txt(row, "compte")
    if compte:
        defaults["account"] = Account.objects.filter(code=compte).first()
        if defaults["account"] is None:
            raise LigneErreur(f"compte inconnu : {compte}.")
    _, cree = Article.objects.update_or_create(code=code, defaults=defaults)
    return ("creee" if cree else "maj"), code


def _salaries(row, ctx):
    from rh_paie.models import ContratTravail, Employe

    matricule = _req(row, "matricule", 20)
    nom = _req(row, "nom", 150)
    prenom = _txt(row, "prenom", 150)
    naissance = _date(row, "date_naissance")
    if naissance:
        homonyme = (
            Employe.objects.filter(nom__iexact=nom, prenom__iexact=prenom, date_naissance=naissance)
            .exclude(code=matricule).values_list("code", flat=True).first()
        )
        if homonyme:
            raise LigneErreur(f"doublon probable : même nom, prénom et date de naissance que le matricule {homonyme}.")
    defaults = {
        "nom": nom,
        "prenom": prenom,
        "civilite": _choix(row, "civilite", Employe.Sexe.choices, alias={"M": "masculin", "H": "masculin", "F": "feminin",
                                                                       "Mme": "feminin", "Mr": "masculin"}),
        "date_naissance": naissance,
        "lieu_naissance": _txt(row, "lieu_naissance", 120),
        "nationalite": _txt(row, "nationalite", 80),
        "categorie": _choix(row, "categorie", Employe.Categorie.choices, defaut=Employe.Categorie.OUVRIER),
        "fonction": _txt(row, "fonction", 150),
        "departement": _txt(row, "departement", 120),
        "site": _txt(row, "site", 120),
        "statut": _choix(row, "statut", Employe.Statut.choices, defaut=Employe.Statut.ACTIF),
        "date_embauche": _date(row, "date_embauche"),
        "date_sortie": _date(row, "date_sortie"),
        "telephone": _txt(row, "telephone", 40),
        "email": _txt(row, "email", 254),
        "adresse": _txt(row, "adresse", 200),
    }
    for colonne, champ in (("numero_cnss", "numero_securite_sociale"), ("matricule_cnamgs", "matricule_cnps"),
                           ("rib_banque", "rib_banque"), ("rib_guichet", "rib_guichet"),
                           ("rib_compte", "rib_compte"), ("rib_cle", "rib_cle")):
        if _txt(row, colonne):
            defaults[champ] = _txt(row, colonne)
    if _txt(row, "banque"):
        defaults["banque_nom"] = _txt(row, "banque", 24)
    parts = _dec(row, "parts_fiscales")
    if parts is not None:
        defaults["parts_fiscales"] = parts
    if defaults["statut"] == Employe.Statut.SORTI and not defaults["date_sortie"]:
        raise LigneErreur("date_sortie obligatoire pour un salarié sorti.")
    employe, cree = Employe.objects.update_or_create(code=matricule, defaults=defaults)

    debut = _date(row, "contrat_debut")
    if debut:
        numero = _txt(row, "contrat_numero", 20)
        valeurs = {
            "employe": employe,
            "type": _choix(row, "contrat_type", ContratTravail.Type.choices, defaut=ContratTravail.Type.CDI),
            "date_debut": debut,
            "date_fin": _date(row, "contrat_fin"),
            "salaire_base": _dec(row, "salaire_base", Decimal("0")),
            "lieu_affectation": _txt(row, "lieu_affectation", 120),
            "regime_horaire": _txt(row, "regime_horaire", 40),
            "statut": _choix(row, "contrat_statut", ContratTravail.Statut.choices, defaut=ContratTravail.Statut.ACTIF),
        }
        contrat = (ContratTravail.objects.filter(code=numero).first() if numero
                   else ContratTravail.objects.filter(employe=employe, date_debut=debut).first())
        if contrat is not None and contrat.employe_id != employe.pk:
            raise LigneErreur(f"contrat {numero} déjà rattaché à un autre salarié ({contrat.employe.code}).")
        if contrat is None:
            contrat = ContratTravail(code=numero, **valeurs)
        else:
            for k, v in valeurs.items():
                setattr(contrat, k, v)
        _valider(contrat)
        contrat.notes = contrat.notes or "Reprise ALAN (migration)"
        contrat.save()
    elif _txt(row, "contrat_numero"):
        raise LigneErreur("contrat_debut obligatoire quand contrat_numero est renseigné.")
    return ("creee" if cree else "maj"), matricule


def _periode(row):
    valeur = _req(row, "periode")
    for fmt in ("%Y-%m", "%Y-%m-%d"):
        try:
            jour = datetime.strptime(valeur, fmt).date()
            return jour.replace(day=1)
        except ValueError:
            continue
    raise LigneErreur(f"periode invalide (attendu AAAA-MM) : {valeur}.")


def _paie_historique(row, ctx):
    from rh_paie.models import Employe

    matricule = _req(row, "matricule")
    employe = Employe.objects.filter(code=matricule).first()
    if employe is None:
        raise LigneErreur(f"salarié inconnu : {matricule} (chargez d'abord le gabarit Salariés).")
    periode = _periode(row)
    if periode > timezone.localdate():
        raise LigneErreur("période future : seul l'historique est repris.")
    rubrique = _req(row, "rubrique", 30).upper()
    _, cree = HistoriquePaie.objects.update_or_create(
        employe=employe, periode=periode, rubrique=rubrique,
        defaults={
            "libelle": _txt(row, "libelle", 150),
            "nature": _choix(row, "nature", HistoriquePaie.Nature.choices, defaut=HistoriquePaie.Nature.CUMUL),
            "base": _dec(row, "base", positif=False),
            "montant": _dec(row, "montant", obligatoire=True, positif=False),
            "lot_id": ctx.lot_id,
        },
    )
    return ("creee" if cree else "maj"), f"{matricule}/{periode:%Y-%m}/{rubrique}"


PROCEDES_ISO4063 = {"111": "smaw", "141": "gtaw", "135": "gmaw", "136": "fcaw", "138": "fcaw", "tig": "gtaw",
                    "mig": "gmaw", "mag": "gmaw", "electrode": "smaw"}
NORMES = {"iso 9606": "iso9606", "iso9606-1": "iso9606", "iso 15614": "iso9606", "asme": "asme_ix", "asme ix": "asme_ix"}


def _wps(row, ctx):
    from qualite.models import QualificationSoudeur, WpsWpqr

    numero = _req(row, "numero", 20)
    type_doc = _choix(row, "type", WpsWpqr.Type.choices, defaut=WpsWpqr.Type.WPS)
    valeurs = {
        "type": type_doc,
        "reference": _txt(row, "reference", 80),
        "norme": _choix(row, "norme", QualificationSoudeur.Norme.choices, defaut=QualificationSoudeur.Norme.ISO_9606,
                        alias=NORMES),
        "procede": _choix(row, "procede", QualificationSoudeur.Procede.choices, defaut=QualificationSoudeur.Procede.SMAW,
                          alias=PROCEDES_ISO4063),
        "materiau": _txt(row, "materiau", 120),
        "position": _txt(row, "position", 60),
        "epaisseur": _txt(row, "epaisseur", 120),
        "gaz_protection": _txt(row, "gaz_protection", 120),
        "revue": _txt(row, "revue", 60),
        "statut": _choix(row, "statut", WpsWpqr.Statut.choices, defaut=WpsWpqr.Statut.VALIDE),
        "date_validation": _date(row, "date_validation"),
    }
    support = _txt(row, "wpqr_support")
    if support:
        if type_doc != WpsWpqr.Type.WPS:
            raise LigneErreur("wpqr_support ne concerne qu'un WPS.")
        valeurs["wpqr"] = WpsWpqr.objects.filter(code=support, type=WpsWpqr.Type.WPQR).first()
        if valeurs["wpqr"] is None:
            raise LigneErreur(f"WPQR support inconnu : {support} (placez les WPQR avant les WPS).")
    _, cree = WpsWpqr.objects.update_or_create(code=numero, defaults=valeurs)
    return ("creee" if cree else "maj"), numero


def _soudeurs(row, ctx):
    from qualite.models import QualificationSoudeur, Soudeur
    from rh_paie.models import Employe

    code = _req(row, "soudeur_code", 20)
    matricule = _txt(row, "matricule", 60)
    valeurs = {
        "nom": _req(row, "nom", 150),
        "prenoms": _txt(row, "prenoms", 150),
        "matricule": matricule,
        "qualification": _txt(row, "qualification_principale", 120),
        "is_active": _bool(row, "actif", True),
    }
    if matricule:
        employe = Employe.objects.filter(code=matricule).first()
        if employe is not None:
            valeurs["employe"] = employe
    soudeur, cree = Soudeur.objects.update_or_create(code=code, defaults=valeurs)

    numero = _txt(row, "qualification_numero", 20)
    if not numero:
        return ("creee" if cree else "maj"), code
    qualif = QualificationSoudeur.objects.filter(code=numero).first()
    if qualif is not None and qualif.soudeur_id != soudeur.pk:
        raise LigneErreur(f"qualification {numero} déjà rattachée au soudeur {qualif.soudeur.code}.")
    q_valeurs = {
        "soudeur": soudeur,
        "norme": _choix(row, "norme", QualificationSoudeur.Norme.choices, defaut=QualificationSoudeur.Norme.ISO_9606,
                        alias=NORMES),
        "procede": _choix(row, "procede", QualificationSoudeur.Procede.choices, defaut=QualificationSoudeur.Procede.SMAW,
                          alias=PROCEDES_ISO4063),
        "position": _txt(row, "position", 60),
        "groupe_materiaux": _txt(row, "groupe_materiaux", 120),
        "epaisseur_min": _dec(row, "epaisseur_min", Decimal("0")),
        "epaisseur_max": _dec(row, "epaisseur_max", Decimal("0")),
        "gamme_diametre": _txt(row, "gamme_diametre", 120),
        "date_qualification": _date(row, "date_qualification", obligatoire=True),
        "date_validite": _date(row, "date_validite", obligatoire=True),
        "certificat": _txt(row, "certificat", 80),
        "statut": _choix(row, "statut", QualificationSoudeur.Statut.choices, defaut=QualificationSoudeur.Statut.VALIDE),
    }
    if qualif is None:
        qualif = QualificationSoudeur(code=numero, **q_valeurs)
        q_cree = True
    else:
        for k, v in q_valeurs.items():
            setattr(qualif, k, v)
        q_cree = False
    _valider(qualif)  # date de validité ≥ qualification ; validité dépassée ⇒ « expirée »
    qualif.save()
    return ("creee" if (cree or q_cree) else "maj"), f"{code}/{numero}"


def _affaires(row, ctx):
    from commercial.models import Affaire, ClientProfile

    code = _req(row, "code", 20)
    existante = Affaire.objects.filter(code=code).first()
    if existante and existante.status in (Affaire.Status.CLOTUREE, Affaire.Status.ARCHIVEE):
        raise LigneErreur(f"affaire {code} clôturée / archivée : non modifiable.")
    partner = _partner(_txt(row, "client"))
    gr = _bool(row, "global_rental", False)
    if gr and partner is not None and not partner.is_global_rental:
        raise LigneErreur("affaire GLOBAL RENTAL : le client doit être un tiers is_global_rental (compte 618).")
    statut = _choix(row, "statut", [c for c in Affaire.Status.choices if c[0] in ("brouillon", "confirmee", "en_cours")],
                    defaut=Affaire.Status.EN_COURS)
    valeurs = {
        "title": _req(row, "intitule", 200),
        "description": _txt(row, "description"),
        "affaire_type": _choix(row, "type", Affaire.AffaireType.choices, defaut=Affaire.AffaireType.ATELIER),
        "currency": _currency(_txt(row, "devise")),
        "contract_amount": _dec(row, "montant_contractuel", Decimal("0")),
        "margin": _dec(row, "marge", Decimal("0"), positif=False),
        "status": statut,
        "start_date": _date(row, "debut"),
        "end_date": _date(row, "fin"),
        "is_global_rental": gr,
        "client": ClientProfile.objects.get_or_create(partner=partner)[0] if partner else None,
    }
    affaire = existante or Affaire(code=code)
    for k, v in valeurs.items():
        setattr(affaire, k, v)
    _valider(affaire)
    affaire.save()
    if statut != Affaire.Status.BROUILLON:
        affaire.assurer_compte_analytique()  # axe projet : coûts et marges M10 / M11
    return ("maj" if existante else "creee"), code


def _contrats(row, ctx):
    from commercial.models import Affaire, ClientProfile, Contract

    code = _req(row, "code", 20)
    existant = Contract.objects.filter(code=code).first()
    if existant and existant.status != Contract.Status.BROUILLON:
        raise LigneErreur(f"contrat {code} déjà signé / actif : toute modification passe par un avenant.")
    affaire = None
    if _txt(row, "affaire"):
        affaire = Affaire.objects.filter(code=_txt(row, "affaire")).first()
        if affaire is None:
            raise LigneErreur(f"affaire inconnue : {_txt(row, 'affaire')} (chargez d'abord le gabarit Affaires).")
    partner = _partner(_txt(row, "client"))
    gr = _bool(row, "global_rental", False)
    if gr and partner is not None and not partner.is_global_rental:
        raise LigneErreur("contrat GLOBAL RENTAL : le client doit être un tiers is_global_rental (compte 618).")
    mois = _dec(row, "mois")
    valeurs = {
        "affaire": affaire,
        "client": ClientProfile.objects.get_or_create(partner=partner)[0] if partner else None,
        "profile": _choix(row, "profil", Contract.Profile.choices),
        "start_date": _date(row, "debut", obligatoire=True),
        "end_date": _date(row, "fin"),
        "months": int(mois) if mois is not None else None,
        "amount_initial": _dec(row, "montant_initial", Decimal("0")),
        "currency": _currency(_txt(row, "devise")),
        "sla": _txt(row, "sla", 200),
        "retenue_rate": _dec(row, "taux_retenue"),
        "indexation": _bool(row, "indexation", False),
        "penalty": _dec(row, "penalites"),
        "is_global_rental": gr,
        "notes": ("[Reprise migration] " + _txt(row, "notes")).strip(),
        "status": Contract.Status.BROUILLON,  # l'activation exige le contrat signé en GED (circuit M1)
    }
    contrat = existant or Contract(code=code)
    for k, v in valeurs.items():
        setattr(contrat, k, v)
    _valider(contrat)
    contrat.save()
    return ("maj" if existant else "creee"), code


REF_OUVERTURE = "REPRISE-OUVERTURE"


def _stocks_ouverture(row, ctx):
    from referentiels.models import Article
    from stocks.models import Depot, LotMatiere, MouvementStock
    from stocks.services import apply_move

    code_depot = _req(row, "depot", 20)
    depot = Depot.objects.filter(code=code_depot).first()
    if depot is None:
        if not _txt(row, "depot_libelle"):
            raise LigneErreur(f"dépôt inconnu : {code_depot} (renseignez depot_libelle pour le créer).")
        depot = Depot.objects.create(code=code_depot, label=_txt(row, "depot_libelle", 200))
    article = Article.objects.filter(code=_req(row, "article")).first()
    if article is None:
        raise LigneErreur(f"article inconnu : {_txt(row, 'article')} (chargez d'abord le gabarit Articles).")
    quantite = _dec(row, "quantite", obligatoire=True)
    if quantite <= 0:
        raise LigneErreur("quantite doit être strictement positive.")
    jour = _date(row, "date", obligatoire=True)
    numero_lot = _txt(row, "numero_lot", 80)
    lot = None
    if numero_lot:
        lot = LotMatiere.objects.filter(article=article, numero_lot=numero_lot).first()
    cle = f"{depot.code}/{article.code}/{numero_lot or '-'}"
    deja = MouvementStock.objects.filter(
        type_mouvement=MouvementStock.Type.INVENTAIRE, destination=depot, article=article, lot=lot,
        document_reference=REF_OUVERTURE,
    )
    if (lot is not None or not numero_lot) and deja.exists():
        return "doublon", cle
    if numero_lot and lot is None:
        lot = LotMatiere.objects.create(
            article=article, numero_lot=numero_lot, numero_coulee=_txt(row, "numero_coulee", 80),
            date_reception=jour, quantite_initiale=quantite, quantite_restante=0,
        )
    mouvement = MouvementStock(
        type_mouvement=MouvementStock.Type.INVENTAIRE, article=article, quantite=quantite,
        prix_unitaire=_dec(row, "prix_unitaire", Decimal("0")), destination=depot, lot=lot, date=jour,
        document_reference=REF_OUVERTURE, created_by=ctx.user, notes="Stock d'ouverture (reprise migration)",
    )
    _valider(mouvement)
    mouvement.save()
    try:
        apply_move(mouvement)
    except ValueError as exc:
        raise LigneErreur(str(exc))
    return "creee", cle


def _balance_ouverture(lignes, ctx):
    """Fichier entier : délègue au gabarit G3 existant (`opening.import_opening_balance`) après lecture CSV / XML."""
    from .opening import OpeningConflict, import_opening_balance

    tampon = io.StringIO()
    ecrivain = csv.DictWriter(tampon, fieldnames=["compte", "debit", "credit", "libelle"], extrasaction="ignore")
    ecrivain.writeheader()
    for ligne in lignes:
        ecrivain.writerow({k: ligne.get(k, "") for k in ("compte", "debit", "credit", "libelle")})
    try:
        move, rejeu = import_opening_balance(
            tampon.getvalue().encode("utf-8"), ctx.options.get("date"), ctx.user, ctx.options.get("total_controle")
        )
    except OpeningConflict as exc:
        raise LigneErreur(str(exc))
    except DjangoValidationError as exc:
        raise LigneErreur(" ".join(exc.messages))
    return ("doublon" if rejeu else "creee"), move.reference


def _ged(row, ctx):
    from django.core.files.base import ContentFile

    from documents.models import Document, DocumentType, Dossier, Version

    nom = _req(row, "fichier")
    try:
        info = ctx.archive.getinfo(nom)
    except KeyError:
        raise LigneErreur(f"fichier absent du lot : {nom}.")
    contenu = ctx.archive.read(info)
    empreinte = hashlib.sha256(contenu).hexdigest()
    attendue = _txt(row, "sha256").lower()
    if attendue and attendue != empreinte:
        raise LigneErreur(f"empreinte SHA-256 différente du bordereau (calculée {empreinte}).")
    if Document.objects.filter(sha256=empreinte).exists():
        return "doublon", empreinte
    code_type = _txt(row, "type", 60)
    type_doc = None
    if code_type:
        type_doc = DocumentType.objects.filter(code=code_type).first()
        if type_doc is None:
            if not _txt(row, "type_libelle"):
                raise LigneErreur(f"type de document inconnu : {code_type} (renseignez type_libelle pour le créer).")
            retention = _dec(row, "retention_annees")
            type_doc = DocumentType.objects.create(code=code_type, label=_txt(row, "type_libelle", 120),
                                                   retention_years=int(retention) if retention is not None else None)
    statut = _choix(row, "statut", [("archived", "Archivé"), ("draft", "Brouillon")], defaut="archived",
                    alias={"archive": "archived", "brouillon": "draft"})
    if statut == "archived" and type_doc is not None and type_doc.officiel:
        statut = "draft"  # document officiel : archivage seulement après signature avancée (M12)
    jour = _date(row, "date")
    mots = [m.strip() for m in re.split(r"[;|]", _txt(row, "mots_cles")) if m.strip()]
    if ctx.blanc:
        return "creee", empreinte
    dossier = None
    for segment in [s.strip() for s in re.split(r"[/\\]", _txt(row, "dossier")) if s.strip()]:
        dossier, _ = Dossier.objects.get_or_create(parent=dossier, name=segment[:200],
                                                   defaults={"created_by": ctx.user})
    document = Document.objects.create(
        title=(_txt(row, "titre") or nom.rsplit("/", 1)[-1])[:255], status=statut, type=type_doc, dossier=dossier,
        archived_at=timezone.now() if statut == "archived" else None, document_date=jour,
        counterparty=_txt(row, "tiers", 200), project=_txt(row, "affaire", 200), reference=_txt(row, "reference", 200),
        keywords=mots + ["reprise"], sha256=empreinte, created_by=ctx.user,
    )
    version = Version.objects.create(
        document=document, number=1, file=ContentFile(contenu, name=nom.rsplit("/", 1)[-1]), sha256=empreinte,
        size=len(contenu), original_filename=nom.rsplit("/", 1)[-1][:255], note="Reprise (migration)", created_by=ctx.user,
    )
    document.current_version = version
    document.save(update_fields=["current_version"])
    return "creee", empreinte


C = Colonne
GABARITS = {
    g.code: g
    for g in [
        Gabarit("tiers", "Tiers (clients, fournisseurs, GLOBAL RENTAL)", "D03", "code", [
            C("code", True, "Code tiers (20 car.)", "CLI-001"), C("name", True, "Raison sociale", "TOTAL GABON"),
            C("kind", False, "client / fournisseur / both / autre", "client"), C("tax_id", False, "NIF", "123456"),
            C("phone"), C("email"), C("is_global_rental", False, "1 = intra-groupe (compte 618)", "0"),
            C("currency_code", False, "Devise ISO", "XAF"),
        ], _tiers, note="Même règle que le gabarit G1 (/api/integrations/import/), avec lecture XML, à blanc et rapport."),
        Gabarit("articles", "Articles, matières et prestations", "D04", "code", [
            C("code", True, "Code article (30 car.)", "MAT-TUBE-6"), C("libelle", True, "Désignation", "Tube acier 6 pouces"),
            C("type", False, "produit / service / matiere / consommable", "matiere"), C("unite", False, "Code unité", "U"),
            C("prix_achat", False, "", "125000"), C("prix_vente", False, "", "0"), C("compte", False, "Compte SYSCOHADA", ""),
            C("stockable", False, "oui / non", "oui"), C("actif", False, "oui / non", "oui"),
        ], _articles),
        Gabarit("salaries", "Salariés et contrats de travail", "D09", "matricule (+ contrat_numero)", [
            C("matricule", True, "Matricule ALAN conservé", "EMP-0042"), C("nom", True, "", "MOUSSAVOU"),
            C("prenom", False, "", "Jean"), C("civilite", True, "masculin / feminin (M / F)", "M"),
            C("date_naissance", False, "AAAA-MM-JJ", "1985-04-12"), C("lieu_naissance"), C("nationalite", False, "", "Gabonaise"),
            C("categorie", False, "cadre / agent_maitrise / technicien / ouvrier", "ouvrier"), C("fonction", False, "", "Soudeur"),
            C("departement", False, "", "Atelier"), C("site", False, "", "Port-Gentil"),
            C("statut", False, "actif / conge / suspendu / sorti", "actif"), C("date_embauche", False, "AAAA-MM-JJ", "2019-01-07"),
            C("date_sortie"), C("telephone"), C("email"), C("adresse"),
            C("numero_cnss", False, "Chiffré", ""), C("matricule_cnamgs", False, "Chiffré", ""),
            C("rib_banque", False, "Chiffré", ""), C("rib_guichet", False, "Chiffré", ""), C("rib_compte", False, "Chiffré", ""),
            C("rib_cle", False, "Chiffré", ""), C("banque"), C("parts_fiscales", False, "", "1"),
            C("contrat_numero", False, "N° contrat source (clé)", "CTR-2019-042"),
            C("contrat_type", False, "cdd / cdi / chantier / mission / stage / expatrie", "cdi"),
            C("contrat_debut", False, "AAAA-MM-JJ (crée le contrat)", "2019-01-07"), C("contrat_fin"),
            C("salaire_base", False, "FCFA", "450000"), C("contrat_statut", False, "actif / essai / expire / resilie", "actif"),
            C("lieu_affectation"), C("regime_horaire"),
        ], _salaries, cercle="rh", sensibles=("numero_cnss", "matricule_cnamgs", "rib_banque", "rib_guichet", "rib_compte",
                                              "rib_cle", "salaire_base")),
        Gabarit("paie_historique", "Historique de paie 12 mois (cumuls par rubrique)", "D10", "matricule + periode + rubrique", [
            C("matricule", True, "Salarié déjà chargé", "EMP-0042"), C("periode", True, "AAAA-MM", "2026-09"),
            C("rubrique", True, "Code rubrique ALAN", "BRUT"), C("libelle", False, "", "Salaire brut"),
            C("nature", False, "gain / retenue / cot_sal / cot_pat / cumul", "cumul"), C("base"),
            C("montant", True, "FCFA", "450000"),
        ], _paie_historique, cercle="paie", sensibles=("base", "montant"),
            note="Lecture seule après chargement (aucune saisie à l'écran) ; sert au contrôle C6."),
        Gabarit("wps_wpqr", "WPS / WPQR (procédures de soudage)", "D13", "numero", [
            C("numero", True, "N° WPS / WPQR (20 car.)", "WPQR-012"), C("type", False, "wps / wpqr", "wpqr"),
            C("reference"), C("norme", False, "iso9606 / asme_ix", "iso9606"),
            C("procede", False, "smaw / gtaw / gmaw / fcaw (ou 111 / 141 / 135 / 136)", "141"),
            C("materiau"), C("position", False, "", "PF"), C("epaisseur"), C("gaz_protection"), C("revue"),
            C("statut", False, "brouillon / valide / obsolete", "valide"), C("date_validation", False, "AAAA-MM-JJ", "2025-03-01"),
            C("wpqr_support", False, "N° du WPQR (WPS seulement)", ""),
        ], _wps, cercle="qualite", note="Placez les WPQR avant les WPS qui s'y appuient."),
        Gabarit("soudeurs", "Soudeurs et qualifications", "D13", "soudeur_code (+ qualification_numero)", [
            C("soudeur_code", True, "Code soudeur (20 car.)", "SOU-007"), C("nom", True, "", "NDONG"), C("prenoms", False, "", "Paul"),
            C("matricule", False, "Matricule salarié (lien M9)", "EMP-0042"), C("qualification_principale"),
            C("actif", False, "oui / non", "oui"), C("qualification_numero", False, "N° qualification (clé)", "Q-2025-031"),
            C("norme", False, "iso9606 / asme_ix", "iso9606"), C("procede", False, "smaw / gtaw / gmaw / fcaw", "smaw"),
            C("position"), C("groupe_materiaux"), C("epaisseur_min"), C("epaisseur_max"), C("gamme_diametre"),
            C("date_qualification", False, "AAAA-MM-JJ (si qualification)", "2025-02-10"),
            C("date_validite", False, "AAAA-MM-JJ (si qualification)", "2027-02-10"), C("certificat"),
            C("statut", False, "valide / expiree / suspendue", "valide"),
        ], _soudeurs, cercle="qualite", note="Une ligne par qualification ; la validité dépassée passe la qualification en « expirée »."),
        Gabarit("affaires", "Affaires en cours (en-cours commerciaux)", "D06", "code", [
            C("code", True, "Code affaire (20 car.)", "AFF-2026-014"), C("intitule", True, "", "Maintenance pipeline"),
            C("client", False, "Code tiers", "CLI-001"), C("type", False, "chantier / atelier / maintenance / fourniture", "chantier"),
            C("devise", False, "", "XAF"), C("montant_contractuel"), C("marge"),
            C("statut", False, "brouillon / confirmee / en_cours", "en_cours"), C("debut", False, "AAAA-MM-JJ", ""),
            C("fin"), C("global_rental", False, "oui / non", "non"), C("description"),
        ], _affaires, note="Une affaire confirmée / en cours reçoit son compte analytique (axe projet)."),
        Gabarit("contrats", "Contrats commerciaux", "D08", "code", [
            C("code", True, "N° contrat (20 car.)", "CTT-2025-003"), C("profil", True, "marche_travaux / maintenance", "maintenance"),
            C("debut", True, "AAAA-MM-JJ", "2025-01-01"), C("fin"), C("mois"), C("affaire", False, "Code affaire", ""),
            C("client", False, "Code tiers", "CLI-001"), C("montant_initial"), C("devise", False, "", "XAF"), C("sla"),
            C("taux_retenue"), C("indexation", False, "oui / non", "non"), C("penalites"),
            C("global_rental", False, "oui / non", "non"), C("notes"),
        ], _contrats, note="Chargé en brouillon : l'activation exige le contrat signé archivé en GED (circuit M1)."),
        Gabarit("stocks_ouverture", "Stocks d'ouverture par dépôt (et lot)", "D05", "depot + article + numero_lot", [
            C("depot", True, "Code dépôt", "MAG-PG"), C("depot_libelle", False, "Crée le dépôt s'il est absent", ""),
            C("article", True, "Code article", "MAT-TUBE-6"), C("quantite", True, "", "120"),
            C("prix_unitaire", False, "Valeur unitaire", "125000"), C("numero_lot"), C("numero_coulee"),
            C("date", True, "Date d'inventaire de bascule", "2026-12-31"),
        ], _stocks_ouverture, note="Un mouvement d'inventaire tracé par ligne (référence REPRISE-OUVERTURE) ; jamais deux ouvertures."),
        Gabarit("balance_ouverture", "Balance d'ouverture (à-nouveaux SAGE)", "D11", "exercice (AN-<année>)", [
            C("compte", True, "Compte du plan ERP", "521100"), C("debit", True, "", "1500000"), C("credit", True, "", "0"),
            C("libelle"),
        ], None, fichier_entier=True, options=("date", "total_controle"),
            note="Même contrôle que G3 : équilibre, total SAGE, une seule écriture AN par exercice."),
        Gabarit("ged", "Documents GED en masse (ZIP + manifeste)", "D16", "SHA-256 du fichier", [
            C("fichier", True, "Chemin dans le ZIP", "contrats/CTT-2025-003.pdf"), C("titre"),
            C("type", False, "Code type de document", "contrat"), C("type_libelle", False, "Crée le type s'il est absent", ""),
            C("retention_annees"), C("date", False, "AAAA-MM-JJ", ""), C("dossier", False, "Chemin « A / B »", "Contrats / 2025"),
            C("tiers"), C("affaire"), C("reference"), C("mots_cles", False, "séparés par ;", ""),
            C("sha256", False, "Empreinte du bordereau (contrôle C9)", ""), C("statut", False, "archived / draft", "archived"),
        ], _ged, formats=("zip",), note="ZIP contenant manifeste.csv (ou manifeste.xml) et les fichiers ; empreinte calculée."),
    ]
}


# --------------------------------------------------------------------------------------------------
# Droits par gabarit
# --------------------------------------------------------------------------------------------------
def _cercle_compta(user):
    from accounting_kernel.permissions import POSTING_ROLES

    return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser or user.role in POSTING_ROLES))


def peut_gabarit(user, gabarit):
    from users.models import User

    if not (user and user.is_authenticated):
        return False
    if gabarit.cercle == "paie":
        from rh_paie.services import can_manage_paie

        return can_manage_paie(user)
    if _cercle_compta(user):
        return True
    return (gabarit.cercle == "rh" and user.role == User.Role.RH) or (
        gabarit.cercle == "qualite" and user.role == User.Role.QAQC
    )


def gabarits_autorises(user):
    return [g for g in GABARITS.values() if peut_gabarit(user, g)]


# --------------------------------------------------------------------------------------------------
# Modèles vides
# --------------------------------------------------------------------------------------------------
def modele_vide(gabarit, fmt):
    colonnes = [c.nom for c in gabarit.colonnes]
    exemple = {c.nom: c.exemple for c in gabarit.colonnes}
    if fmt == "xml":
        racine = ET.Element("lignes", {"gabarit": gabarit.code})
        ligne = ET.SubElement(racine, "ligne")
        for nom in colonnes:
            ET.SubElement(ligne, nom).text = exemple[nom]
        return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(racine, encoding="utf-8")
    tampon = io.StringIO()
    ecrivain = csv.writer(tampon)
    ecrivain.writerow(colonnes)
    ecrivain.writerow([exemple[n] for n in colonnes])
    return ("﻿" + tampon.getvalue()).encode("utf-8")


# --------------------------------------------------------------------------------------------------
# Exécution d'un lot
# --------------------------------------------------------------------------------------------------
class _Annuler(Exception):
    pass


def _lire_lot_ged(contenu, user):
    plafond = get_param_reprise("TAILLE_MAX_LOT_GED_MO") * 1024 * 1024
    try:
        archive = zipfile.ZipFile(io.BytesIO(contenu))
    except zipfile.BadZipFile:
        raise FichierErreur("lot GED : archive ZIP attendue.")
    infos = archive.infolist()
    if len(infos) > 20000:
        raise FichierErreur("lot GED : 20 000 fichiers maximum par archive.")
    if sum(i.file_size for i in infos) > plafond:
        raise FichierErreur(f"lot GED : taille décompressée supérieure à {plafond / 1024 / 1024:.0f} Mo (paramètre).")
    manifeste = next((i for i in infos if i.filename.rsplit("/", 1)[-1].lower() in ("manifeste.csv", "manifeste.xml")), None)
    if manifeste is None:
        raise FichierErreur("lot GED : manifeste.csv (ou manifeste.xml) absent de l'archive.")
    fmt, lignes, colonnes = lire_fichier(manifeste.filename, archive.read(manifeste))
    return archive, lignes, colonnes


def _masquer(gabarit, ligne):
    return {k: (MASQUE if k in gabarit.sensibles and v else v) for k, v in ligne.items()}


def executer_lot(code, nom, contenu, user, mode=LotReprise.Mode.BLANC, force=False, options=None):
    """Retourne `(lot, rejeu)`. Lève FichierErreur seulement pour un gabarit inconnu (400)."""
    gabarit = GABARITS.get(code)
    if gabarit is None:
        raise FichierErreur(f"gabarit inconnu : {code}.")
    empreinte = hashlib.sha256(contenu).hexdigest()
    if mode == LotReprise.Mode.REEL and not force:
        deja = LotReprise.objects.filter(
            gabarit=code, empreinte=empreinte, mode=LotReprise.Mode.REEL,
            statut__in=[LotReprise.Statut.SUCCES, LotReprise.Statut.PARTIEL],
        ).first()
        if deja is not None:
            return deja, True

    seuil = get_param_reprise("TAUX_ERREUR_MAX")
    lot = LotReprise(gabarit=code, mode=mode, fichier=nom[:255], empreinte=empreinte, cree_par=user,
                     seuil_erreur=seuil, format="zip" if "zip" in gabarit.formats else "csv")
    if "zip" not in gabarit.formats:
        lot.format = "xml" if nom.lower().endswith(".xml") else "csv"
    lot.statut, lot.message = LotReprise.Statut.ECHEC, "Chargement en cours."
    lot.save()  # avant les lignes : l'historique de paie y est rattaché
    ctx = Contexte(user=user, blanc=(mode == LotReprise.Mode.BLANC), options=options or {}, lot_id=lot.pk)
    try:
        if gabarit.formats == ("zip",):
            ctx.archive, lignes, colonnes = _lire_lot_ged(contenu, user)
        else:
            plafond = get_param_reprise("TAILLE_MAX_FICHIER_MO") * 1024 * 1024
            if len(contenu) > plafond:
                raise FichierErreur(f"fichier supérieur à {plafond / 1024 / 1024:.0f} Mo (paramètre).")
            lot.format, lignes, colonnes = lire_fichier(nom, contenu)
        manquantes = [c.nom for c in gabarit.colonnes if c.obligatoire and c.nom not in colonnes]
        if manquantes:
            raise FichierErreur("Colonnes manquantes : " + ", ".join(manquantes) + ".")
        if not lignes:
            raise FichierErreur("Fichier vide.")
        for opt in gabarit.options:
            if opt == "date" and not ctx.options.get("date"):
                raise FichierErreur("date obligatoire (1er jour de l'exercice).")
    except FichierErreur as exc:
        lot.statut, lot.message = LotReprise.Statut.ECHEC, str(exc)
        lot.save()
        return lot, False

    resultats = []
    rejet = False
    try:
        with transaction.atomic():
            if gabarit.fichier_entier:
                try:
                    with transaction.atomic():
                        statut, cle = _balance_ouverture(lignes, ctx)
                    resultats.append((1, statut, cle, {"lignes": str(len(lignes))}, ""))
                except LigneErreur as exc:
                    resultats.append((1, "erreur", "", {"lignes": str(len(lignes))}, str(exc)))
            else:
                if gabarit.code == "ged" and not ctx.blanc:
                    # GED : pré-contrôle sans écriture (les fichiers stockés ne se « rollbackent » pas).
                    ctx_pre = Contexte(user=user, blanc=True, options=ctx.options, archive=ctx.archive)
                    erreurs_pre = 0
                    for ligne in lignes:
                        try:
                            with transaction.atomic():
                                gabarit.traiter(ligne, ctx_pre)
                        except Exception:  # noqa: BLE001
                            erreurs_pre += 1
                    if Decimal(erreurs_pre * 100) / len(lignes) > seuil:
                        ctx.blanc = True  # rejet annoncé : on rejoue la validation sans rien stocker
                for numero, ligne in enumerate(lignes, start=1):
                    try:
                        with transaction.atomic():
                            statut, cle = gabarit.traiter(ligne, ctx)
                        resultats.append((numero, statut, str(cle)[:200], _masquer(gabarit, ligne), ""))
                    except (LigneErreur, DjangoValidationError, ValueError) as exc:
                        message = " ".join(exc.messages) if isinstance(exc, DjangoValidationError) else str(exc)
                        resultats.append((numero, "erreur", "", _masquer(gabarit, ligne), message))
                    except Exception as exc:  # noqa: BLE001 — une ligne ne fait jamais tomber le lot
                        resultats.append((numero, "erreur", "", _masquer(gabarit, ligne), f"erreur inattendue : {exc!r}"))
            erreurs = sum(1 for r in resultats if r[1] == "erreur")
            taux = (Decimal(erreurs * 100) / len(resultats)).quantize(Decimal("0.01")) if resultats else Decimal("0")
            rejet = taux > seuil
            if mode == LotReprise.Mode.BLANC or rejet or ctx.blanc:
                raise _Annuler
    except _Annuler:
        pass

    lot.lignes = len(resultats)
    lot.creees = sum(1 for r in resultats if r[1] == "creee")
    lot.mises_a_jour = sum(1 for r in resultats if r[1] == "maj")
    lot.doublons = sum(1 for r in resultats if r[1] == "doublon")
    lot.erreurs = sum(1 for r in resultats if r[1] == "erreur")
    lot.taux_erreur = (Decimal(lot.erreurs * 100) / lot.lignes).quantize(Decimal("0.01")) if lot.lignes else Decimal("0")
    if rejet:
        lot.statut = LotReprise.Statut.REJETE
        lot.message = (f"Taux d'erreur {lot.taux_erreur} % supérieur au seuil toléré {seuil} % : "
                       + ("aucune écriture (à blanc)." if mode == LotReprise.Mode.BLANC else "rien n'a été écrit."))
    elif mode == LotReprise.Mode.BLANC:
        lot.statut = LotReprise.Statut.VALIDE
        lot.message = "Validation à blanc : rien n'a été écrit."
    else:
        lot.statut = LotReprise.Statut.PARTIEL if lot.erreurs else LotReprise.Statut.SUCCES
    if force and mode == LotReprise.Mode.REEL:
        lot.rejeu_de = (LotReprise.objects.filter(gabarit=code, empreinte=empreinte, mode=LotReprise.Mode.REEL)
                        .exclude(pk=lot.pk).first())
    with transaction.atomic():
        lot.save()
        LigneReprise.objects.bulk_create([
            LigneReprise(lot=lot, numero=n, statut=s, cle=c, donnees=d, erreur=e) for n, s, c, d, e in resultats
        ])
    return lot, False


def rapport_csv(lot):
    tampon = io.StringIO()
    ecrivain = csv.writer(tampon, delimiter=";")
    ecrivain.writerow(["lot", "gabarit", "mode", "fichier", "ligne", "statut", "cle", "anomalie", "donnees"])
    for ligne in lot.lignes_rapport.all():
        ecrivain.writerow([str(lot.pk), lot.gabarit, lot.mode, lot.fichier, ligne.numero, ligne.get_statut_display(),
                           ligne.cle, ligne.erreur, "; ".join(f"{k}={v}" for k, v in ligne.donnees.items())])
    return ("﻿" + tampon.getvalue()).encode("utf-8")


def echantillon(gabarit, taille):
    """C10 : tirage aléatoire de `taille` clés chargées (dernier lot réel abouti du gabarit)."""
    lot = LotReprise.objects.filter(
        gabarit=gabarit, mode=LotReprise.Mode.REEL, statut__in=[LotReprise.Statut.SUCCES, LotReprise.Statut.PARTIEL]
    ).first()
    if lot is None:
        return None, []
    cles = list(lot.lignes_rapport.filter(statut__in=["creee", "maj"]).values_list("cle", flat=True))
    return lot, sorted(random.sample(cles, min(int(taille), len(cles))))

