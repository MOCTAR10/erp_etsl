"""Service de signature électronique avancée : code à usage unique, preuve scellée (HMAC chaîné), vérification."""

import hashlib
import hmac
import json
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from users import mfa

from .models import SignatureRequest, Signer, Version
from config.i18n import tr

OTP_TTL_MINUTES = 10
OTP_RESEND_SECONDS = 20
MAX_ATTEMPTS = 5
DEFAULT_VALIDITY_DAYS = 14

# Second facteur (lot correctif) : code e-mail quand la messagerie réelle est active (EMAIL_ENABLED), sinon code TOTP
# de l'application d'authentification déjà utilisée par la MFA (users/mfa.py). Méthode par défaut = e-mail si la
# messagerie est active, sinon TOTP ; un signataire avec la MFA peut toujours choisir le TOTP.
METHODE_EMAIL = "email"
METHODE_TOTP = "totp"
MESSAGE_SANS_FACTEUR = (
    "La messagerie n'est pas encore configurée : activez la double authentification (application "
    "d'authentification) pour signer."
)
MESSAGE_TOTP_SEUL = (
    "La messagerie n'est pas encore configurée : signez avec le code de votre application d'authentification."
)


def email_actif() -> bool:
    return bool(getattr(settings, "EMAIL_ENABLED", False))


def totp_disponible(user) -> bool:
    return bool(getattr(user, "mfa_active", False) and getattr(user, "mfa_secret", ""))


def methodes_disponibles(user) -> list:
    out = []
    if email_actif():
        out.append(METHODE_EMAIL)
    if totp_disponible(user):
        out.append(METHODE_TOTP)
    return out


def mode_signature(user) -> dict:
    """Méthodes de second facteur offertes au signataire (lu par l'écran Signatures)."""
    methodes = methodes_disponibles(user)
    return {
        "email_actif": email_actif(),
        "mfa_active": totp_disponible(user),
        "methodes": methodes,
        "methode_defaut": methodes[0] if methodes else None,
        "enrolement_requis": not methodes,
        "message": "" if methodes else MESSAGE_SANS_FACTEUR,
    }


def _hmac(data: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), data.encode(), hashlib.sha256).hexdigest()


def file_sha256(version: Version) -> str:
    """Empreinte réelle du fichier stocké (chaîne vide si illisible)."""
    h = hashlib.sha256()
    try:
        with version.file.storage.open(version.file.name, "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
    except Exception:  # noqa: BLE001 — fichier absent/illisible = intégrité non démontrée
        return ""
    return h.hexdigest()


def _evidence(signer: Signer) -> str:
    data = {
        "request": str(signer.request_id),
        "version": str(signer.request.version_id),
        "sha256": signer.document_sha256,
        "signer": str(signer.user_id),
        "email": signer.user.email,
        "order": signer.order,
        "signed_at": signer.signed_at.isoformat() if signer.signed_at else None,
        "ip": signer.ip_address,
    }
    if signer.methode:  # méthode scellée dans la preuve (absente des signatures antérieures : sceaux inchangés)
        data["method"] = signer.methode
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def compute_seal(signer: Signer, previous_seal: str) -> str:
    return _hmac(_evidence(signer) + "|" + previous_seal)


def _otp_digest(signer: Signer, code: str) -> str:
    return _hmac(f"otp:{signer.pk}:{code}")


@transaction.atomic
def create_request(version, signers, created_by, title="", message="", validity_days=DEFAULT_VALIDITY_DAYS):
    if not signers:
        raise ValidationError("Au moins un signataire est requis.")
    if len({s.pk for s in signers}) != len(signers):
        raise ValidationError("Un signataire ne peut figurer qu'une fois.")
    if any(not s.is_active for s in signers):
        raise ValidationError("Signataire inactif.")
    req = SignatureRequest.objects.create(
        version=version, title=title, message=message, created_by=created_by,
        document_sha256=version.sha256, expires_at=timezone.now() + timedelta(days=validity_days),
    )
    for order, user in enumerate(signers, start=1):
        Signer.objects.create(request=req, user=user, order=order)
    return req


def current_signer(req: SignatureRequest):
    return req.signers.filter(status=Signer.Status.PENDING).order_by("order").first()


def _check_open(req: SignatureRequest):
    if req.status != SignatureRequest.Status.PENDING:
        raise ValidationError("Cette demande n'est plus en cours.")
    if req.is_expired:
        raise ValidationError("Demande expirée : relancez une nouvelle demande de signature.")


def _my_turn(req: SignatureRequest, user) -> Signer:
    signer = req.signers.filter(user=user).first()
    if signer is None:
        raise ValidationError("Vous n'êtes pas signataire de cette demande.")
    if signer.status != Signer.Status.PENDING:
        raise ValidationError("Vous avez déjà répondu à cette demande.")
    cur = current_signer(req)
    if cur is None or cur.pk != signer.pk:
        raise ValidationError("Ce n'est pas encore votre tour : les signataires précédents doivent signer d'abord.")
    return signer


@transaction.atomic
def send_otp(req: SignatureRequest, user):
    req = SignatureRequest.objects.select_for_update().get(pk=req.pk)
    _check_open(req)
    signer = _my_turn(req, user)
    if not email_actif():
        raise ValidationError(MESSAGE_TOTP_SEUL if totp_disponible(user) else MESSAGE_SANS_FACTEUR)
    if signer.otp_attempts >= MAX_ATTEMPTS:
        raise ValidationError("Signature verrouillée après trop d'essais : contactez l'émetteur de la demande.")
    now = timezone.now()
    if signer.otp_sent_at and (now - signer.otp_sent_at).total_seconds() < OTP_RESEND_SECONDS:
        raise ValidationError(tr("Patientez %(otp_resend_seconds)s secondes avant de redemander un code.") % {"otp_resend_seconds": OTP_RESEND_SECONDS})
    code = f"{secrets.randbelow(10**6):06d}"
    signer.otp_hash = _otp_digest(signer, code)
    signer.otp_sent_at = now
    signer.otp_expires_at = now + timedelta(minutes=OTP_TTL_MINUTES)
    signer.save(update_fields=["otp_hash", "otp_sent_at", "otp_expires_at"])
    send_mail(
        subject="Code de signature ETSL",
        message=(
            f"Votre code de signature pour « {req.title or req.version.document.title} » : {code}\n"
            f"Valable {OTP_TTL_MINUTES} minutes. Ne le communiquez à personne."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )
    return signer


class _AuthFailure(Exception):
    """Échec d'authentification (code ou mot de passe) : le compteur d'essais doit survivre au rollback."""

    def __init__(self, signer_pk):
        super().__init__("auth failure")
        self.signer_pk = signer_pk


def sign(req: SignatureRequest, user, otp: str, password: str, ip=None, user_agent="", methode=""):
    """Signe pour `user` ; un échec d'authentification incrémente le compteur d'essais (hors transaction annulée).

    `methode` : « email » (code reçu par e-mail) ou « totp » (code courant de l'application d'authentification) ;
    vide = code e-mail s'il en a été demandé un, sinon TOTP si la MFA est active.
    """
    try:
        with transaction.atomic():
            return _sign(req, user, otp, password, ip, user_agent, methode)
    except _AuthFailure as failure:
        Signer.objects.filter(pk=failure.signer_pk).update(otp_attempts=F("otp_attempts") + 1)
        attempts = Signer.objects.get(pk=failure.signer_pk).otp_attempts
        raise ValidationError(tr("Code ou mot de passe invalide (%(attempts)s/%(max_attempts)s essais).") % {"attempts": attempts, "max_attempts": MAX_ATTEMPTS})


def _resoudre_methode(signer: Signer, user, methode: str) -> str:
    methode = (methode or "").strip().lower()
    if methode and methode not in (METHODE_EMAIL, METHODE_TOTP):
        raise ValidationError("Méthode de signature inconnue (email ou totp).")
    if not methode:
        methode = METHODE_EMAIL if signer.otp_hash or not totp_disponible(user) else METHODE_TOTP
    if methode == METHODE_TOTP and not totp_disponible(user):
        raise ValidationError(MESSAGE_SANS_FACTEUR if not email_actif() else
                              "Double authentification non activée : signez avec le code reçu par e-mail.")
    if methode == METHODE_EMAIL and not signer.otp_hash and not email_actif():
        raise ValidationError(MESSAGE_TOTP_SEUL if totp_disponible(user) else MESSAGE_SANS_FACTEUR)
    return methode


def _sign(req: SignatureRequest, user, otp: str, password: str, ip=None, user_agent="", methode=""):
    req = SignatureRequest.objects.select_for_update().get(pk=req.pk)
    _check_open(req)
    signer = _my_turn(req, user)
    signer = Signer.objects.select_for_update().get(pk=signer.pk)
    if signer.otp_attempts >= MAX_ATTEMPTS:
        raise ValidationError("Signature verrouillée après trop d'essais : contactez l'émetteur de la demande.")
    methode = _resoudre_methode(signer, user, methode)
    pas_totp = None
    if methode == METHODE_TOTP:
        # Verrou sur le compte : un même code TOTP ne sert qu'une fois (connexion ou signature), comme à la MFA.
        compte = type(user).objects.select_for_update().get(pk=user.pk)
        pas_totp = mfa.verifier(compte.mfa_secret, otp, compte.mfa_dernier_pas)
        ok = pas_totp is not None and compte.check_password(password or "")
    else:
        if not signer.otp_hash or not signer.otp_expires_at or timezone.now() > signer.otp_expires_at:
            raise ValidationError("Aucun code valide : demandez un nouveau code.")
        ok = hmac.compare_digest(signer.otp_hash, _otp_digest(signer, str(otp))) and user.check_password(
            password or ""
        )
    if not ok:
        raise _AuthFailure(signer.pk)
    if pas_totp is not None:
        type(user).objects.filter(pk=user.pk).update(mfa_dernier_pas=pas_totp)

    # intégrité : la version n'a pas changé depuis la demande (empreinte en base ET fichier réel)
    version = req.version
    if version.sha256 != req.document_sha256 or file_sha256(version) != req.document_sha256:
        raise ValidationError("Intégrité du document non garantie : il a été modifié depuis la demande.")

    previous = (
        req.signers.filter(status=Signer.Status.SIGNED).order_by("-order").values_list("seal", flat=True).first() or ""
    )
    signer.status = Signer.Status.SIGNED
    signer.signed_at = timezone.now()
    signer.ip_address = ip
    signer.user_agent = (user_agent or "")[:255]
    signer.document_sha256 = req.document_sha256
    signer.otp_hash = ""
    signer.methode = methode
    signer.seal = compute_seal(signer, previous)
    signer.save()
    if not req.signers.filter(status=Signer.Status.PENDING).exists():
        req.status = SignatureRequest.Status.COMPLETED
        req.completed_at = timezone.now()
        req.save(update_fields=["status", "completed_at"])
    return signer


@transaction.atomic
def refuse(req: SignatureRequest, user, reason: str):
    req = SignatureRequest.objects.select_for_update().get(pk=req.pk)
    _check_open(req)
    signer = _my_turn(req, user)
    if not (reason or "").strip():
        raise ValidationError("Le motif de refus est obligatoire.")
    signer.status = Signer.Status.REFUSED
    signer.refusal_reason = reason.strip()[:300]
    signer.save(update_fields=["status", "refusal_reason"])
    req.status = SignatureRequest.Status.REFUSED
    req.save(update_fields=["status"])
    return signer


def unlock(req: SignatureRequest):
    req.signers.filter(status=Signer.Status.PENDING).update(otp_attempts=0, otp_hash="", otp_sent_at=None)


def certificate(req: SignatureRequest) -> dict:
    """Certificat de signature : chaîne des preuves rejouée + intégrité du fichier."""
    previous = ""
    chain_ok = True
    rows = []
    for s in req.signers.filter(status=Signer.Status.SIGNED).select_related("user").order_by("order"):
        expected = compute_seal(s, previous)
        valid = hmac.compare_digest(expected, s.seal)
        chain_ok = chain_ok and valid and s.document_sha256 == req.document_sha256
        rows.append(
            {
                "order": s.order, "signer": s.user.get_full_name() or s.user.email, "email": s.user.email,
                "signed_at": s.signed_at, "ip": s.ip_address, "seal": s.seal, "seal_valid": valid,
                "methode": s.methode or METHODE_EMAIL,
            }
        )
        previous = s.seal
    return {
        "request": str(req.pk),
        "title": req.title,
        "status": req.status,
        "document": req.version.document.title,
        "version": req.version.number,
        "document_sha256": req.document_sha256,
        "document_intact": file_sha256(req.version) == req.document_sha256,
        "signatures": rows,
        "valid": chain_ok and bool(rows),
        "method": "Signature électronique avancée interne : authentification (mot de passe + code à usage unique "
        "reçu par e-mail ou code TOTP de l'application d'authentification), empreinte SHA-256 du document, "
        "sceau HMAC-SHA256 chaîné.",
    }


def version_signee(version) -> bool:
    """Vrai si une signature avancée est achevée sur l'empreinte exacte de cette version (CL-OM-06)."""
    return bool(version) and SignatureRequest.objects.filter(
        version=version, status=SignatureRequest.Status.COMPLETED, document_sha256=version.sha256
    ).exists()


def document_officiel_signe(document) -> bool:
    """Document de type officiel dont la version courante est signée : contenu scellé."""
    return bool(document.type_id and document.type.officiel and version_signee(document.current_version))
