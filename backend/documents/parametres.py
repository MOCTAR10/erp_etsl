"""Paramètres provisoires de la GED (écarts a1) : norme PDF/A d'archivage et PDF/A des exports (EX-G-08).

Valeurs = DONNÉES modifiables à l'écran `/parametres` (registre `config/parametres_etsl.py`), affichées « provisoire —
à confirmer ou modifier par ETSL » tant qu'ETSL ne les a pas confirmées. Modification et confirmation : admin, PDG,
DGA. Une valeur modifiée redevient provisoire. Question ETSL : norme exigée (PDF/A-2b par défaut) et documents concernés.
"""

from decimal import Decimal, InvalidOperation

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response

from config import pdfa
from config.i18n import tr

from .models import ParametreGed

#: code -> (libellé, valeur, unité, texte)
PARAMETRES_DEFAUT = {
    "PDFA_NORME": ("Norme PDF/A des PDF versés en GED (1b, 2b, 3b ou aucune)", Decimal("0"), "", "2b"),
    "PDFA_EXPORTS": ("Exports PDF convertis en PDF/A (1 = oui, 0 = non)", Decimal("1"), "booléen", ""),
}
PARAMETRES_TEXTE = {code for code, d in PARAMETRES_DEFAUT.items() if d[3]}
EDITION_ROLES = ("admin", "pdg", "dga")


def get_parametre(code):
    label, valeur, unite, texte = PARAMETRES_DEFAUT[code]
    p, _ = ParametreGed.objects.get_or_create(
        code=code, defaults={"label": label, "valeur": valeur, "unite": unite, "texte": texte}
    )
    return p


def assurer_parametres():
    for code in PARAMETRES_DEFAUT:
        get_parametre(code)


def norme_pdfa():
    """Norme PDF/A en vigueur pour la GED ("1b" | "2b" | "3b"), ou "" si désactivée."""
    try:
        norme = get_parametre("PDFA_NORME").texte.strip().lower()
    except Exception:  # noqa: BLE001 — table absente (migrations) : défaut du code
        norme = pdfa.NORME_DEFAUT
    return norme if norme in pdfa.NORMES else ""


def pdfa_exports_actif():
    try:
        return get_parametre("PDFA_EXPORTS").valeur == 1
    except Exception:  # noqa: BLE001
        return True


def preparer_fichier(uploaded):
    """Fichier à archiver : PDF converti en PDF/A selon le paramètre, sinon l'original. Renvoie
    `(fichier, statut, norme)` ; ne lève jamais (dégradation propre, cf. `config.pdfa`)."""
    norme = norme_pdfa()
    nom = getattr(uploaded, "name", "") or "document.pdf"
    uploaded.seek(0)
    entete = uploaded.read(1024)
    uploaded.seek(0)
    if not pdfa.est_pdf(entete):
        return uploaded, pdfa.NON_PDF, ""
    if not norme:
        return uploaded, pdfa.DESACTIVE, ""
    contenu = b"".join(uploaded.chunks())
    uploaded.seek(0)
    converti, statut = pdfa.convertir_pdfa(contenu, norme)
    if statut != pdfa.CONVERTI:
        return uploaded, statut, ""
    return ContentFile(converti, name=nom), statut, norme


def peut_editer(user):
    return bool(user and user.is_authenticated) and (user.is_staff or user.role in EDITION_ROLES)


class CanEditerParametreGed(BasePermission):
    message = "Paramètres GED : modification réservée à l'administrateur et à la Direction Générale."

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return bool(request.user and request.user.is_authenticated)
        return peut_editer(request.user)


class ParametreGedSerializer(serializers.ModelSerializer):
    provisoire = serializers.SerializerMethodField()
    confirme_par_email = serializers.SerializerMethodField()

    class Meta:
        model = ParametreGed
        fields = ["id", "code", "label", "valeur", "texte", "unite", "statut_valeur", "provisoire",
                  "confirme_par_email", "confirme_le"]
        read_only_fields = fields

    def get_provisoire(self, obj):
        return obj.statut_valeur != ParametreGed.StatutValeur.CONFIRME

    def get_confirme_par_email(self, obj):
        return getattr(obj.confirme_par, "email", None)


class ParametreGedViewSet(viewsets.ModelViewSet):
    """Paramètres GED : lecture par tout compte, modification / confirmation par admin, PDG, DGA."""

    permission_classes = [IsAuthenticated, CanEditerParametreGed]
    serializer_class = ParametreGedSerializer
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_queryset(self):
        assurer_parametres()
        return ParametreGed.objects.filter(code__in=list(PARAMETRES_DEFAUT)).select_related("confirme_par")

    def create(self, request, *args, **kwargs):
        return Response({"detail": "Paramètres prédéfinis : modification seulement."}, status=405)

    def partial_update(self, request, *args, **kwargs):
        with transaction.atomic():
            p = ParametreGed.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
            if p.code in PARAMETRES_TEXTE:
                texte = str(request.data.get("texte", request.data.get("valeur", "")) or "").strip().lower()
                if texte not in (*pdfa.NORMES, "aucune"):
                    raise serializers.ValidationError({"texte": tr("Norme PDF/A attendue : 1b, 2b, 3b ou aucune.")})
                p.texte = texte
            else:
                try:
                    valeur = Decimal(str(request.data.get("valeur")).replace(",", ".").strip())
                except (InvalidOperation, ValueError):
                    raise serializers.ValidationError({"valeur": tr("Nombre attendu.")})
                if valeur not in (0, 1):
                    raise serializers.ValidationError({"valeur": tr("0 (non) ou 1 (oui).")})
                p.valeur = valeur
            p.statut_valeur = ParametreGed.StatutValeur.PROVISOIRE
            p.confirme_par, p.confirme_le = None, None
            p.save()
        return Response(self.get_serializer(p).data)

    def update(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def confirmer(self, request, pk=None):
        with transaction.atomic():
            p = ParametreGed.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
            p.statut_valeur = ParametreGed.StatutValeur.CONFIRME
            p.confirme_par, p.confirme_le = request.user, timezone.now()
            p.save(update_fields=["statut_valeur", "confirme_par", "confirme_le"])
        return Response(self.get_serializer(p).data)
