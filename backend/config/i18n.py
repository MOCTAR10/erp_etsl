"""Bilinguisme côté serveur (EX-G-07) : messages d'erreur, exports et PDF en français ou en anglais.

- La langue est celle de la requête : `Accept-Language` envoyé par le SPA (fr | en), activée par `LocaleMiddleware`.
- Les messages métier sont écrits en français dans le code ; leur traduction anglaise est un CATALOGUE
  (`backend/locale/en/LC_MESSAGES/django.po`, msgid = texte français). Ajouter une traduction = ajouter une entrée au
  catalogue puis `python manage.py compiler_traductions` (compilateur Python pur : pas besoin de `msgfmt`).
- `TraductionReponsesMiddleware` traduit, en anglais seulement, les chaînes des réponses d'erreur DRF (`detail`,
  erreurs de champ) et les `detail` / `message` des réponses réussies : aucune modification des vues n'est
  nécessaire, un message absent du catalogue reste en français (repli, jamais d'erreur).
- `tr()` sert aux exports (en-têtes, titres, pied de page PDF) et à tout texte serveur.
"""

from django.utils import translation
from django.utils.translation import gettext


def langue_anglaise():
    return (translation.get_language() or "").lower().startswith("en")


def tr(texte):
    """Traduction du texte français `texte` dans la langue active (inchangé en français ou s'il est inconnu)."""
    if not texte or not isinstance(texte, str) or not langue_anglaise():
        return texte
    return gettext(str(texte))


def traduire(donnees):
    """Traduit récursivement les chaînes d'une structure JSON (dict / list / str) ; les clés restent inchangées."""
    if isinstance(donnees, str):
        traduit = tr(donnees)
        return traduit if traduit != str(donnees) else donnees
    if isinstance(donnees, dict):
        return {k: traduire(v) for k, v in donnees.items()}
    if isinstance(donnees, list):
        return [traduire(v) for v in donnees]
    return donnees


CLES_MESSAGES = ("detail", "message", "erreur", "error")


class TraductionReponsesMiddleware:
    """Traduit en anglais les messages des réponses DRF quand la requête est en anglais (EX-G-07)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        data = getattr(response, "data", None)
        if data is None or not langue_anglaise() or not hasattr(response, "render"):
            return response
        if response.status_code >= 400:
            nouvelles = traduire(data)
        elif isinstance(data, dict) and any(k in data for k in CLES_MESSAGES):
            nouvelles = {k: (traduire(v) if k in CLES_MESSAGES else v) for k, v in data.items()}
        else:
            return response
        if nouvelles != data:
            response.data = nouvelles
            response._is_rendered = False
            response.render()
        return response

