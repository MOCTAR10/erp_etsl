"""API du suivi inter-modules M11 : marges à terminaison reçues de M3, balance âgée de M10 (voir `suivi.py`)."""

from decimal import Decimal

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.fields import DateField
from rest_framework.response import Response

from users.permissions import can_read_module

from . import suivi
from .models import MargeTerminaisonAffaire
from .services import CanManageGestion, can_see_amount

MONTANTS = ("chiffre_affaires", "couts_engages", "cout_a_terminaison", "marge_a_terminaison")


def _s(v):
    return None if v is None else str(v)


class MargesTerminaisonView(viewsets.ViewSet):
    """Dernière marge à terminaison publiée par M3 pour chaque affaire (événement outbox)."""

    def get_permissions(self):
        if self.action == "integrer":
            return [CanManageGestion()]
        return [can_read_module("controle_gestion")()]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def list(self, request):
        from outbox.models import OutboxEvent

        voir = can_see_amount(request.user)
        rows = []
        for m in MargeTerminaisonAffaire.objects.select_related("affaire").order_by("affaire__code"):
            row = {
                "id": str(m.pk), "affaire": str(m.affaire_id), "affaire_code": m.affaire.code,
                "affaire_label": m.affaire.title, "avancement_pct": _s(m.avancement_pct),
                "marge_pct": _s(m.marge_pct) if voir else None, "ordres": m.ordres,
                "publie_le": m.publie_le.isoformat() if m.publie_le else None, "publie_par": m.publie_par,
                "recu_le": m.recu_le.isoformat(),
                "alerte": m.marge_a_terminaison is not None and m.marge_a_terminaison < Decimal("0"),
            }
            for champ in MONTANTS:
                row[champ] = _s(getattr(m, champ)) if voir else None
            rows.append(row)
        en_attente = OutboxEvent.objects.filter(topic=suivi.TOPIC_MARGE, status=OutboxEvent.Status.PENDING).count()
        return Response({"rows": rows, "en_attente": en_attente, "has_amount_access": voir})

    @extend_schema(request=None, responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["post"])
    def integrer(self, request):
        """Intègre tout de suite les événements en attente (sinon : tâche périodique de l'outbox)."""
        from outbox.tasks import dispatch_outbox

        return Response(dispatch_outbox(limit=500))


class BalanceAgeeGestionView(viewsets.ViewSet):
    """Balance âgée clients / fournisseurs de la comptabilité (M10), lue par le contrôle de gestion."""

    permission_classes = [can_read_module("controle_gestion")]

    @extend_schema(parameters=[OpenApiParameter("date", type=str, required=False)], responses={200: OpenApiTypes.OBJECT})
    def list(self, request):
        brut = request.query_params.get("date")
        date_to = DateField().run_validation(brut) if brut else None
        voir = can_see_amount(request.user)
        sortie = {}
        for nature, etat in suivi.balances_agees(date_to).items():
            tableau = etat["tableaux"][0]
            montants = [c["key"] for c in tableau["colonnes"] if c.get("montant")]
            lignes = []
            for ligne in tableau["lignes"]:
                ligne = dict(ligne)
                for cle in montants:
                    ligne[cle] = (str(ligne[cle]) if ligne.get(cle) is not None else None) if voir else None
                lignes.append(ligne)
            sortie[nature] = {
                "titre": etat["titre"], "sous_titre": etat["sous_titre"], "provisoire": etat["provisoire"],
                "avertissement": etat["avertissement"], "colonnes": tableau["colonnes"], "lignes": lignes,
            }
        return Response({**sortie, "has_amount_access": voir})
