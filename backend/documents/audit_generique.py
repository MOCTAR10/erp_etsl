"""Piste d'audit générique avant / après (écarts transverses EX-G-06, §8.2 « Audit »).

Toute création, modification ou suppression d'un objet métier faite par un utilisateur (requête HTTP) est tracée
dans `AuditLog` : modèle, identifiant, auteur, adresse IP, et pour une modification les seules valeurs changées
**avant / après**. Aucune application métier n'est instrumentée : signaux `pre_save` / `post_save` / `post_delete`
globaux, filtrés sur les applications tracées. Les secrets (mot de passe, secret TOTP, champs chiffrés, OTP) sont
masqués. Les traitements hors requête (seeds, tâches planifiées, migrations) ne sont pas tracés ici : ils ont leurs
propres journaux (outbox, historique des barèmes…). L'écriture d'audit ne fait jamais échouer l'action métier
(point de sauvegarde dédié).
"""

import contextvars

from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save

_requete = contextvars.ContextVar("etls_requete_courante", default=None)

#: Applications dont chaque objet est tracé.
APPS_TRACEES = frozenset({
    "commercial", "achats", "operations", "logistique", "stocks", "qualite", "hse", "maintenance", "rh_paie",
    "comptabilite", "accounting_kernel", "controle_gestion", "juridique", "integrations", "referentiels",
    "registres", "analytics",
})
#: Modèles du socle tracés en plus (droits, circuits, paramètres) ; le reste de la GED a sa propre piste.
MODELES_SOCLE = frozenset({
    "users.user", "users.parametretransverse", "workflow.circuit", "workflow.circuitstep", "workflow.delegation",
    "documents.documenttype", "documents.dossier",
})
#: Champs jamais recopiés en clair dans la piste.
CHAMPS_MASQUES = frozenset({"password", "mfa_secret", "otp_hash", "seal"})
#: Champs techniques ignorés (bruit).
CHAMPS_IGNORES = frozenset({"search_vector", "extracted_text", "updated_at", "last_login", "mfa_dernier_pas"})
MAX_TEXTE = 300


class RequeteCouranteMiddleware:
    """Mémorise la requête courante : l'auteur (authentifié par DRF / JWT) est lu au moment de l'écriture."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        jeton = _requete.set(request)
        try:
            return self.get_response(request)
        finally:
            _requete.reset(jeton)


def requete_courante():
    return _requete.get()


def est_trace(sender):
    meta = getattr(sender, "_meta", None)
    if meta is None or meta.proxy and meta.concrete_model is not sender:
        return False
    return meta.app_label in APPS_TRACEES or meta.label_lower in MODELES_SOCLE


def _masque(field):
    from config.fields import EncryptedCharField

    return field.name in CHAMPS_MASQUES or isinstance(field, EncryptedCharField)


def _champs(model):
    return [f for f in model._meta.concrete_fields if f.name not in CHAMPS_IGNORES]


def _court(value):
    from .audit import _json_safe

    value = _json_safe(value)
    if isinstance(value, str) and len(value) > MAX_TEXTE:
        return value[:MAX_TEXTE] + "…"
    if hasattr(value, "name") and not isinstance(value, (str, int, float, bool, list, dict)):
        return str(value.name or "")
    return value if isinstance(value, (str, int, float, bool, list, dict, type(None))) else str(value)


def _etat(instance, champs):
    out = {}
    for f in champs:
        out[f.attname] = "***" if _masque(f) else _court(getattr(instance, f.attname, None))
    return out


def _ecrire(request, instance, action, detail):
    from .audit import request_ip
    from .models import AuditLog

    user = getattr(request, "user", None)
    try:
        with transaction.atomic():
            AuditLog.objects.create(
                user=user if user is not None and user.is_authenticated else None,
                action=action,
                object_type=instance._meta.label_lower[:50],
                object_id=str(instance.pk)[:36],
                detail=detail,
                ip_address=request_ip(request) or None,
            )
    except Exception:  # noqa: BLE001 — l'audit ne bloque jamais l'action métier
        pass


def _avant(sender, instance, raw=False, update_fields=None, **kwargs):
    instance._audit_avant = None
    if raw or requete_courante() is None or not est_trace(sender) or instance._state.adding or instance.pk is None:
        return
    champs = _champs(sender)
    if update_fields:
        champs = [f for f in champs if f.name in update_fields or f.attname in update_fields]
    try:
        ancien = sender._base_manager.filter(pk=instance.pk).first()
    except Exception:  # noqa: BLE001
        ancien = None
    instance._audit_avant = _etat(ancien, champs) if ancien is not None else None
    instance._audit_champs = champs


def _apres(sender, instance, created, raw=False, **kwargs):
    request = requete_courante()
    if raw or request is None or not est_trace(sender):
        return
    from .models import AuditLog

    if created:
        apres = {k: v for k, v in _etat(instance, _champs(sender)).items() if v not in (None, "", [], {})}
        _ecrire(request, instance, AuditLog.Action.CREATE, {"modele": sender._meta.label, "apres": apres})
        return
    avant = getattr(instance, "_audit_avant", None)
    if avant is None:
        return
    apres = _etat(instance, getattr(instance, "_audit_champs", _champs(sender)))
    change = sorted(k for k in apres if apres[k] != avant.get(k))
    if not change:
        return
    _ecrire(request, instance, AuditLog.Action.UPDATE, {
        "modele": sender._meta.label, "champs": change,
        "avant": {k: avant.get(k) for k in change}, "apres": {k: apres[k] for k in change},
    })


def _suppression(sender, instance, **kwargs):
    request = requete_courante()
    if request is None or not est_trace(sender):
        return
    from .models import AuditLog

    avant = {k: v for k, v in _etat(instance, _champs(sender)).items() if v not in (None, "", [], {})}
    _ecrire(request, instance, AuditLog.Action.DELETE, {"modele": sender._meta.label, "avant": avant})


def connecter():
    pre_save.connect(_avant, dispatch_uid="etls_audit_generique_avant")
    post_save.connect(_apres, dispatch_uid="etls_audit_generique_apres")
    post_delete.connect(_suppression, dispatch_uid="etls_audit_generique_suppression")
