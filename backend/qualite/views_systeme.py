"""Écarts M6-C : système de management de la qualité (CDC M6.2) — processus, organisation, liste maîtresse des documents,
audits internes / externes / fournisseurs, compétences, revue de direction."""

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    AuditQualite, ConstatAuditQualite, DocumentQualite, ProcessusQualite, ResponsabiliteQualite, RevueDirectionQualite,
)
from .serializers import (
    AuditQualiteSerializer, ConstatAuditQualiteSerializer, DocumentQualiteSerializer, ProcessusQualiteSerializer,
    ResponsabiliteQualiteSerializer, RevueDirectionQualiteSerializer,
)
from .services import CanManageQualite, can_validate_pv
from .systeme import (
    approuver_document, bilan_pdf, bilan_qualite, cloturer_audit, competences, engage_direction, nc_constat,
    rapport_audit_pdf, reviser_document,
)
from config.i18n import en_francais, tr


def _pdf_response(contenu, nom):
    from hse.views import _pdf_response as reponse

    return reponse(contenu, nom)


def _refus(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({"detail": message}, status=code)


class ProcessusQualiteViewSet(viewsets.ModelViewSet):
    queryset = ProcessusQualite.objects.select_related("pilote").all()
    serializer_class = ProcessusQualiteSerializer
    permission_classes = [CanManageQualite]
    search_fields = ("code", "libelle")
    http_method_names = ["get", "post", "patch", "head", "options"]

    @action(detail=True, methods=["post"], url_path="mesurer")
    def mesurer(self, request, pk=None):
        """Enregistre la dernière mesure de l'indicateur du processus (pilotage, ISO 9001 §9.1)."""
        processus = self.get_object()
        try:
            processus.valeur = serializers.DecimalField(max_digits=12, decimal_places=2).run_validation(request.data.get("valeur"))
            processus.date_mesure = serializers.DateField().run_validation(request.data.get("date_mesure") or timezone.localdate())
        except serializers.ValidationError as exc:
            return Response({"detail": exc.detail}, status=status.HTTP_400_BAD_REQUEST)
        processus.save(update_fields=["valeur", "date_mesure"])
        return Response(self.get_serializer(processus).data)


class ResponsabiliteQualiteViewSet(viewsets.ModelViewSet):
    queryset = ResponsabiliteQualite.objects.select_related("titulaire", "suppleant", "processus").all()
    serializer_class = ResponsabiliteQualiteSerializer
    permission_classes = [CanManageQualite]
    search_fields = ("fonction",)

    @action(detail=False, methods=["get"], url_path="utilisateurs")
    def utilisateurs(self, request):
        """Comptes actifs (id, nom, rôle) pour désigner titulaires, suppléants et pilotes de processus."""
        from users.models import User

        return Response([
            {"id": str(u.pk), "nom": u.get_full_name() or u.email, "role": u.get_role_display()}
            for u in User.objects.filter(is_active=True).order_by("last_name", "first_name", "email")
        ])


class DocumentQualiteViewSet(viewsets.ModelViewSet):
    """Liste maîtresse : un brouillon se modifie ; une version approuvée est scellée (révision = nouvelle version)."""

    queryset = DocumentQualite.objects.select_related("processus", "affaire", "approuve_par", "redige_par").all()
    serializer_class = DocumentQualiteSerializer
    permission_classes = [CanManageQualite]
    search_fields = ("reference", "titre")
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        if type_doc := self.request.query_params.get("type"):
            qs = qs.filter(type_doc=type_doc)
        if self.request.query_params.get("en_vigueur"):
            qs = qs.filter(statut=DocumentQualite.Statut.APPROUVE)
        return qs

    def perform_create(self, serializer):
        serializer.save(redige_par=self.request.user)

    def perform_update(self, serializer):
        if serializer.instance.statut != DocumentQualite.Statut.BROUILLON:
            raise serializers.ValidationError({"detail": "Version approuvée ou obsolète : scellée, créer une révision."})
        serializer.save()

    @action(detail=True, methods=["post"], url_path="fichier")
    def fichier(self, request, pk=None):
        """Joint le fichier source (PDF, Word, Excel) tant que la version est en brouillon."""
        doc = self.get_object()
        if doc.statut != DocumentQualite.Statut.BROUILLON:
            return _refus("Version approuvée : scellée.")
        fichier = request.FILES.get("fichier")
        if fichier is None or not fichier.name.lower().endswith((".pdf", ".docx", ".xlsx", ".doc", ".xls")):
            return Response({"fichier": "Fichier attendu : PDF, Word ou Excel."}, status=status.HTTP_400_BAD_REQUEST)
        doc.fichier = fichier
        doc.save(update_fields=["fichier"])
        return Response(self.get_serializer(doc).data)

    @action(detail=True, methods=["post"], url_path="approuver")
    @transaction.atomic
    def approuver(self, request, pk=None):
        doc = DocumentQualite.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if doc.statut != DocumentQualite.Statut.BROUILLON:
            return _refus("Seul un brouillon s'approuve.")
        if doc.type_doc in (DocumentQualite.TypeDoc.POLITIQUE, DocumentQualite.TypeDoc.MANUEL):
            if not engage_direction(request.user):
                return _refus("La politique et le manuel qualité s'approuvent par la direction générale.", status.HTTP_403_FORBIDDEN)
        elif not can_validate_pv(request.user):
            return _refus("Approbation réservée au QA/QC et à la hiérarchie.", status.HTTP_403_FORBIDDEN)
        return Response(self.get_serializer(approuver_document(doc, request.user)).data)

    @action(detail=True, methods=["post"], url_path="reviser")
    @transaction.atomic
    def reviser(self, request, pk=None):
        doc = DocumentQualite.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if doc.statut != DocumentQualite.Statut.APPROUVE:
            return _refus("Seule la version en vigueur se révise.")
        if DocumentQualite.objects.filter(reference=doc.reference, statut=DocumentQualite.Statut.BROUILLON).exists():
            return _refus("Une révision est déjà en cours pour ce document.")
        motif = str(request.data.get("motif", "")).strip()
        if not motif:
            return Response({"motif": "Indiquer l'objet de la révision."}, status=status.HTTP_400_BAD_REQUEST)
        nouvelle = reviser_document(doc, request.user, motif)
        return Response(self.get_serializer(nouvelle).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="obsolete")
    @transaction.atomic
    def obsolete(self, request, pk=None):
        doc = DocumentQualite.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if not can_validate_pv(request.user):
            return _refus("Réservé au QA/QC et à la hiérarchie.", status.HTTP_403_FORBIDDEN)
        if doc.statut == DocumentQualite.Statut.OBSOLETE:
            return _refus("Document déjà obsolète.")
        doc.statut = DocumentQualite.Statut.OBSOLETE
        doc.save(update_fields=["statut"])
        return Response(self.get_serializer(doc).data)


class AuditQualiteViewSet(viewsets.ModelViewSet):
    queryset = AuditQualite.objects.select_related("processus", "fournisseur").prefetch_related("constats__nc").all()
    serializer_class = AuditQualiteSerializer
    permission_classes = [CanManageQualite]
    search_fields = ("code", "perimetre")
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        if type_audit := self.request.query_params.get("type"):
            qs = qs.filter(type_audit=type_audit)
        return qs

    def perform_update(self, serializer):
        if serializer.instance.statut == AuditQualite.Statut.CLOTURE:
            raise serializers.ValidationError({"detail": "Audit clôturé : scellé."})
        serializer.save()

    @action(detail=True, methods=["post"], url_path="realiser")
    @transaction.atomic
    def realiser(self, request, pk=None):
        audit = AuditQualite.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if audit.statut != AuditQualite.Statut.PLANIFIE:
            return _refus("Seul un audit planifié peut être réalisé.")
        try:
            audit.score = serializers.IntegerField(min_value=0, max_value=100).run_validation(request.data.get("score"))
            audit.date_realisation = serializers.DateField().run_validation(request.data.get("date_realisation") or timezone.localdate())
        except serializers.ValidationError as exc:
            return Response({"detail": exc.detail}, status=status.HTTP_400_BAD_REQUEST)
        audit.conclusion = str(request.data.get("conclusion", audit.conclusion))[:4000]
        audit.statut = AuditQualite.Statut.REALISE
        audit.realise_par = request.user
        audit.save()
        return Response(self.get_serializer(audit).data)

    @action(detail=True, methods=["post"], url_path="cloturer")
    @transaction.atomic
    def cloturer(self, request, pk=None):
        audit = AuditQualite.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if audit.statut != AuditQualite.Statut.REALISE:
            return _refus("Seul un audit réalisé peut être clôturé.")
        if n := audit.nc_ouvertes.count():
            return _refus(tr("%(n)s NC d'audit non clôturée(s) : clôture impossible.") % {"n": n})
        return Response(self.get_serializer(cloturer_audit(audit, request.user)).data)

    @action(detail=True, methods=["get"], url_path="rapport")
    def rapport(self, request, pk=None):
        audit = self.get_object()
        return _pdf_response(rapport_audit_pdf(audit), f"rapport-{audit.code}.pdf")


class ConstatAuditQualiteViewSet(viewsets.ModelViewSet):
    """Constats ; un écart ouvre une NC (source audit). Constats figés une fois l'audit clôturé."""

    queryset = ConstatAuditQualite.objects.select_related("audit", "nc").all()
    serializer_class = ConstatAuditQualiteSerializer
    permission_classes = [CanManageQualite]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        if audit := self.request.query_params.get("audit"):
            qs = qs.filter(audit_id=audit)
        return qs

    @transaction.atomic
    def perform_create(self, serializer):
        constat = serializer.save()
        nc_constat(constat, self.request.user)


class RevueDirectionQualiteViewSet(viewsets.ModelViewSet):
    """Revue de direction qualité (ISO 9001 §9.3) : bilan calculé, validée par la direction, scellée et archivée 10 ans."""

    queryset = RevueDirectionQualite.objects.select_related("validee_par").all()
    serializer_class = RevueDirectionQualiteSerializer
    permission_classes = [CanManageQualite]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def perform_create(self, serializer):
        serializer.save(bilan=bilan_qualite(serializer.validated_data["annee"]))

    def perform_update(self, serializer):
        if serializer.instance.statut == RevueDirectionQualite.Statut.VALIDEE:
            raise serializers.ValidationError({"detail": "Revue validée : scellée, non modifiable."})
        serializer.save()

    @action(detail=False, methods=["get"], url_path="bilan")
    def bilan(self, request):
        try:
            annee = serializers.IntegerField(min_value=2000, max_value=2100).run_validation(
                request.query_params.get("annee") or timezone.localdate().year)
        except serializers.ValidationError as exc:
            return Response({"detail": exc.detail}, status=status.HTTP_400_BAD_REQUEST)
        bilan = bilan_qualite(annee)
        if request.query_params.get("export") == "pdf":
            return _pdf_response(bilan_pdf(bilan, f"Bilan qualité {annee}"), f"bilan-qualite-{annee}.pdf")
        return Response(bilan)

    @action(detail=True, methods=["post"], url_path="actualiser")
    def actualiser(self, request, pk=None):
        revue = self.get_object()
        if revue.statut == RevueDirectionQualite.Statut.VALIDEE:
            return _refus("Revue validée : bilan figé.")
        revue.bilan = bilan_qualite(revue.annee)
        revue.save(update_fields=["bilan"])
        return Response(self.get_serializer(revue).data)

    @action(detail=True, methods=["post"], url_path="valider")
    @transaction.atomic
    def valider(self, request, pk=None):
        from .systeme import archiver

        revue = RevueDirectionQualite.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if not engage_direction(request.user):
            return _refus("La revue de direction se valide par la direction générale.", status.HTTP_403_FORBIDDEN)
        if revue.statut == RevueDirectionQualite.Statut.VALIDEE:
            return _refus("Revue déjà validée.")
        manquants = [c for c in ("participants", "conclusions", "decisions") if not getattr(revue, c).strip()]
        if manquants:
            return Response({c: "Obligatoire pour valider la revue." for c in manquants}, status=status.HTTP_400_BAD_REQUEST)
        revue.statut = RevueDirectionQualite.Statut.VALIDEE
        revue.validee_par, revue.validee_le = request.user, timezone.now()
        titre = f"Revue de direction qualité {revue.annee}"
        revue.document = archiver(en_francais(bilan_pdf, revue.bilan, titre, revue), f"{revue.code}.pdf", titre, revue.code,
                                  "qualite.revuedirectionqualite", revue.pk, request.user, ("revue de direction", "ISO 9001"),
                                  "Revue de direction qualité validée")
        revue.save(update_fields=["statut", "validee_par", "validee_le", "document"])
        return Response(self.get_serializer(revue).data)

    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request, pk=None):
        revue = self.get_object()
        return _pdf_response(bilan_pdf(revue.bilan, f"Revue de direction qualité {revue.annee}", revue), f"{revue.code}.pdf")


class CompetencesQualiteViewSet(viewsets.ViewSet):
    """Matrice des compétences (ISO 9001 §7.2) : qualifications soudage M6 + habilitations RH M9, validité."""

    permission_classes = [CanManageQualite]

    def list(self, request):
        return Response(competences())
