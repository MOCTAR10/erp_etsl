"""Surcouche du gestionnaire d'exceptions DRF : transforme les erreurs de base
de données Django en HTTP propres au lieu de 500.

- django.db.IntegrityError  → 409 Conflict (contrainte violée, ex. code dupliqué)
- django.db.models.deletion.ProtectedError → 409 Conflict (suppression FK protégée)
Tout le reste retombe sur le comportement DRF par défaut.
"""

from django.db import IntegrityError
from django.db.models.deletion import ProtectedError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as _drf_exception_handler


def _db_conflict_response(detail):
    return Response({"detail": detail}, status=status.HTTP_409_CONFLICT)


def drf_exception_handler(exc, context):
    if isinstance(exc, ProtectedError):
        return _db_conflict_response(
            "Suppression impossible : des éléments sont encore rattachés à cet objet."
        )
    if isinstance(exc, IntegrityError):
        return _db_conflict_response(
            "Conflit de données : doublon détecté sur une valeur unique."
        )
    return _drf_exception_handler(exc, context)