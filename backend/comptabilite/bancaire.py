"""Lecture des relevés bancaires MT940 et CFONB 120 (M10, RF-ERP-91) — module PUR (aucun accès base).

⚠ Gabarits STANDARD, testés sur des fichiers fabriqués : ETSL n'a pas encore fourni ses relevés réels.
Une banque peut s'écarter du standard (positions, codes) : tout écart se corrige ici, dans un seul fichier.

Convention des lignes : `credit` = argent ENTRANT sur le compte (crédit bancaire, MT940 « C »),
`debit` = argent SORTANT. Les soldes sont signés (débiteur < 0).

Résultat de `parse_*` : dict {format, compte, devise, date_debut, date_fin, solde_initial, solde_final,
lignes: [{date, libelle, reference, debit, credit}], anomalies: [{type, message}]}.
Les anomalies (solde incohérent, ligne illisible, doublon, date hors période) n'empêchent pas la lecture.
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from config.i18n import tr

ZERO = Decimal("0")


class FichierBancaireInvalide(ValueError):
    """Fichier illisible ou vide : rien n'a pu être extrait."""


def _anomalie(liste, type_, message):
    liste.append({"type": type_, "message": message})


def _controles(res):
    """Contrôles communs : équilibre des soldes, doublons, dates hors période."""
    an = res["anomalies"]
    lignes = res["lignes"]
    total_credit = sum((l["credit"] for l in lignes), ZERO)
    total_debit = sum((l["debit"] for l in lignes), ZERO)
    if res["solde_initial"] is not None and res["solde_final"] is not None:
        attendu = res["solde_initial"] + total_credit - total_debit
        if attendu != res["solde_final"]:
            _anomalie(
                an, "solde_incoherent",
                f"Solde final {res['solde_final']} ≠ solde initial + mouvements ({attendu}).",
            )
    vus = set()
    for l in lignes:
        cle = (l["date"], l["debit"], l["credit"], l["reference"], l["libelle"])
        if cle in vus:
            _anomalie(an, "doublon", f"Ligne en double le {l['date']} ({l['debit'] or l['credit']}).")
        vus.add(cle)
        if res["date_debut"] and res["date_fin"] and not (res["date_debut"] <= l["date"] <= res["date_fin"]):
            _anomalie(an, "date_hors_periode", f"Ligne du {l['date']} hors de la période du relevé.")
    return res


# --------------------------------------------------------------------------------------------------
# MT940 (SWIFT)
# --------------------------------------------------------------------------------------------------
_RE_SOLDE = re.compile(r"^([DC])(\d{6})([A-Z]{3})([\d,]+)$")
_RE_61 = re.compile(r"^(\d{6})(\d{4})?(R?[DC])[A-Z]?([\d,]+)N(\w{3})(.*)$")


def _date_yymmdd(s):
    return date(2000 + int(s[:2]), int(s[2:4]), int(s[4:6]))


def _montant_mt940(s):
    try:
        return Decimal(s.replace(",", "."))
    except InvalidOperation:
        raise ValueError(tr("montant illisible : %(s)s") % {"s": repr(s)})


def parse_mt940(texte):
    res = {"format": "mt940", "compte": "", "devise": "", "date_debut": None, "date_fin": None,
           "solde_initial": None, "solde_final": None, "lignes": [], "anomalies": []}
    an = res["anomalies"]
    # Regroupe en champs « :tag:valeur » (les lignes de continuation s'ajoutent au champ courant).
    champs, courant = [], None
    for brut in texte.replace("\r", "").split("\n"):
        m = re.match(r"^:(\d{2}[A-Z]?):(.*)$", brut)
        if m:
            courant = [m.group(1), m.group(2)]
            champs.append(courant)
        elif courant is not None and brut.strip() and not brut.startswith("-"):
            courant[1] += "\n" + brut.strip()
    if not champs:
        raise FichierBancaireInvalide("Aucun champ MT940 reconnu.")
    derniere = None
    for tag, val in champs:
        if tag == "25":
            res["compte"] = val.strip()
        elif tag in ("60F", "60M"):
            m = _RE_SOLDE.match(val.strip())
            if not m:
                _anomalie(an, "ligne_illisible", f"Solde initial illisible : {val!r}")
                continue
            sens, d, devise, mt = m.groups()
            res["devise"] = devise
            res["date_debut"] = _date_yymmdd(d)
            res["solde_initial"] = _montant_mt940(mt) * (1 if sens == "C" else -1)
        elif tag in ("62F", "62M"):
            m = _RE_SOLDE.match(val.strip())
            if not m:
                _anomalie(an, "ligne_illisible", f"Solde final illisible : {val!r}")
                continue
            sens, d, _dev, mt = m.groups()
            res["date_fin"] = _date_yymmdd(d)
            res["solde_final"] = _montant_mt940(mt) * (1 if sens == "C" else -1)
        elif tag == "61":
            premiere = val.split("\n")[0].strip()
            m = _RE_61.match(premiere)
            if not m:
                _anomalie(an, "ligne_illisible", f"Mouvement illisible : {premiere!r}")
                derniere = None
                continue
            d, _md, sens, mt, _code, reste = m.groups()
            try:
                montant = _montant_mt940(mt)
            except ValueError as e:
                _anomalie(an, "ligne_illisible", str(e))
                derniere = None
                continue
            client, _, banque = reste.partition("//")
            ref = client.strip()
            if not ref or ref.upper() == "NONREF":
                ref = banque.strip()  # à défaut de référence client, référence de la banque
            entrant = sens in ("C", "RD")
            derniere = {
                "date": _date_yymmdd(d), "libelle": "", "reference": ref[:120],
                "debit": ZERO if entrant else montant, "credit": montant if entrant else ZERO,
            }
            res["lignes"].append(derniere)
        elif tag == "86" and derniere is not None:
            derniere["libelle"] = " ".join(val.split())[:250]
            derniere = None
    for l in res["lignes"]:
        l["libelle"] = l["libelle"] or "Mouvement bancaire"
    if not res["lignes"] and not an:
        raise FichierBancaireInvalide("Aucun mouvement dans le fichier MT940.")
    return _controles(res)


# --------------------------------------------------------------------------------------------------
# CFONB 120 (enregistrements de 120 caractères : 01 ancien solde, 04 mouvement, 05 complément, 07 nouveau solde)
# Positions (1-indexées) : 1-2 type · 3-7 banque · 12-16 guichet · 17-19 devise · 20 décimales ·
# 22-32 compte · 35-40 date JJMMAA · 49-79 libellé · 82-87 n° d'écriture · 91-104 montant (dernier
# caractère = chiffre signé : { A-I = positif/crédit, } J-R = négatif/débit) · 105-120 référence.
# --------------------------------------------------------------------------------------------------
_POS = {**{c: (i, 1) for i, c in enumerate("{ABCDEFGHI")}, **{c: (i, -1) for i, c in enumerate("}JKLMNOPQR")}}


def _montant_cfonb(champ, decimales):
    champ = champ.strip()
    if not champ:
        raise ValueError("montant absent")
    dernier = champ[-1]
    if dernier in _POS:
        chiffre, signe = _POS[dernier]
        champ = champ[:-1] + str(chiffre)
    elif dernier.isdigit():
        signe = 1
    else:
        raise ValueError(tr("montant illisible : %(champ)s") % {"champ": repr(champ)})
    if not champ.isdigit():
        raise ValueError(tr("montant illisible : %(champ)s") % {"champ": repr(champ)})
    return Decimal(int(champ)).scaleb(-decimales) * signe


def _date_ddmmyy(s):
    return date(2000 + int(s[4:6]), int(s[2:4]), int(s[0:2]))


def parse_cfonb120(texte):
    res = {"format": "cfonb120", "compte": "", "devise": "", "date_debut": None, "date_fin": None,
           "solde_initial": None, "solde_final": None, "lignes": [], "anomalies": []}
    an = res["anomalies"]
    derniere = None
    n = 0
    for brut in texte.replace("\r", "").split("\n"):
        if not brut.strip():
            continue
        n += 1
        ligne = brut.ljust(120)
        code = ligne[0:2]
        if code not in ("01", "04", "05", "07"):
            _anomalie(an, "ligne_illisible", f"Ligne {n} : enregistrement {code!r} non pris en charge.")
            continue
        if len(brut.rstrip()) < 104 and code != "05":
            _anomalie(an, "ligne_illisible", f"Ligne {n} : enregistrement trop court.")
            continue
        try:
            dec = int(ligne[19]) if ligne[19].isdigit() else 2
            if code in ("01", "07", "04"):
                d = _date_ddmmyy(ligne[34:40])
                montant = _montant_cfonb(ligne[90:104], dec)
        except (ValueError, IndexError) as e:
            _anomalie(an, "ligne_illisible", f"Ligne {n} : {e}")
            derniere = None
            continue
        if code != "05":
            res["compte"] = res["compte"] or ligne[21:32].strip()
            res["devise"] = res["devise"] or ligne[16:19].strip()
        if code == "01":
            res["solde_initial"], res["date_debut"] = montant, d
        elif code == "07":
            res["solde_final"], res["date_fin"] = montant, d
        elif code == "04":
            derniere = {
                "date": d, "libelle": ligne[48:79].strip(), "reference": ligne[104:120].strip(),
                "debit": -montant if montant < 0 else ZERO, "credit": montant if montant > 0 else ZERO,
            }
            res["lignes"].append(derniere)
        elif code == "05" and derniere is not None:
            # Complément d'information : ajouté au libellé (zone libre 49-117).
            complement = ligne[48:117].strip()
            if complement:
                derniere["libelle"] = f"{derniere['libelle']} {complement}".strip()[:250]
    for l in res["lignes"]:
        l["libelle"] = l["libelle"] or "Mouvement bancaire"
    if not res["lignes"] and res["solde_initial"] is None:
        raise FichierBancaireInvalide("Aucun enregistrement CFONB 120 reconnu.")
    return _controles(res)


def detecter_format(texte):
    """`mt940` si le fichier contient des champs « :60F: / :61: », sinon `cfonb120` s'il commence par 01/04."""
    if re.search(r"^:(20|25|60[FM]|61):", texte, re.M):
        return "mt940"
    premiere = next((l for l in texte.splitlines() if l.strip()), "")
    if premiere[:2] in ("01", "04"):
        return "cfonb120"
    raise FichierBancaireInvalide("Format de relevé non reconnu (MT940 ou CFONB 120 attendu).")


def parse(texte, format_="auto"):
    if format_ == "auto":
        format_ = detecter_format(texte)
    if format_ == "mt940":
        return parse_mt940(texte)
    if format_ in ("cfonb", "cfonb120"):
        return parse_cfonb120(texte)
    raise FichierBancaireInvalide(tr("Format inconnu : %(format)s") % {"format": format_})
