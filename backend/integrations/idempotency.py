"""Décorateur d'idempotence pour les vues DRF rejouables (saisies terrain, CL-OM-08).

Usage : `@idempotent` sur `create()` ou sur une `@action` POST. Sans en-tête `Idempotency-Key`, la vue
se comporte normalement. Avec la clé : première requête = exécution + mémorisation de la réponse
(succès uniquement) ; rejeu = réponse mémorisée + en-tête `Idempotent-Replay: true`.
"""

import functools
import json

from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from .models import IdempotencyRecord

MAX_KEY_LENGTH = 80


def _replay(record):
    response = Response(record.body, status=record.status_code)
    response["Idempotent-Replay"] = "true"
    return response


def idempotent(view_method):
    @functools.wraps(view_method)
    def wrapper(self, request, *args, **kwargs):
        key = request.headers.get("Idempotency-Key")
        if not key or not request.user.is_authenticated:
            return view_method(self, request, *args, **kwargs)
        if len(key) > MAX_KEY_LENGTH:
            raise ValidationError({"Idempotency-Key": f"{MAX_KEY_LENGTH} caractères maximum."})

        record = IdempotencyRecord.objects.filter(user=request.user, key=key).first()
        if record:
            return _replay(record)

        try:
            with transaction.atomic():
                response = view_method(self, request, *args, **kwargs)
                if response.status_code < 400:
                    IdempotencyRecord.objects.create(
                        user=request.user,
                        key=key,
                        method=request.method,
                        path=request.path[:255],
                        status_code=response.status_code,
                        body=json.loads(JSONRenderer().render(response.data) or "null"),
                    )
        except IntegrityError:  # deux rejeux simultanés : le second renvoie la réponse du premier
            record = IdempotencyRecord.objects.filter(user=request.user, key=key).first()
            if record:
                return _replay(record)
            raise
        return response

    return wrapper
