"""Paramètres transverses du socle (écarts transverses) : valeurs provisoires modifiables à l'écran par ETSL.

Chaque valeur est une DONNÉE (jamais figée dans le code) : le défaut ci-dessous n'est qu'un point de départ,
créé à la volée, affiché « provisoire — à confirmer ou modifier par ETSL » tant qu'ETSL ne l'a pas confirmé.
Modification : administrateur, PDG, DGA ; une valeur modifiée redevient provisoire. Confirmation : PDG, DGA, admin.
"""

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response

from .models import ParametreTransverse, User

#: code -> (libellé, valeur, unité, texte). Questions ETSL en commentaire.
PARAMETRES_DEFAUT = {
    # §8.2 Audit / EX-G-06 : durée de conservation de la piste d'audit et du journal des accès (CDC : 5 ans).
    "AUDIT_RETENTION_ANS": ("Conservation de la piste d'audit et du journal des accès", Decimal("5"), "ans", ""),
    # EX-G-05 : courriel systématique de chaque notification interne (1 = oui, 0 = interne seulement).
    "NOTIF_EMAIL_ACTIF": ("Courriel envoyé pour chaque notification interne (1 = oui, 0 = non)", Decimal("1"), "booléen", ""),
    # §8.2 Continuité : fenêtre de maintenance autorisée et responsable de l'exercice de restauration.
    "MAINTENANCE_FENETRE": ("Fenêtre de maintenance autorisée", Decimal("0"), "", "Dimanche 02:00-06:00 (heure de Libreville)"),
    "MAINTENANCE_RESPONSABLE": ("Responsable de l'exploitation et signataire de l'exercice de reprise", Decimal("0"), "", "DSI ETSL (à désigner)"),
    "RESTAURATION_PERIODICITE_JOURS": ("Périodicité de l'exercice de restauration des sauvegardes", Decimal("90"), "jours", ""),
    "RPO_HEURES": ("Perte de données maximale admissible (RPO)", Decimal("24"), "h", ""),
    "RTO_HEURES": ("Durée maximale de reprise (RTO) — objectif interne du PRA ; engagement contractuel CDC : 48 h ; objectif interne : à confirmer par ETSL", Decimal("8"), "h", ""),
    # Mot de passe oublié : durée de validité du lien à usage unique envoyé par courriel.
    "MDP_LIEN_VALIDITE_MIN": ("Validité du lien « mot de passe oublié »", Decimal("60"), "min", ""),
    # §8.2 Performance : seuil de temps de réponse au-delà duquel une requête est journalisée comme lente.
    "PERF_SEUIL_MS": ("Seuil de temps de réponse d'un écran (au-delà : requête journalisée lente)", Decimal("3000"), "ms", ""),
    # EX-G-03 : un compte rattaché à un site ne lit que les fiches de son site (1) ; 0 = tous les sites (défaut).
    "SITES_LECTURE_RESTREINTE": ("Lecture limitée au site de rattachement du compte (1 = oui, 0 = non)", Decimal("0"), "booléen", ""),
}

#: Paramètres à valeur texte (les autres sont numériques).
PARAMETRES_TEXTE = {code for code, d in PARAMETRES_DEFAUT.items() if d[3]}

EDITION_ROLES = (User.Role.ADMIN, User.Role.PDG, User.Role.DGA)


def get_param_transverse(code):
    """Paramètre (créé avec sa valeur par défaut provisoire s'il n'existe pas encore)."""
    label, valeur, unite, texte = PARAMETRES_DEFAUT[code]
    p, _ = ParametreTransverse.objects.get_or_create(
        code=code, defaults={"label": label, "valeur": valeur, "unite": unite, "texte": texte}
    )
    return p


def valeur_transverse(code):
    """Valeur numérique courante (défaut si la base est indisponible, ex. pendant les migrations)."""
    try:
        return get_param_transverse(code).valeur
    except Exception:  # noqa: BLE001 — table absente (migrations) : le défaut du code s'applique
        return PARAMETRES_DEFAUT[code][1]


def assurer_parametres():
    for code in PARAMETRES_DEFAUT:
        get_param_transverse(code)


def peut_editer(user):
    return bool(user and user.is_authenticated) and (user.is_staff or user.role in EDITION_ROLES)


class CanEditerParametreTransverse(BasePermission):
    message = "Paramètres transverses : modification réservée à l'administrateur et à la Direction Générale."

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return bool(request.user and request.user.is_authenticated)
        return peut_editer(request.user)


class ParametreTransverseViewSet(viewsets.ModelViewSet):
    """Paramètres transverses : lecture par tout compte, modification / confirmation par admin, PDG, DGA."""

    permission_classes = [IsAuthenticated, CanEditerParametreTransverse]
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_serializer_class(self):
        from .serializers import ParametreTransverseSerializer

        return ParametreTransverseSerializer

    def get_queryset(self):
        assurer_parametres()
        return ParametreTransverse.objects.filter(code__in=list(PARAMETRES_DEFAUT)).select_related("confirme_par")

    def create(self, request, *args, **kwargs):
        return Response({"detail": "Paramètres prédéfinis : modification seulement."}, status=405)

    def partial_update(self, request, *args, **kwargs):
        with transaction.atomic():
            p = ParametreTransverse.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
            if p.code in PARAMETRES_TEXTE:
                texte = str(request.data.get("texte", request.data.get("valeur", "")) or "").strip()
                if not texte:
                    raise serializers.ValidationError({"texte": "Valeur texte obligatoire."})
                p.texte = texte[:200]
            else:
                brut = request.data.get("valeur")
                try:
                    valeur = Decimal(str(brut).replace(",", ".").strip())
                except (InvalidOperation, ValueError):
                    raise serializers.ValidationError({"valeur": "Nombre attendu."})
                if valeur < 0 or not valeur.is_finite():
                    raise serializers.ValidationError({"valeur": "Valeur positive attendue."})
                if p.code in ("NOTIF_EMAIL_ACTIF", "SITES_LECTURE_RESTREINTE") and valeur not in (0, 1):
                    raise serializers.ValidationError({"valeur": "0 (non) ou 1 (oui)."})
                p.valeur = valeur
            p.statut_valeur = ParametreTransverse.StatutValeur.PROVISOIRE
            p.confirme_par, p.confirme_le = None, None
            p.save()
        return Response(self.get_serializer(p).data)

    def update(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def confirmer(self, request, pk=None):
        with transaction.atomic():
            p = ParametreTransverse.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
            p.statut_valeur = ParametreTransverse.StatutValeur.CONFIRME
            p.confirme_par, p.confirme_le = request.user, timezone.now()
            p.save(update_fields=["statut_valeur", "confirme_par", "confirme_le"])
        return Response(self.get_serializer(p).data)
