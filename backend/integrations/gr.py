"""Webhooks sortants (CL-OM-09) : livraison signée HMAC-SHA256 avec reprise bornée.

Sécurité :
- URL validée à la création ET à chaque livraison (HTTPS ; adresses internes interdites hors DEBUG ;
  la résolution DNS est revérifiée au moment de l'envoi contre le « DNS rebinding ») ;
- aucune redirection suivie (`allow_redirects=False`) : une redirection ne peut pas viser le réseau interne ;
- seules les données publiées par l'ERP pour le sujet partent (jamais de montants dans les événements GR).
"""

import hashlib
import hmac
import ipaddress
import json
import socket
from datetime import timedelta
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from outbox.subscribers import subscriber

from .models import WebhookDelivery, WebhookEndpoint

MAX_DELIVERY_ATTEMPTS = 5
TIMEOUT_SECONDS = 5
#: délais avant la tentative suivante (s) : 1 min, 5 min, 30 min, 2 h
BACKOFF = (60, 300, 1800, 7200)


def _resolve(host):
    """Adresses IP d'un nom d'hôte (isolé pour être remplacé dans les tests)."""
    return list({info[4][0] for info in socket.getaddrinfo(host, None)})


def validate_webhook_url(url, debug=None):
    """Lève `ValueError` si l'URL n'est pas une destination de webhook acceptable."""
    debug = settings.DEBUG if debug is None else debug
    parsed = urlparse(url or "")
    if parsed.scheme not in ("https", "http") or not parsed.hostname:
        raise ValueError("URL invalide : schéma https requis.")
    if parsed.scheme == "http" and not debug:
        raise ValueError("HTTPS obligatoire (http n'est toléré qu'en développement).")
    if debug:
        return
    try:
        addresses = _resolve(parsed.hostname)
    except OSError as exc:
        raise ValueError(f"Nom d'hôte introuvable : {exc}")
    if not addresses:
        raise ValueError("Nom d'hôte introuvable.")
    for raw in addresses:
        ip = ipaddress.ip_address(raw.split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ValueError(f"Adresse interne interdite ({ip}).")


def sign(secret, body):
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _body(delivery):
    return json.dumps(
        {
            "id": str(delivery.id),
            "event": delivery.topic,
            "created_at": delivery.created_at.isoformat(),
            "data": delivery.payload,
        },
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    ).encode()


def deliver(delivery):
    """Tente l'envoi d'une livraison ; met à jour l'état (jamais d'exception vers l'appelant)."""
    endpoint = delivery.endpoint
    delivery.attempts += 1
    try:
        validate_webhook_url(endpoint.url)
        body = _body(delivery)
        response = requests.post(
            endpoint.url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "ETSL-ERP-Webhook/1",
                "X-ETSL-Event": delivery.topic,
                "X-ETSL-Delivery": str(delivery.id),
                "X-ETSL-Signature": sign(endpoint.secret, body),
            },
            timeout=TIMEOUT_SECONDS,
            allow_redirects=False,
        )
        delivery.response_code = response.status_code
        if 200 <= response.status_code < 300:
            delivery.status = WebhookDelivery.Status.DELIVERED
            delivery.delivered_at = timezone.now()
            delivery.last_error = ""
            delivery.next_attempt_at = None
            delivery.save()
            return delivery
        delivery.last_error = f"HTTP {response.status_code}"
    except Exception as exc:  # noqa: BLE001 — réseau, DNS, URL refusée : on journalise et on reprogramme
        delivery.last_error = str(exc)[:500]
    if delivery.attempts >= MAX_DELIVERY_ATTEMPTS:
        delivery.status = WebhookDelivery.Status.FAILED
        delivery.next_attempt_at = None
    else:
        delay = BACKOFF[min(delivery.attempts - 1, len(BACKOFF) - 1)]
        delivery.next_attempt_at = timezone.now() + timedelta(seconds=delay)
    delivery.save()
    return delivery


@subscriber("*")
def fanout_webhooks(event):
    """Abonné joker de l'outbox : une livraison par endpoint actif abonné au sujet, envoyée aussitôt."""
    for endpoint in WebhookEndpoint.objects.filter(is_active=True):
        if event.topic not in (endpoint.topics or []):
            continue
        delivery = WebhookDelivery.objects.create(endpoint=endpoint, topic=event.topic, payload=event.payload or {})
        deliver(delivery)


def retry_due_deliveries(limit=50):
    """Relance les livraisons en attente dont l'échéance est atteinte (appelé par Celery beat)."""
    due = (
        WebhookDelivery.objects.filter(status=WebhookDelivery.Status.PENDING)
        .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=timezone.now()))
        .select_related("endpoint")[:limit]
    )
    done = 0
    for delivery in due:
        deliver(delivery)
        done += 1
    return done
