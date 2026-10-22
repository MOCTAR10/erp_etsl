"""Écarts M12 — archivage légal : purge des documents arrivés au terme de leur rétention, après validation DG.

Un document archivé reste inaltérable et non supprimable (WORM applicatif : `DocumentViewSet.perform_destroy`) ;
sa seule sortie est cette purge : candidats calculés (fin de rétention dépassée), demande proposée par le
Secrétariat Général, puis validation (exécution) ou rejet par la Direction Générale. La demande conserve la trace
du document purgé (titre, empreinte, type, fin de rétention, validateur) ; la piste d'audit aussi.
"""

from datetime import timedelta

from django.db import transaction
from django.db.models import ProtectedError
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from users.models import User

from .audit import log_audit, request_ip
from .models import AuditLog, DemandePurge, Document, SignatureRequest
from config.i18n import tr

PROPOSE_ROLES = (User.Role.ADMIN, User.Role.SECRETAIRE_GENERAL, User.Role.PDG, User.Role.DGA)


def fin_retention(doc):
    """Fin de rétention (même règle que l'alerte GED : date du document, sinon d'archivage, + N années)."""
    if not doc.type_id or not doc.type.retention_years:
        return None
    base = doc.document_date or (doc.archived_at or doc.created_at).date()
    return base + timedelta(days=365 * doc.type.retention_years)


def candidats_purge():
    today = timezone.localdate()
    en_cours = set(
        DemandePurge.objects.filter(statut=DemandePurge.Statut.PROPOSEE).values_list("document_id", flat=True)
    )
    out = []
    qs = Document.objects.filter(status=Document.Status.ARCHIVED, type__retention_years__isnull=False)
    for doc in qs.select_related("type"):
        fin = fin_retention(doc)
        if fin and fin < today and doc.pk not in en_cours:
            out.append((doc, fin))
    return out


def _peut_proposer(user):
    from juridique.services import can_validate_dg

    return bool(user and user.is_authenticated) and (
        user.is_staff or user.is_superuser or user.role in PROPOSE_ROLES or can_validate_dg(user)
    )


class CanProposerPurge(BasePermission):
    message = "Purge réservée au Secrétariat Général et à la Direction Générale."

    def has_permission(self, request, view):
        return _peut_proposer(getattr(request, "user", None))


class DemandePurgeSerializer(serializers.ModelSerializer):
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)

    class Meta:
        model = DemandePurge
        fields = [
            "id", "document", "document_title", "document_sha256", "type_label", "fin_retention", "statut",
            "statut_label", "motif", "propose_par", "valide_par", "traite_le", "created_at",
        ]
        read_only_fields = [
            "document_title", "document_sha256", "type_label", "fin_retention", "statut", "propose_par",
            "valide_par", "traite_le", "created_at",
        ]

    def validate(self, attrs):
        doc = attrs.get("document")
        if doc is None:
            raise serializers.ValidationError({"document": "Document obligatoire."})
        fin = fin_retention(doc)
        if doc.status != Document.Status.ARCHIVED or fin is None:
            raise serializers.ValidationError({"document": "Seul un document archivé soumis à rétention est purgeable."})
        if fin >= timezone.localdate():
            raise serializers.ValidationError({"document": tr("Rétention en cours jusqu'au %(fin)s.") % {"fin": format(fin, '%d/%m/%Y')}})
        if DemandePurge.objects.filter(document=doc, statut=DemandePurge.Statut.PROPOSEE).exists():
            raise serializers.ValidationError({"document": "Une demande de purge est déjà en cours."})
        attrs.update(
            document_title=doc.title, document_sha256=doc.sha256, type_label=doc.type.label, fin_retention=fin
        )
        return attrs


class DemandePurgeViewSet(viewsets.ModelViewSet):
    serializer_class = DemandePurgeSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_permissions(self):
        from juridique.services import CanValidateDg

        if self.action in ("valider", "rejeter"):
            return [CanValidateDg()]
        return [CanProposerPurge()]

    def get_queryset(self):
        qs = DemandePurge.objects.all()
        if st := self.request.query_params.get("statut"):
            qs = qs.filter(statut=st)
        return qs

    def perform_create(self, serializer):
        serializer.save(propose_par=self.request.user)

    @action(detail=False, methods=["get"])
    def candidats(self, request):
        return Response([
            {
                "id": str(doc.pk), "title": doc.title, "type_label": doc.type.label,
                "retention_years": doc.type.retention_years, "fin_retention": fin, "sha256": doc.sha256,
            }
            for doc, fin in candidats_purge()[:200]
        ])

    def _verrou(self):
        obj = self.get_object()
        return DemandePurge.objects.select_for_update(of=("self",)).get(pk=obj.pk)

    @action(detail=True, methods=["post"])
    def rejeter(self, request, pk=None):
        with transaction.atomic():
            demande = self._verrou()
            if demande.statut != DemandePurge.Statut.PROPOSEE:
                raise DRFValidationError("Demande déjà traitée.")
            demande.statut = DemandePurge.Statut.REJETEE
            demande.valide_par = request.user
            demande.traite_le = timezone.now()
            motif = (request.data.get("motif") or "").strip()
            if motif:
                demande.motif = motif[:255]
            demande.save(update_fields=["statut", "valide_par", "traite_le", "motif"])
        return Response(self.get_serializer(demande).data)

    @action(detail=True, methods=["post"])
    def valider(self, request, pk=None):
        """Validation DG = exécution : fichiers, versions, signatures et liens supprimés ; la trace demeure."""
        with transaction.atomic():
            demande = self._verrou()
            if demande.statut != DemandePurge.Statut.PROPOSEE:
                raise DRFValidationError("Demande déjà traitée.")
            doc = demande.document
            if doc is None:
                raise DRFValidationError("Document introuvable.")
            # Revérification avec la durée EN VIGUEUR (la rétention du type a pu être allongée depuis la proposition,
            # ex. contrats 5 → 10 ans) : la demande n'est plus purgeable → rejet tracé, document conservé.
            fin = fin_retention(doc)
            if doc.status != Document.Status.ARCHIVED or fin is None or fin >= timezone.localdate():
                ans = doc.type.retention_years if doc.type_id else None
                if doc.status != Document.Status.ARCHIVED or fin is None:
                    detail = "Document plus soumis à rétention archivée : purge refusée."
                else:
                    detail = (f"Rétention en vigueur ({ans} ans) : document conservé jusqu'au {fin:%d/%m/%Y}, "
                              "purge refusée.")
                demande.statut = DemandePurge.Statut.REJETEE
                demande.valide_par = request.user
                demande.traite_le = timezone.now()
                demande.motif = detail[:255]
                champs = ["statut", "valide_par", "traite_le", "motif"]
                if fin is not None:
                    demande.fin_retention = fin
                    champs.append("fin_retention")
                demande.save(update_fields=champs)
                log_audit(request.user, AuditLog.Action.UPDATE, "document", doc.pk,
                          {"purge": "refusee", "motif": detail}, request_ip(request))
                return Response({"detail": detail, "demande": self.get_serializer(demande).data},
                                status=status.HTTP_400_BAD_REQUEST)
            if demande.fin_retention != fin:  # trace alignée sur la durée en vigueur
                demande.fin_retention = fin
                demande.save(update_fields=["fin_retention"])
            fichiers = [(v.file.storage, v.file.name) for v in doc.versions.all() if v.file]
            doc_id, titre = doc.pk, doc.title
            try:
                with transaction.atomic():
                    SignatureRequest.objects.filter(version__document=doc).delete()
                    Document.objects.filter(pk=doc.pk).update(current_version=None)
                    doc.delete()
            except ProtectedError as exc:
                refs = sorted({o._meta.verbose_name for o in exc.protected_objects})
                raise DRFValidationError(
                    tr("Document encore référencé (%(liste)s) : purge impossible.") % {"liste": ", ".join(str(r) for r in refs)}
                )
            demande.document = None
            demande.statut = DemandePurge.Statut.EXECUTEE
            demande.valide_par = request.user
            demande.traite_le = timezone.now()
            demande.save(update_fields=["document", "statut", "valide_par", "traite_le"])
            log_audit(
                request.user, AuditLog.Action.DELETE, "document", doc_id,
                {"purge": True, "title": titre, "sha256": demande.document_sha256,
                 "fin_retention": demande.fin_retention.isoformat()},
                request_ip(request),
            )

            def effacer():
                for storage, name in fichiers:
                    try:
                        storage.delete(name)
                    except Exception:  # noqa: BLE001 — fichier déjà absent
                        pass

            transaction.on_commit(effacer)
        return Response(self.get_serializer(demande).data)
