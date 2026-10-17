"""Validation des saisies lues directement dans `request.data` par les actions DRF (`@action`).

Les actions de workflow n'ont pas de sérialiseur : sans ces aides, une date, un choix ou un identifiant mal formé
était affecté tel quel au modèle et faisait planter l'enregistrement (500) ou stockait une valeur hors choix.
Chaque aide lève une `ValidationError` DRF → réponse 400 avec le nom du champ.
"""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.exceptions import ValidationError


def date_input(raw, field, default=None):
    """Date ISO (AAAA-MM-JJ) ; `default` si vide."""
    if raw in (None, ""):
        return default
    try:
        return serializers.DateField().run_validation(raw)
    except serializers.ValidationError as exc:
        raise ValidationError({field: exc.detail})


def choice_input(raw, choices, field, default=None):
    """Valeur d'un `TextChoices` ; `default` si vide."""
    if raw in (None, ""):
        return default
    if raw not in choices.values:
        raise ValidationError({field: f"Valeur inconnue : {raw!r}."})
    return raw


def fk_input(raw, queryset, field):
    """Objet désigné par sa clé primaire dans `queryset` (None si vide)."""
    if raw in (None, ""):
        return None
    try:
        return queryset.get(pk=raw)
    except (queryset.model.DoesNotExist, DjangoValidationError, ValueError, TypeError):
        raise ValidationError({field: "Référence inconnue."})


def positive_decimal(raw, field):
    """Décimal fini >= 0."""
    try:
        value = Decimal(str(raw).replace(",", "."))
    except (InvalidOperation, ValueError):
        raise ValidationError({field: "Nombre attendu."})
    if not value.is_finite() or value < 0:
        raise ValidationError({field: "Valeur positive attendue."})
    return value
