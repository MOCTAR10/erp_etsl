"""Lot a3 « flux terrain » : saisie hors ligne (horodatage de saisie, conflits de synchronisation) et consommation
OF → stock (M3 → M5) depuis l'écran de l'OF.

Hors ligne (CL-OM-08) : chaque saisie terrain porte `saisi_le` (heure de l'appareil au moment de la saisie). À la
synchronisation, le serveur rejette en **409 (conflit)** une saisie trop ancienne ou un doublon probable : l'appareil
la marque « conflit » et l'utilisateur choisit « Forcer » (renvoi avec `forcer=true`) ou « Abandonner ».
"""

from datetime import timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import APIException
from rest_framework.response import Response

from config.inputs import positive_decimal

#: Tolérance d'horloge : une saisie « dans le futur » au-delà est refusée (horloge de l'appareil déréglée).
TOLERANCE_FUTUR = timedelta(minutes=10)


class ConflitSaisie(APIException):
    status_code = 409
    default_detail = "Conflit de synchronisation : saisie à confirmer ou à abandonner."
    default_code = "conflit"


def as_bool(valeur):
    return str(valeur).strip().lower() in ("1", "true", "on", "oui", "yes")


def verifier_saisi_le(valeur):
    """Horodatage de saisie de l'appareil : jamais dans le futur (au-delà de la tolérance d'horloge)."""
    if valeur and valeur > timezone.now() + TOLERANCE_FUTUR:
        raise serializers.ValidationError("Horodatage de saisie dans le futur : vérifier l'horloge de l'appareil.")
    return valeur


def saisi_le_input(valeur):
    """`saisi_le` d'une action (hors sérialiseur) : date-heure ISO valide, sinon 400."""
    if valeur in (None, ""):
        return None
    try:
        return verifier_saisi_le(serializers.DateTimeField().run_validation(valeur))
    except serializers.ValidationError as exc:
        raise serializers.ValidationError({"saisi_le": exc.detail})


def controler_synchro(saisi_le, request, doublons=None, objet="Saisie"):
    """Conflits de synchronisation d'une saisie terrain (seulement si elle porte `saisi_le`) :
    - saisie plus ancienne que `TERRAIN_DELAI_SYNCHRO_JOURS` (0 = sans limite) ;
    - doublon probable (`doublons` non vide) si `TERRAIN_DOUBLON_CONFLIT` = 1.
    `forcer=true` dans le corps lève le conflit (choix explicite de l'utilisateur)."""
    if saisi_le is None or as_bool(request.data.get("forcer")):
        return
    from .ecarts import param

    jours = int(param("TERRAIN_DELAI_SYNCHRO_JOURS"))
    if jours and timezone.now() - saisi_le > timedelta(days=jours):
        raise ConflitSaisie(
            f"{objet} saisie le {timezone.localtime(saisi_le):%d/%m/%Y %H:%M}, synchronisée plus de {jours} j après : "
            "à confirmer (Forcer) ou à abandonner."
        )
    if doublons is not None and param("TERRAIN_DOUBLON_CONFLIT") and doublons.exists():
        raise ConflitSaisie(f"{objet} identique déjà enregistrée sur le serveur (doublon probable) : forcer ou abandonner.")


# ----------------------------------------------------------------------------------------------------------------
# M3 → M5 : consommation de matière sur l'OF (sortie de stock liée à l'OF)
# ----------------------------------------------------------------------------------------------------------------
STATUTS_CONSOMMABLES = ("lance", "en_cours")


def consommer_sur_of(of, user, *, article, depot, quantite, lot=None, date=None, notes=""):
    """Sortie de stock « consommation » imputée à l'OF : contrôles M5 (lot obligatoire, quarantaine, dépôt, stock
    réservé, stock suffisant), coût CUMP/FIFO, imputation analytique de l'affaire, solde de la réservation."""
    from stocks.models import MouvementStock
    from stocks.services import apply_move, controler_depot

    if of.status not in STATUTS_CONSOMMABLES:
        raise serializers.ValidationError({"detail": "Consommation possible seulement sur un OF lancé ou en cours."})
    if quantite <= 0:
        raise serializers.ValidationError({"quantite": "La quantité consommée doit être strictement positive."})
    if lot is not None and lot.article_id != article.pk:
        raise serializers.ValidationError({"lot": "Ce lot n'appartient pas à l'article choisi."})
    try:
        with transaction.atomic():
            mouvement = MouvementStock.objects.create(
                type_mouvement=MouvementStock.Type.CONSOMMATION, article=article, quantite=quantite, source=depot,
                lot=lot, ordre=of, date=date or timezone.localdate(), created_by=user,
                document_reference=of.code[:60], notes=notes,
            )
            controler_depot(mouvement, user)
            apply_move(mouvement)
    except (ValueError, DjangoValidationError) as exc:
        messages = getattr(exc, "messages", None) or [str(exc)]
        raise serializers.ValidationError({"detail": " ".join(messages)})
    return mouvement


def consommations_of(of, voir_montants):
    from stocks.models import MouvementStock

    lignes = []
    for m in (
        MouvementStock.objects.filter(ordre=of, type_mouvement=MouvementStock.Type.CONSOMMATION)
        .select_related("article", "lot", "source").order_by("-date", "-created_at")
    ):
        valeur = m.quantite * m.cout_unitaire
        lignes.append({
            "id": str(m.pk), "code": m.code, "date": m.date.isoformat(), "article": str(m.article_id),
            "article_code": m.article.code, "article_label": m.article.label,
            "lot": str(m.lot_id) if m.lot_id else None, "lot_code": m.lot.code if m.lot_id else None,
            "numero_coulee": m.lot.numero_coulee if m.lot_id else "",
            "depot_code": m.source.code if m.source_id else None, "quantite": str(m.quantite),
            "cout_unitaire": str(m.cout_unitaire.quantize(1)) if voir_montants else None,
            "valeur": str(valeur.quantize(1)) if voir_montants else None,
        })
    return lignes


class ConsommationOfMixin:
    """`/api/operations/ordres/<id>/consommations/` : GET = sorties de stock de l'OF ; POST = consommer (magasin)."""

    def get_permissions(self):
        if getattr(self, "action", None) == "consommations" and self.request.method == "POST":
            from stocks.services import CanManageStocks

            return [CanManageStocks()]
        return super().get_permissions()

    @action(detail=True, methods=["get", "post"], url_path="consommations")
    def consommations(self, request, pk=None):
        from referentiels.models import Article
        from stocks.models import Depot, LotMatiere
        from stocks.services import can_see_amount as voir_montants_stock

        from .models import OrdreFabrication

        of = self.get_object()
        if request.method == "POST":
            with transaction.atomic():
                of = OrdreFabrication.objects.select_for_update(of=("self",)).get(pk=of.pk)
                data = request.data
                article = _fk(Article, data.get("article"), "article")
                depot = _fk(Depot, data.get("depot"), "depot")
                lot = _fk(LotMatiere, data.get("lot"), "lot", requis=False)
                date = serializers.DateField().run_validation(data.get("date")) if data.get("date") else None
                consommer_sur_of(
                    of, request.user, article=article, depot=depot, lot=lot, date=date,
                    quantite=positive_decimal(data.get("quantite"), "quantite"), notes=str(data.get("notes", ""))[:500],
                )
        voir = voir_montants_stock(request.user) or bool(self.get_serializer_context().get("can_view_amount"))
        return Response({"ordre": str(of.pk), "ordre_code": of.code, "lignes": consommations_of(of, voir)},
                        status=201 if request.method == "POST" else 200)


def _fk(modele, valeur, champ, requis=True):
    if valeur in (None, ""):
        if requis:
            raise serializers.ValidationError({champ: "Champ obligatoire."})
        return None
    try:
        return modele.objects.get(pk=valeur)
    except (modele.DoesNotExist, DjangoValidationError, ValueError):
        raise serializers.ValidationError({champ: "Référence inconnue."})

