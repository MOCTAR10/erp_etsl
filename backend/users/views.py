import csv
import io

from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import generics, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from config.inputs import date_input

from . import mfa
from .journal import journaliser
from .models import JournalAcces, User
from .permissions import IsAdmin
from .rbac import ERP_APPS, modules_for_role
from .serializers import AdminUserSerializer, JournalAccesSerializer, UserCreateSerializer, UserSerializer

Evt = JournalAcces.Evenement


def _jetons(user):
    refresh = RefreshToken.for_user(user)
    return {"refresh": str(refresh), "access": str(refresh.access_token)}


class ThrottledTokenObtainPairView(TokenObtainPairView):
    """Connexion JWT avec limitation de débit anti brute-force (scope `login`), journal des accès (EX-G-10)
    et étape MFA pour les rôles sensibles (lot 15b) : le mot de passe seul ne délivre alors aucun jeton JWT."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def throttled(self, request, wait):
        journaliser(request, Evt.CONNEXION_BLOQUEE, email=str(request.data.get("email", "")))
        super().throttled(request, wait)

    def post(self, request, *args, **kwargs):
        email = str(request.data.get("email", "")).strip()
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except AuthenticationFailed:
            journaliser(request, Evt.ECHEC_CONNEXION, user=User.objects.filter(email__iexact=email).first(), email=email)
            raise
        except TokenError as exc:
            raise InvalidToken(exc.args[0])
        user = serializer.user
        if mfa.mfa_requise(user):
            return Response({
                "mfa_requis": True,
                "mfa_enrolement": not user.mfa_active,
                "mfa_jeton": mfa.emettre_jeton(user),
            })
        journaliser(request, Evt.CONNEXION, user=user)
        return Response(serializer.validated_data)


class _EtapeMfaView(APIView):
    """Étapes MFA appelées entre le mot de passe et la délivrance des jetons (jeton MFA signé, 5 min)."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def utilisateur(self, request, verrou=False):
        pk = mfa.lire_jeton(request.data.get("mfa_jeton"))
        qs = User.objects.select_for_update() if verrou else User.objects
        user = qs.filter(pk=pk, is_active=True).first() if pk else None
        if user is None:
            raise ValidationError({"mfa_jeton": "Jeton MFA invalide ou expiré : reconnectez-vous."})
        return user


class MfaEnrolementView(_EtapeMfaView):
    """Premier passage : clé secrète TOTP à enregistrer dans l'application d'authentification."""

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        user = self.utilisateur(request)
        if user.mfa_active:
            raise ValidationError({"detail": "MFA déjà activée pour ce compte."})
        if not user.mfa_secret:
            user.mfa_secret = mfa.generer_secret()
            user.save(update_fields=["mfa_secret"])
        journaliser(request, Evt.MFA_ENROLEMENT, user=user)
        return Response({"secret": user.mfa_secret, "otpauth_uri": mfa.uri_otpauth(user.mfa_secret, user.email)})


class MfaVerificationView(_EtapeMfaView):
    """Code TOTP valide (non rejoué) → activation au premier passage + délivrance des jetons JWT."""

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        # Verrou sur le compte : deux soumissions simultanées du même code ne passent pas toutes les deux.
        with transaction.atomic():
            user = self.utilisateur(request, verrou=True)
            pas = mfa.verifier(user.mfa_secret, request.data.get("code"), user.mfa_dernier_pas)
            if pas is not None:
                user.mfa_dernier_pas = pas
                champs = ["mfa_dernier_pas"]
                if not user.mfa_active:
                    user.mfa_active, user.mfa_active_le = True, timezone.now()
                    champs += ["mfa_active", "mfa_active_le"]
                user.save(update_fields=champs)
        if pas is None:  # journalisé hors transaction : l'échec reste tracé malgré le refus
            journaliser(request, Evt.MFA_ECHEC, user=user)
            raise ValidationError({"code": "Code invalide ou expiré."})
        journaliser(request, Evt.MFA_SUCCES, user=user)
        journaliser(request, Evt.CONNEXION, user=user, details={"mfa": True})
        return Response(_jetons(user))


class MeView(generics.RetrieveUpdateAPIView):
    """Profil de l'utilisateur connecté."""

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class UserViewSet(viewsets.ModelViewSet):
    """Gestion des utilisateurs — admin uniquement (RF-62)."""

    queryset = User.objects.all().order_by("email")
    serializer_class = UserSerializer
    permission_classes = [IsAdmin]
    http_method_names = ["get", "post", "patch", "delete"]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        return AdminUserSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if role := params.get("role"):
            qs = qs.filter(role=role)
        if (actif := params.get("actif")) in ("0", "1"):
            qs = qs.filter(is_active=actif == "1")
        if q := params.get("search", "").strip():
            qs = qs.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
        return qs

    def list(self, request, *args, **kwargs):
        fmt = request.query_params.get("export")
        if fmt not in ("csv", "xlsx", "pdf"):
            return super().list(request, *args, **kwargs)
        from config.exports import export_response

        colonnes = [("email", "Email"), ("nom", "Nom"), ("role", "Rôle"), ("actif", "Actif"), ("mfa", "MFA activée"),
                    ("modules", "Modules lisibles"), ("derniere_connexion", "Dernière connexion")]
        lignes = [{
            "email": u.email, "nom": u.get_full_name(), "role": u.get_role_display(), "actif": u.is_active,
            "mfa": u.mfa_active, "modules": ", ".join(modules_for_role(u.role)), "derniere_connexion": u.last_login,
        } for u in self.filter_queryset(self.get_queryset())]
        return export_response(lignes, colonnes, fmt, "Utilisateurs et droits ETSL", "utilisateurs")

    def perform_destroy(self, instance):
        if instance.pk == self.request.user.pk:
            raise ValidationError({"detail": "Vous ne pouvez pas supprimer votre propre compte."})
        # Un compte qui a laissé une trace (pièces, validations) se désactive : la suppression lèverait un 409.
        instance.delete()

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"], url_path="reinitialiser-mot-de-passe")
    def reinitialiser_mot_de_passe(self, request, pk=None):
        """Mot de passe provisoire `{mot_de_passe}` ; l'utilisateur devra le changer à sa prochaine connexion."""
        from .motdepasse import reinitialiser_par_admin

        user = self.get_object()
        reinitialiser_par_admin(request, user)
        return Response(AdminUserSerializer(user, context={"request": request}).data)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def matrice(self, request):
        """Matrice rôle → modules ERP lisibles (EX-G-01), avec le nombre de comptes actifs par rôle."""
        comptes = dict(User.objects.filter(is_active=True).values_list("role").annotate(n=Count("id")).order_by())
        return Response({
            "modules": list(ERP_APPS),
            "roles": [
                {"role": code, "label": label, "modules": list(modules_for_role(code)), "comptes_actifs": comptes.get(code, 0)}
                for code, label in User.Role.choices
            ],
        })

    @action(detail=True, methods=["post"], url_path="reinitialiser-mfa")
    def reinitialiser_mfa(self, request, pk=None):
        """Perte du téléphone : l'admin efface le secret. Un rôle de `MFA_ROLES` est relancé en enrôlement à la
        prochaine connexion ; les autres réactivent la MFA eux-mêmes depuis /signatures (facultative pour eux).
        Le bouton n'est proposé que si la MFA est active : sans secret, il n'y a rien à effacer."""
        user = self.get_object()
        user.mfa_secret, user.mfa_active, user.mfa_active_le, user.mfa_dernier_pas = "", False, None, None
        user.save(update_fields=["mfa_secret", "mfa_active", "mfa_active_le", "mfa_dernier_pas"])
        journaliser(request, Evt.MFA_REINITIALISATION, user=user, details={"par": request.user.email})
        return Response(UserSerializer(user).data)


class JournalAccesViewSet(viewsets.ReadOnlyModelViewSet):
    """Journal des accès (EX-G-10) — lecture et export réservés à l'administrateur ; aucune écriture par l'API."""

    queryset = JournalAcces.objects.select_related("user").all()
    serializer_class = JournalAccesSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if evenement := params.get("evenement"):
            qs = qs.filter(evenement=evenement)
        if email := params.get("email"):
            qs = qs.filter(email__icontains=email)
        if du := date_input(params.get("du"), "du"):
            qs = qs.filter(cree_le__date__gte=du)
        if au := date_input(params.get("au"), "au"):
            qs = qs.filter(cree_le__date__lte=au)
        return qs

    def list(self, request, *args, **kwargs):
        if request.query_params.get("export") != "csv":
            return super().list(request, *args, **kwargs)
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";")
        writer.writerow(["horodatage", "evenement", "email", "ip", "ressource", "navigateur"])
        for j in self.get_queryset().iterator():
            writer.writerow([j.cree_le.isoformat(), j.evenement, j.email, j.ip or "", j.chemin, j.user_agent])
        response = HttpResponse(buffer.getvalue().encode("utf-8-sig"), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="journal_acces.csv"'
        return response
