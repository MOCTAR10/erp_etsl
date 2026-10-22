"""Mot de passe en libre-service (écarts transverses, guides utilisateur).

- « Changer mon mot de passe » : ancien + nouveau + confirmation, validateurs Django, journalisé ; les autres
  sessions sont invalidées (les jetons JWT portent l'empreinte du mot de passe : `CHECK_REVOKE_TOKEN`), la session
  courante reçoit de nouveaux jetons.
- « Mot de passe oublié » : lien à usage unique par courriel (jeton signé, expirant après MDP_LIEN_VALIDITE_MIN,
  paramètre provisoire ; invalidé dès que le mot de passe change). Réponse identique que le compte existe ou non.
- Réinitialisation par l'administrateur : mot de passe provisoire + changement obligatoire à la prochaine connexion
  (`doit_changer_mdp` : toute autre API répond 403 tant que le mot de passe n'est pas changé).
"""

import hashlib

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import transaction
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .journal import journaliser
from .models import JournalAcces, User

Evt = JournalAcces.Evenement
SEL = "etls.mdp.reinitialisation"
MESSAGE_OUBLI = "Si un compte actif correspond à cette adresse, un lien de réinitialisation vient d'être envoyé."
MESSAGE_SANS_EMAIL = (
    "L'envoi de courriels n'est pas encore configuré : contactez votre administrateur, qui réinitialisera votre "
    "mot de passe (vous le changerez à la connexion)."
)


def email_actif():
    return bool(getattr(settings, "EMAIL_ENABLED", False))


class ConfigMotDePasseView(APIView):
    """`GET /api/users/mot-de-passe/config/` : le lien par courriel est-il disponible ? (public, sans donnée)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response({"email_actif": email_actif(), "message": "" if email_actif() else MESSAGE_SANS_EMAIL})


def _empreinte(user):
    """Change dès que le mot de passe change : un lien déjà utilisé (ou antérieur au dernier changement) est mort."""
    return hashlib.sha256(f"{user.pk}:{user.password}".encode()).hexdigest()[:24]


def emettre_jeton(user):
    return signing.dumps({"u": str(user.pk), "e": _empreinte(user)}, salt=SEL)


def lire_jeton(jeton):
    from .parametres import valeur_transverse

    duree = int(valeur_transverse("MDP_LIEN_VALIDITE_MIN")) * 60
    try:
        data = signing.loads(str(jeton or ""), salt=SEL, max_age=duree)
    except (signing.BadSignature, TypeError):
        return None
    user = User.objects.filter(pk=data.get("u"), is_active=True).first()
    if user is None or data.get("e") != _empreinte(user):
        return None
    return user


def _nouveau_mdp(user, data):
    nouveau, confirmation = str(data.get("nouveau") or ""), str(data.get("confirmation") or "")
    if not nouveau:
        raise ValidationError({"nouveau": "Nouveau mot de passe obligatoire."})
    if nouveau != confirmation:
        raise ValidationError({"confirmation": "La confirmation ne correspond pas au nouveau mot de passe."})
    try:
        validate_password(nouveau, user)
    except DjangoValidationError as exc:
        raise ValidationError({"nouveau": list(exc.messages)})
    return nouveau


def _jetons(user):
    refresh = RefreshToken.for_user(user)
    return {"refresh": str(refresh), "access": str(refresh.access_token)}


class ChangerMotDePasseView(APIView):
    """`POST /api/users/me/mot-de-passe/` `{ancien, nouveau, confirmation}` → nouveaux jetons."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            if not user.check_password(str(request.data.get("ancien") or "")):
                raise ValidationError({"ancien": "Mot de passe actuel incorrect."})
            nouveau = _nouveau_mdp(user, request.data)
            if user.check_password(nouveau):
                raise ValidationError({"nouveau": "Le nouveau mot de passe doit être différent de l'actuel."})
            user.set_password(nouveau)
            user.doit_changer_mdp = False
            user.save(update_fields=["password", "doit_changer_mdp"])
        journaliser(request, Evt.MDP_CHANGE, user=user)
        return Response({"detail": "Mot de passe modifié. Les autres sessions sont déconnectées.", **_jetons(user)})


class MotDePasseOublieView(APIView):
    """`POST /api/users/mot-de-passe/oubli/` `{email}` : réponse identique, que le compte existe ou non."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        from .parametres import valeur_transverse

        email = str(request.data.get("email") or "").strip()
        if not email_actif():
            # Messagerie non configurée : aucun lien envoyé, chemin = réinitialisation par l'administrateur.
            return Response({"detail": MESSAGE_SANS_EMAIL, "email_actif": False})
        user = User.objects.filter(email__iexact=email, is_active=True).first() if email else None
        journaliser(request, Evt.MDP_OUBLI, user=user, email=email)
        if user is not None:
            lien = f"{settings.FRONTEND_URL.rstrip('/')}/reinitialiser-mot-de-passe?jeton={emettre_jeton(user)}"
            minutes = int(valeur_transverse("MDP_LIEN_VALIDITE_MIN"))
            try:
                send_mail(
                    subject="[ETSL ERP] Réinitialisation de votre mot de passe",
                    message=(
                        f"Bonjour,\n\nUne réinitialisation du mot de passe de votre compte ETSL ERP a été demandée.\n"
                        f"Lien à usage unique, valable {minutes} minutes :\n{lien}\n\n"
                        f"Si vous n'êtes pas à l'origine de cette demande, ignorez ce message."
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=True,
                )
            except Exception:  # noqa: BLE001 — réponse identique même si l'envoi échoue
                pass
        return Response({"detail": MESSAGE_OUBLI, "email_actif": True})


class ReinitialiserMotDePasseView(APIView):
    """`POST /api/users/mot-de-passe/reinitialiser/` `{jeton, nouveau, confirmation}` (lien du courriel)."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        with transaction.atomic():
            user = lire_jeton(request.data.get("jeton"))
            if user is None:
                raise ValidationError({"jeton": "Lien invalide, expiré ou déjà utilisé : refaites une demande."})
            user = User.objects.select_for_update().get(pk=user.pk)
            nouveau = _nouveau_mdp(user, request.data)
            user.set_password(nouveau)
            user.doit_changer_mdp = False
            user.save(update_fields=["password", "doit_changer_mdp"])
        journaliser(request, Evt.MDP_REINITIALISATION, user=user, details={"par": "lien courriel"})
        return Response({"detail": "Mot de passe réinitialisé : connectez-vous avec le nouveau mot de passe."})


def reinitialiser_par_admin(request, user):
    """Mot de passe provisoire posé par l'administrateur ; changement imposé à la prochaine connexion."""
    provisoire = str(request.data.get("mot_de_passe") or "")
    try:
        validate_password(provisoire, user)
    except DjangoValidationError as exc:
        raise ValidationError({"mot_de_passe": list(exc.messages)})
    user.set_password(provisoire)
    user.doit_changer_mdp = True
    user.save(update_fields=["password", "doit_changer_mdp"])
    journaliser(request, Evt.MDP_REINITIALISATION, user=user, details={"par": request.user.email})
