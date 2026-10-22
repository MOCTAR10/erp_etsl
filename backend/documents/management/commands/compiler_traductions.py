"""Compile les catalogues `backend/locale/<langue>/LC_MESSAGES/django.po` en `django.mo` (EX-G-07).

Compilateur Python pur (format GNU .mo) : `compilemessages` de Django exige `msgfmt` (gettext), absent du poste et du
serveur de dev. Les entrées `#, fuzzy` et les traductions vides sont ignorées (le texte français s'affiche alors).
`--check` : échoue si un `.mo` n'est pas à jour avec son `.po` (contrôle de la suite de tests).
"""

import ast
import struct
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


def lire_po(chemin):
    """Entrées {msgid: msgstr} d'un fichier .po (msgctxt et pluriels non gérés : non utilisés ici)."""
    entrees, courant, champ, fuzzy = {}, {}, None, False

    def clore():
        nonlocal courant, fuzzy
        if "msgid" in courant and not fuzzy:
            msgid, msgstr = courant["msgid"], courant.get("msgstr", "")
            if msgstr or msgid == "":
                entrees[msgid] = msgstr
        courant, fuzzy = {}, False

    for brut in Path(chemin).read_text(encoding="utf-8").splitlines():
        ligne = brut.strip()
        if not ligne:
            clore()
            champ = None
            continue
        if ligne.startswith("#"):
            if ligne.startswith("#,") and "fuzzy" in ligne:
                fuzzy = True
            continue
        for mot in ("msgid", "msgstr"):
            if ligne.startswith(mot + " "):
                if mot == "msgid" and "msgid" in courant:
                    clore()
                champ = mot
                courant[mot] = ast.literal_eval(ligne[len(mot) + 1:])
                break
        else:
            if ligne.startswith('"') and champ:
                courant[champ] += ast.literal_eval(ligne)
            else:
                raise CommandError(f"{chemin} : ligne non reconnue « {brut} »")
    clore()
    return entrees


def produire_mo(entrees):
    """Octets d'un fichier .mo (petit-boutiste, sans table de hachage)."""
    cles = sorted(entrees)
    ids = [k.encode("utf-8") for k in cles]
    strs = [entrees[k].encode("utf-8") for k in cles]
    n = len(cles)
    debut_ids = 7 * 4
    debut_strs = debut_ids + n * 8
    donnees = debut_strs + n * 8
    table_ids, table_strs, blob = [], [], b""
    for b in ids:
        table_ids.append((len(b), donnees + len(blob)))
        blob += b + b"\0"
    for b in strs:
        table_strs.append((len(b), donnees + len(blob)))
        blob += b + b"\0"
    sortie = struct.pack("<7I", 0x950412DE, 0, n, debut_ids, debut_strs, 0, donnees)
    for longueur, position in table_ids + table_strs:
        sortie += struct.pack("<2I", longueur, position)
    return sortie + blob


def catalogues():
    for dossier in getattr(settings, "LOCALE_PATHS", []):
        yield from sorted(Path(dossier).glob("*/LC_MESSAGES/django.po"))


class Command(BaseCommand):
    help = "Compile les catalogues de traduction du serveur (.po -> .mo) sans msgfmt."

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true", help="Échoue si un .mo n'est pas à jour.")

    def handle(self, *args, **options):
        perimes = []
        for po in catalogues():
            mo = po.with_suffix(".mo")
            contenu = produire_mo(lire_po(po))
            if options["check"]:
                if not mo.exists() or mo.read_bytes() != contenu:
                    perimes.append(str(mo))
                continue
            mo.write_bytes(contenu)
            self.stdout.write(f"{po} -> {mo.name}")
        if perimes:
            raise CommandError("Catalogue(s) à recompiler (manage.py compiler_traductions) : " + ", ".join(perimes))
