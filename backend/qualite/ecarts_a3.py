"""Lot a3 « flux terrain » côté M6.

- M5 → M6 : le joint soudé cite le **lot de stock** du métal de base ; la coulée en est reprise, les certificats
  (3.1 = MTC EN 10204) sont visibles, et la traçabilité remonte joint → lot → certificats → réception → sortie OF.
- M6 → M10 : **coût de non-qualité** d'une NC (rebut, reprise, réparation, frais externes) valorisé puis transmis à la
  comptabilité par une écriture de reclassement au journal OD (noyau comptable `accounting_kernel`, comptes en
  paramètres provisoires).
"""

from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .ecarts import get_param_qualite
from .models import CoutNonQualite
from .services import CanManageQualite
from config.i18n import tr


# ----------------------------------------------------------------------------------------------------------------
# M5 → M6 : lot / coulée / certificat 3.1 jusqu'au joint
# ----------------------------------------------------------------------------------------------------------------
def _lots_consommes(ordre):
    from stocks.models import MouvementStock

    return set(
        MouvementStock.objects.filter(
            ordre=ordre, type_mouvement=MouvementStock.Type.CONSOMMATION, lot__isnull=False, executed=True
        ).values_list("lot_id", flat=True)
    )


def controler_lot_joint(attrs):
    """Règle provisoire de rattachement coulée ↔ lot : lot obligatoire dès que l'OF a consommé un lot, lot non
    bloqué, sorti du stock pour cet OF, coulée identique à celle du lot (reprise automatiquement)."""
    ordre, lot = attrs["ordre"], attrs.get("lot")
    lots_of = _lots_consommes(ordre)
    if lot is None:
        if lots_of and get_param_qualite("JOINT_LOT_OBLIGATOIRE"):
            raise serializers.ValidationError(
                {"lot": "Lot matière obligatoire : l'OF a consommé des lots tracés (coulée reprise du lot)."}
            )
        return attrs
    if lot.statut == lot.Statut.BLOQUE:
        raise serializers.ValidationError({"lot": tr("Lot %(lot_code)s en quarantaine : soudage interdit.") % {"lot_code": lot.code}})
    if get_param_qualite("JOINT_LOT_CONSOMME_OF") and lot.pk not in lots_of:
        raise serializers.ValidationError({"lot": tr("Lot %(lot_code)s non sorti du stock pour l'OF %(ordre_code)s.") % {"lot_code": lot.code, "ordre_code": ordre.code}})
    coulee = (attrs.get("numero_coulee") or "").strip()
    if coulee and lot.numero_coulee and coulee != lot.numero_coulee:
        raise serializers.ValidationError(
            {"numero_coulee": tr("Coulée %(coulee)s différente de celle du lot %(lot_code)s (%(lot_numero_coulee)s).") % {"coulee": coulee, "lot_code": lot.code, "lot_numero_coulee": lot.numero_coulee}}
        )
    attrs["numero_coulee"] = lot.numero_coulee or coulee
    return attrs


def certificats_lot(lot):
    if lot is None:
        return []
    return [
        {
            "id": str(c.pk), "code": c.code, "type": c.type,
            "type_label": "3.1 (MTC EN 10204)" if c.type == c.Type.MTC else c.get_type_display(),
            "numero_certificat": c.numero_certificat, "conforme": c.conforme,
            "valide": c.date_validation is not None, "document": str(c.document_id) if c.document_id else None,
        }
        for c in lot.certificats.all()
    ]


def tracabilite_joint(joint):
    """Chaîne joint → lot → certificats → entrée en stock (réception / BC) → sortie sur l'OF."""
    from stocks.models import MouvementStock

    lot = joint.lot
    mouvements = []
    if lot is not None:
        for m in MouvementStock.objects.filter(lot=lot).select_related("ordre", "source", "destination").order_by("date", "code"):
            if m.type_mouvement == MouvementStock.Type.CONSOMMATION and m.ordre_id != joint.ordre_id:
                continue  # sorties vers d'autres OF : hors de la chaîne de ce joint
            mouvements.append({
                "code": m.code, "date": m.date.isoformat(), "type": m.type_mouvement,
                "type_label": m.get_type_mouvement_display(), "quantite": str(m.quantite),
                "reference": m.document_reference, "ordre": m.ordre.code if m.ordre_id else None,
            })
    return {
        "joint": joint.code, "repere": joint.repere, "ordre": joint.ordre.code, "soudeur": joint.soudeur.display_name,
        "wps": joint.wps.code if joint.wps_id else None, "numero_coulee": joint.numero_coulee,
        "lot": None if lot is None else {
            "id": str(lot.pk), "code": lot.code, "numero_lot": lot.numero_lot, "numero_coulee": lot.numero_coulee,
            "article": lot.article.code, "statut": lot.statut, "date_reception": lot.date_reception.isoformat(),
        },
        "certificats": certificats_lot(lot),
        "mouvements": mouvements,
    }


class JointTracabiliteMixin:
    @action(detail=True, methods=["get"], url_path="tracabilite")
    def tracabilite(self, request, pk=None):
        return Response(tracabilite_joint(self.get_object()))

    @action(detail=False, methods=["get"], url_path="lots-consommes")
    def lots_consommes(self, request):
        """Lots sortis du stock sur des OF (`?ordre=` pour un OF) : choix du lot d'un joint, sans droit de lecture M5."""
        from stocks.models import MouvementStock

        qs = MouvementStock.objects.filter(
            type_mouvement=MouvementStock.Type.CONSOMMATION, lot__isnull=False, ordre__isnull=False, executed=True
        ).select_related("lot", "lot__article", "ordre")
        if ordre := request.query_params.get("ordre"):
            qs = qs.filter(ordre_id=ordre)
        vus, lignes = set(), []
        for m in qs.order_by("ordre__code", "lot__code"):
            if (m.ordre_id, m.lot_id) in vus:
                continue
            vus.add((m.ordre_id, m.lot_id))
            lignes.append({
                "id": str(m.lot_id), "code": m.lot.code, "numero_coulee": m.lot.numero_coulee,
                "article_code": m.lot.article.code, "ordre": str(m.ordre_id), "ordre_code": m.ordre.code,
            })
        return Response(lignes)


# ----------------------------------------------------------------------------------------------------------------
# M6 → M10 : coût de non-qualité
# ----------------------------------------------------------------------------------------------------------------
def _compte(code_param):
    from referentiels.models import Account

    code = str(int(get_param_qualite(code_param)))
    compte = Account.objects.filter(code=code).first()
    if compte is None:
        raise DjangoValidationError(tr("Compte %(code)s (%(code_param)s) absent du plan comptable : corriger le paramètre.") % {"code": code, "code_param": code_param})
    return compte


def cout_unitaire_lot(nc):
    """Coût unitaire par défaut de la matière rebutée : coût appliqué au dernier mouvement du lot de la NC."""
    from stocks.models import MouvementStock

    lot = nc.controle.lot if nc.controle_id and nc.controle.lot_id else (nc.joint.lot if nc.joint_id else None)
    if lot is None:
        return Decimal("0")
    m = MouvementStock.objects.filter(lot=lot, executed=True).exclude(cout_unitaire=0).order_by("-date", "-created_at").first()
    if m is not None:
        return Decimal(m.cout_unitaire).quantize(Decimal("0.01"))
    m = MouvementStock.objects.filter(lot=lot).exclude(prix_unitaire=0).order_by("-date").first()
    return m.prix_unitaire if m else Decimal("0")


def _analytique(nc):
    ordre = None
    if nc.joint_id:
        ordre = nc.joint.ordre
    elif nc.controle_id and nc.controle.ordre_id:
        ordre = nc.controle.ordre
    affaire = ordre.affaire if ordre is not None and ordre.affaire_id else (
        nc.controle.affaire if nc.controle_id and nc.controle.affaire_id else None
    )
    return affaire.assurer_compte_analytique() if affaire is not None else None


@transaction.atomic
def comptabiliser_cnq(cnq, user):
    """Écriture de reclassement au journal OD : Dr compte CNQ (analytique de l'affaire) / Cr matière et main-d'œuvre.
    Une seule écriture par coût ; l'écriture est comptabilisée (immuable) par le noyau comptable."""
    from accounting_kernel.models import AccountMove, AccountMoveLine, Journal
    from accounting_kernel.services import period_for_date, post_move

    cnq = CoutNonQualite.objects.select_for_update(of=("self",)).select_related("non_conformite").get(pk=cnq.pk)
    if cnq.statut != CoutNonQualite.Statut.SAISI:
        raise DjangoValidationError("Coût déjà comptabilisé.")
    if cnq.montant <= 0:
        raise DjangoValidationError("Coût nul : rien à comptabiliser.")
    journal = Journal.objects.filter(code="OD").first()
    if journal is None:
        raise DjangoValidationError("Journal OD absent : comptabilisation impossible.")
    charge = _compte("CNQ_COMPTE_CHARGE")
    label = f"Coût de non-qualité {cnq.code} — NC {cnq.non_conformite.code} ({cnq.get_nature_display().lower()})"[:200]
    move = AccountMove.objects.create(
        journal=journal, period=period_for_date(cnq.date), date=cnq.date, reference=cnq.code, label=label,
        source="M6", source_ref=str(cnq.pk), status=AccountMove.Status.DRAFT,
    )
    analytique = _analytique(cnq.non_conformite)
    AccountMoveLine.objects.create(
        move=move, account=charge, analytic_account=analytique, label=label, debit=cnq.montant, credit=0, order=1
    )
    ordre = 2
    matiere = (cnq.part_matiere).quantize(Decimal("1"))
    for code_param, montant in (("CNQ_COMPTE_MATIERE", matiere), ("CNQ_COMPTE_MO", cnq.montant - matiere)):
        if montant > 0:
            AccountMoveLine.objects.create(
                move=move, account=_compte(code_param), label=label, debit=0, credit=montant, order=ordre
            )
            ordre += 1
    cnq.ecriture = post_move(move, user=user)
    cnq.statut = CoutNonQualite.Statut.COMPTABILISE
    cnq.comptabilise_par = user
    cnq.comptabilise_le = timezone.now()
    cnq.save(update_fields=["ecriture", "statut", "comptabilise_par", "comptabilise_le", "updated_at"])
    return cnq


def voir_montants(user):
    from comptabilite.services import can_see_amount as voir_compta
    from stocks.services import can_see_amount as voir_stock

    return bool(user and user.is_authenticated and (voir_compta(user) or voir_stock(user)))


def peut_comptabiliser(user):
    from .services import can_comptabiliser_cnq

    return can_comptabiliser_cnq(user)


class CoutNonQualiteSerializer(serializers.ModelSerializer):
    nc_code = serializers.CharField(source="non_conformite.code", read_only=True)
    nature_label = serializers.CharField(source="get_nature_display", read_only=True)
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    ecriture_numero = serializers.CharField(source="ecriture.number", read_only=True, default=None)
    has_amount_access = serializers.SerializerMethodField()

    class Meta:
        model = CoutNonQualite
        fields = [
            "id", "code", "non_conformite", "nc_code", "nature", "nature_label", "date", "heures", "taux_horaire",
            "quantite", "cout_unitaire", "frais_externes", "montant", "description", "statut", "statut_label",
            "ecriture", "ecriture_numero", "comptabilise_le", "created_at", "has_amount_access",
        ]
        read_only_fields = ["code", "montant", "statut", "ecriture", "comptabilise_le", "created_at"]
        extra_kwargs = {"taux_horaire": {"required": False}, "cout_unitaire": {"required": False}}

    MONTANTS = ("taux_horaire", "cout_unitaire", "frais_externes", "montant")

    def get_has_amount_access(self, obj):
        return voir_montants(self.context["request"].user) if "request" in self.context else False

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not data["has_amount_access"]:
            for champ in self.MONTANTS:
                data[champ] = None
        return data

    def validate(self, attrs):
        for champ in ("heures", "quantite", "frais_externes", "taux_horaire", "cout_unitaire"):
            if attrs.get(champ) is not None and attrs[champ] < 0:
                raise serializers.ValidationError({champ: "Valeur positive attendue."})
        nc = attrs["non_conformite"]
        nature = attrs.get("nature", CoutNonQualite.Nature.REPRISE)
        if nature == CoutNonQualite.Nature.REBUT and not attrs.get("quantite"):
            raise serializers.ValidationError({"quantite": "Rebut : quantité rebutée requise."})
        if nature in (CoutNonQualite.Nature.REPRISE, CoutNonQualite.Nature.REPARATION) and not attrs.get("heures"):
            raise serializers.ValidationError({"heures": "Reprise / réparation : heures requises."})
        if nature == CoutNonQualite.Nature.AUTRE and not attrs.get("frais_externes"):
            raise serializers.ValidationError({"frais_externes": "Frais externes requis."})
        if not attrs.get("taux_horaire"):
            attrs["taux_horaire"] = get_param_qualite("CNQ_TAUX_HORAIRE")
        if attrs.get("quantite") and not attrs.get("cout_unitaire"):
            attrs["cout_unitaire"] = cout_unitaire_lot(nc)
        return attrs


class CoutNonQualiteViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                            viewsets.GenericViewSet):
    """Coûts de non-qualité : saisie par la qualité, comptabilisation par la finance (séparation des tâches)."""

    queryset = CoutNonQualite.objects.select_related("non_conformite", "ecriture").all()
    serializer_class = CoutNonQualiteSerializer
    search_fields = ("code", "non_conformite__code")
    permission_classes = [CanManageQualite]

    def get_permissions(self):
        if getattr(self, "action", None) == "comptabiliser":
            return []  # contrôle dans l'action : rôles comptables (et non qualité)
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        if nc := self.request.query_params.get("non_conformite"):
            qs = qs.filter(non_conformite_id=nc)
        if statut := self.request.query_params.get("statut"):
            qs = qs.filter(statut=statut)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"], url_path="comptabiliser")
    def comptabiliser(self, request, pk=None):
        if not peut_comptabiliser(request.user):
            return Response({"detail": "Comptabilisation réservée aux rôles comptables / finance."},
                            status=status.HTTP_403_FORBIDDEN)
        try:
            cnq = comptabiliser_cnq(self.get_object(), request.user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"detail": " ".join(exc.messages)})
        return Response(self.get_serializer(cnq).data)

    @action(detail=False, methods=["get"], url_path="synthese")
    def synthese(self, request):
        """Coût de non-qualité par nature et total (montants masqués hors cercle des montants)."""
        from django.db.models import Sum

        lignes = {n: Decimal("0") for n in CoutNonQualite.Nature.values}
        for row in self.get_queryset().values("nature").annotate(t=Sum("montant")):
            lignes[row["nature"]] = row["t"] or Decimal("0")
        voir = voir_montants(request.user)
        return Response({
            "par_nature": [
                {"nature": n, "label": CoutNonQualite.Nature(n).label, "montant": str(v) if voir else None}
                for n, v in lignes.items()
            ],
            "total": str(sum(lignes.values(), Decimal("0"))) if voir else None,
            "has_amount_access": voir,
        })
