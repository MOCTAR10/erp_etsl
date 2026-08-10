"""Traçabilité (RF-63 à 65) — écriture dans la piste d'audit."""

import uuid as uuid_module
from datetime import date, datetime
from decimal import Decimal

from .models import AuditLog


def _json_safe(value):
    """Rend un détail d'audit sérialisable en JSON (UUID, dates, Decimal…)."""
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, uuid_module.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def log_audit(user, action, object_type, object_id, detail=None, ip_address=None):
    """Enregistre une action dans la piste d'audit (jamais bloquante)."""
    try:
        AuditLog.objects.create(
            user=user if user and user.is_authenticated else None,
            action=action,
            object_type=object_type,
            object_id=str(object_id),
            detail=_json_safe(detail or {}),
            ip_address=ip_address,
        )
    except Exception:
        # L'audit ne doit jamais faire échouer l'action métier.
        pass


def request_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
