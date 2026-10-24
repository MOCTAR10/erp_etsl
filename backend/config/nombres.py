"""Nombres lisibles en français dans les messages composés côté serveur (notifications, motifs, descriptions).

Jamais « 900.00 » ni « -100.00 % » : « 900 », « 1 250 », « 48,5 », « +11,34 % ». Séparateur de milliers = espace
fine insécable (U+202F), comme `Intl.NumberFormat("fr-FR")` côté SPA.
"""

from decimal import Decimal


def nombre_fr(valeur, signe=False):
    """« 900 », « 1 250 », « 48,5 » ; `signe=True` : « +11,34 », « −100 » (signe moins typographique)."""
    if valeur is None:
        return ""
    d = Decimal(valeur)
    prefixe = "−" if d < 0 else ("+" if signe and d > 0 else "")
    entier, _, decimales = f"{abs(d).quantize(Decimal('0.01')):f}".partition(".")
    texte = f"{int(entier):,}".replace(",", " ")
    decimales = decimales.rstrip("0")
    return prefixe + texte + ("," + decimales if decimales else "")


def pourcentage_fr(valeur, signe=False):
    """« +11,34 % » (espace insécable avant le signe %)."""
    return f"{nombre_fr(valeur, signe=signe)} %"
