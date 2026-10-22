"""EX-G-07 (lot a8) : messages construits à l'exécution, exports et PDF traduits ; garde-fou de complétude du catalogue.

- Un message dynamique s'écrit `tr("Texte %(nom)s.") % {"nom": valeur}` : le gabarit est le msgid du catalogue
  (`locale/en/LC_MESSAGES/django.po`), traduit avant formatage (le middleware ne sait traduire que du texte exact).
- Garde-fous (pour les lots suivants) : tout `tr("…")` littéral du code a sa traduction anglaise (mêmes `%(nom)s`) ;
  aucun message d'erreur n'est construit en f-string / concaténation ; tout message d'erreur fixe est au catalogue.
  En cas d'échec : compléter `django.po`, puis `python manage.py compiler_traductions`.
"""

import ast
import base64
import re
import zlib
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.utils import translation
from rest_framework.test import APITestCase

from config.i18n import en_francais, tr
from documents.management.commands.compiler_traductions import lire_po
from users.models import User

PWD = "Etls#Demo2026"
RACINE = Path(settings.BASE_DIR)
EXCLUS = {".venv", "migrations", "locale", "perf", "node_modules"}
PLACE = re.compile(r"%\((\w+)\)s")
TEXTE = re.compile(r"[A-Za-zÀ-ÿ]{4,}")
CLES = {"detail", "message", "erreur", "error"}
EXC_IGNOREES = {"CommandError", "TypeError", "KeyError", "AttributeError", "NotImplementedError", "AssertionError",
                "RuntimeError", "ImproperlyConfigured"}


def catalogue():
    return lire_po(Path(settings.LOCALE_PATHS[0]) / "en" / "LC_MESSAGES" / "django.po")


def sources():
    for p in sorted(RACINE.rglob("*.py")):
        rel = p.relative_to(RACINE)
        if set(rel.parts) & EXCLUS or rel.name.startswith("test") or rel.parts[0] in ("manage.py",) \
                or rel.name in ("settings.py", "settings_test.py") or rel.parts[0].startswith(("check_rbac", "smoke_rbac")):
            continue
        yield str(rel).replace("\\", "/"), ast.parse(p.read_text(encoding="utf-8"))


def _nom(call):
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")


def _exception(nom):
    return nom.endswith(("Error", "Erreur", "Exception")) or nom in {"PermissionDenied", "NotFound", "Http404", "ParseError"}


def _textes(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        yield node.value
    elif isinstance(node, ast.JoinedStr):
        for v in node.values:
            if isinstance(v, ast.Constant):
                yield v.value
    elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        yield from _textes(node.left)
        yield from _textes(node.right)


def _messages(arg):
    """Expressions-messages d'un argument d'exception / de réponse (dict, liste, ternaire traversés)."""
    if isinstance(arg, ast.Dict):
        for v in arg.values:
            yield from _messages(v)
    elif isinstance(arg, (ast.List, ast.Tuple)):
        for v in arg.elts:
            yield from _messages(v)
    elif isinstance(arg, ast.IfExp):
        yield from _messages(arg.body)
        yield from _messages(arg.orelse)
    elif isinstance(arg, (ast.Constant, ast.JoinedStr, ast.BinOp)):
        yield arg


def messages_du_code():
    """(fichier, ligne, nœud) des messages d'erreur : arguments d'exceptions levées et `detail`/`message` des réponses."""
    for fichier, arbre in sources():
        for n in ast.walk(arbre):
            args = []
            if isinstance(n, ast.Call):
                nom = _nom(n)
                if _exception(nom) and nom not in EXC_IGNOREES:
                    args = list(n.args) + [k.value for k in n.keywords if k.arg in ("detail", "message")]
            if isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call) and _nom(n.exc) not in EXC_IGNOREES:
                args = list(n.exc.args)
            if isinstance(n, ast.Dict):
                args = [v for k, v in zip(n.keys, n.values) if isinstance(k, ast.Constant) and k.value in CLES]
            for a in args:
                for m in _messages(a):
                    if any(TEXTE.search(t) for t in _textes(m)):
                        yield fichier, m.lineno, m


def appels_tr():
    """msgids littéraux passés à `tr(...)` / `_tr(...)` dans le code."""
    for fichier, arbre in sources():
        for n in ast.walk(arbre):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("tr", "_tr") and n.args \
                    and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str) and n.args[0].value:
                yield fichier, n.lineno, n.args[0].value


class CompletudeCatalogueTests(SimpleTestCase):
    """Garde-fous : le catalogue anglais suit le code (lots suivants compris)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cat = {k: v for k, v in catalogue().items() if k}

    def test_chaque_tr_litteral_a_sa_traduction(self):
        appels = list(appels_tr())
        self.assertGreater(len(appels), 600)
        manquants = sorted({f"{f}:{l} {m!r}" for f, l, m in appels if m not in self.cat})
        self.assertEqual(manquants, [], "msgid sans traduction anglaise : compléter locale/en/LC_MESSAGES/django.po")

    def test_gabarits_memes_variables(self):
        ecarts = [k for k, v in self.cat.items() if set(PLACE.findall(k)) != set(PLACE.findall(v))]
        self.assertEqual(ecarts, [])
        for k, v in self.cat.items():
            if PLACE.search(k):
                valeurs = dict.fromkeys(PLACE.findall(k), "x")
                k % valeurs, v % valeurs  # aucun « % » isolé : le formatage ne lève pas

    def test_aucun_message_d_erreur_construit_hors_gabarit(self):
        dynamiques = sorted(f"{f}:{l}" for f, l, m in messages_du_code() if not isinstance(m, ast.Constant))
        self.assertEqual(dynamiques, [], "message d'erreur en f-string / concaténation : écrire tr(\"… %(x)s …\") % {...}")

    def test_messages_d_erreur_fixes_au_catalogue(self):
        fixes = [(f, l, m.value) for f, l, m in messages_du_code() if isinstance(m, ast.Constant)]
        self.assertGreater(len(fixes), 900)
        manquants = sorted({f"{f}:{l} {v!r}" for f, l, v in fixes if v not in self.cat})
        self.assertEqual(manquants, [])


class GabaritsAnglaisTests(SimpleTestCase):
    def test_gabarit_formate_dans_les_deux_langues(self):
        gabarit = "Lot %(lot_code)s (%(lot_numero_lot)s) en quarantaine : sortie interdite (CDC M5 §7.8)."
        valeurs = {"lot_code": "LOT-1", "lot_numero_lot": "N42"}
        with translation.override("fr"):
            self.assertEqual(tr(gabarit) % valeurs, "Lot LOT-1 (N42) en quarantaine : sortie interdite (CDC M5 §7.8).")
        with translation.override("en"):
            self.assertEqual(tr(gabarit) % valeurs, "Batch LOT-1 (N42) in quarantine: issue forbidden (CDC M5 §7.8).")

    def test_pourcentage_echappe(self):
        with translation.override("en"):
            self.assertEqual(tr("Total des parts %(total)s %% > 100 %%.") % {"total": 120}, "Total of shares 120 % > 100 %.")

    def test_en_francais_force_la_langue(self):
        with translation.override("en"):
            self.assertEqual(en_francais(tr, "Cumul"), "Cumul")
            self.assertEqual(tr("Cumul"), "Cumulative")


def texte_pdf(octets):
    """Texte brut d'un PDF ReportLab (flux FlateDecode, éventuellement ASCII85)."""
    morceaux = []
    for flux in re.findall(rb"stream\r?\n(.*?)\r?\n?endstream", octets, re.S):
        for decode in (lambda b: zlib.decompress(b), lambda b: zlib.decompress(base64.a85decode(b.strip().removesuffix(b"~>")))):
            try:
                morceaux.append(decode(flux).decode("latin-1"))
                break
            except Exception:  # noqa: BLE001 - flux non compressé ou autre filtre
                continue
        else:
            morceaux.append(flux.decode("latin-1"))
    return "\n".join(morceaux)


class PdfAnglaisTests(TestCase):
    def test_export_direction_pdf_en_anglais(self):
        from analytics.exports import reponse_export

        sections = [("pilotage", ["Indicateur", "Valeur"], [["Exercice", 2026], ["Reste à couvrir", 10]])]
        with translation.override("en"):
            en = texte_pdf(reponse_export("pdf", "Pilotage Direction — trésorerie et budget", "x", sections).content)
        with translation.override("fr"):
            fr = texte_pdf(reponse_export("pdf", "Pilotage Direction — trésorerie et budget", "x", sections).content)
        self.assertIn("Indicator", en)
        self.assertIn("Fiscal year", en)
        self.assertIn("Indicateur", fr)
        self.assertNotIn("Indicator", fr)

    def test_etat_comptable_pdf_et_json_en_anglais(self):
        from comptabilite.etats import plan_comptable, to_pdf

        with translation.override("en"):
            etat = plan_comptable()
            self.assertEqual(etat["titre"], "SYSCOHADA chart of accounts (multi-level)")
            self.assertIn("Printed on", texte_pdf(to_pdf(etat)))
        with translation.override("fr"):
            self.assertEqual(plan_comptable()["titre"], "Plan comptable SYSCOHADA (multi-niveaux)")

    def test_documents_legaux_en_francais_par_defaut(self):
        from comptabilite.models import ParametreCompta
        from comptabilite.services import langue_documents_legaux

        with translation.override("en"):
            self.assertEqual(langue_documents_legaux(), "fr")
            ParametreCompta.objects.filter(code="DOCS_LEGAUX_LANGUE_UTILISATEUR").update(valeur=Decimal("1"))
            self.assertEqual(langue_documents_legaux(), "en")


class MessagesDynamiquesApiTests(APITestCase):
    """Requêtes réelles : message construit à l'exécution, en `fr` puis en `en`."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(email="admin.a8@etls.ga", password=PWD, role=User.Role.ADMIN, is_staff=True)

    def _deux(self, methode, url, **kw):
        self.client.force_authenticate(self.admin)
        appel = getattr(self.client, methode)
        return appel(url, HTTP_ACCEPT_LANGUAGE="fr", **kw), appel(url, HTTP_ACCEPT_LANGUAGE="en", **kw)

    def test_filtre_multicritere_invalide(self):
        fr, en = self._deux("get", "/api/documents/documents/?document_date__gte=31-12-2026")
        self.assertEqual(fr.status_code, 400)
        self.assertIn("Date invalide (format attendu AAAA-MM-JJ). (31-12-2026)", str(fr.data))
        self.assertIn("Invalid date (expected format YYYY-MM-DD). (31-12-2026)", str(en.data))

    def test_service_comptable_sans_periode(self):
        from accounting_kernel.services import period_for_date

        with translation.override("en"):
            with self.assertRaisesMessage(Exception, "No accounting period for the date 1990-01-01."):
                period_for_date(date(1990, 1, 1))
        with translation.override("fr"):
            with self.assertRaisesMessage(Exception, "Aucune période comptable pour la date 1990-01-01."):
                period_for_date(date(1990, 1, 1))
