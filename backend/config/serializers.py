"""Briques de sérialiseurs partagées."""

import copy

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers


class ModelCleanMixin:
    """Rejoue `Model.clean()` dans la validation DRF (DRF ne l'appelle jamais).

    Sans lui, les règles métier écrites dans `clean()` (dates cohérentes, partenaire GLOBAL RENTAL, équipement non
    affecté, quantités positives…) ne protègent que l'admin Django, pas l'API. L'objet est reconstruit avec les valeurs
    reçues (copie de l'instance en modification : l'objet réel n'est pas modifié si la validation échoue). S'exécute
    après la validation propre du sérialiseur (`validate()` inclus) : à placer AVANT `ModelSerializer` dans les bases.
    """

    def run_validation(self, data=serializers.empty):
        value = super().run_validation(data)
        model = self.Meta.model
        concrete = {f.name for f in model._meta.concrete_fields}
        values = {k: v for k, v in value.items() if k in concrete}
        if self.instance is not None:
            obj = copy.copy(self.instance)
            for key, val in values.items():
                setattr(obj, key, val)
        else:
            obj = model(**values)
        try:
            obj.clean()
        except DjangoValidationError as exc:
            if hasattr(exc, "error_dict"):
                raise serializers.ValidationError(exc.message_dict)
            raise serializers.ValidationError({"detail": exc.messages})
        return value
