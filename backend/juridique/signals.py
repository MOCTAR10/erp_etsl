"""Écarts M12 — liage GED automatique, archivage automatique à la transition, notification J-60.

* Liage automatique : tout objet métier liable (liste blanche `services.OBJETS_LIEABLES`) qui porte un document GED
  (clé étrangère vers `documents.Document`) est lié à ce document dès son enregistrement — la recherche juridique
  le retrouve sans saisie manuelle.
* Archivage automatique : à l'entrée dans un statut déclencheur (paramètre provisoire `archivage_auto`), une fiche
  PDF de l'objet est déposée en GED (statut archivé, empreinte SHA-256) et liée à l'objet.
* Notification : après la tâche quotidienne d'échéances existante, les échéances juridiques des paliers paramétrés
  (J-60 compris) sont notifiées — sans nouvelle tâche planifiée.

Les traitements s'exécutent après validation de la transaction (`on_commit`) et n'interrompent jamais
l'enregistrement de l'objet métier (erreur journalisée).
"""

import hashlib
import io
import logging

from django.apps import apps
from django.db import transaction
from django.db.models.signals import post_save
from django.utils import timezone

logger = logging.getLogger(__name__)


def _document_fields(modele):
    return [
        f for f in modele._meta.concrete_fields
        if f.is_relation and f.related_model is not None and f.related_model._meta.label_lower == "documents.document"
    ]


def lier_documents(objet, objet_type, user=None):
    """Crée les liens GED manquants pour les documents portés par `objet` ; renvoie le nombre de liens créés."""
    from .models import LienDocument
    from .services import OBJETS_LIEABLES

    crees = 0
    for field in _document_fields(type(objet)):
        doc_id = getattr(objet, field.attname)
        if not doc_id:
            continue
        _, cree = LienDocument.objects.get_or_create(
            document_id=doc_id, objet_type=objet_type, objet_id=str(objet.pk),
            defaults={
                "objet_label": str(objet)[:255], "module": OBJETS_LIEABLES[objet_type],
                "note": "Liage automatique", "created_by": user,
            },
        )
        crees += int(cree)
    return crees


def _fiche_pdf(objet):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    c.setFont("Helvetica-Bold", 13)
    c.drawString(40, y, f"Fiche d'archivage — {objet._meta.verbose_name}")
    y -= 22
    c.setFont("Helvetica", 9)
    c.drawString(40, y, f"Archivée automatiquement le {timezone.localtime():%d/%m/%Y %H:%M}")
    y -= 20
    for field in objet._meta.concrete_fields:
        if field.name in ("id",):
            continue
        valeur = getattr(objet, field.name, "")
        if field.choices:
            valeur = getattr(objet, f"get_{field.name}_display")()
        texte = f"{field.verbose_name} : {'' if valeur is None else valeur}"[:120]
        c.drawString(40, y, texte)
        y -= 13
        if y < 50:
            c.showPage()
            c.setFont("Helvetica", 9)
            y = 800
    c.showPage()
    c.save()
    return buf.getvalue()


def _libelle_statut(objet, statut):
    """Libellé lisible du statut (« Réceptionné ») d'après les choix du modèle ; le code brut à défaut."""
    champs = sorted(
        (f for f in objet._meta.concrete_fields if f.choices),
        key=lambda f: f.name not in ("statut", "status"),  # le champ de statut d'abord
    )
    for field in champs:
        libelles = dict(field.flatchoices)
        if statut in libelles:
            return str(libelles[statut])
    return statut


def archiver_objet(objet, objet_type, statut, type_code=None, user=None):
    """Dépose en GED une fiche PDF de l'objet pour ce statut (idempotent) ; renvoie le document ou None."""
    from django.core.files.base import ContentFile

    from documents.models import Document, DocumentType, Version

    from .models import LienDocument
    from .services import OBJETS_LIEABLES

    note = f"Archivage automatique : {statut}"
    if LienDocument.objects.filter(objet_type=objet_type, objet_id=str(objet.pk), note=note).exists():
        return None
    contenu = _fiche_pdf(objet)
    sha = hashlib.sha256(contenu).hexdigest()
    now = timezone.now()
    doc = Document.objects.create(
        title=f"{objet} — archivage ({_libelle_statut(objet, statut)})"[:255],
        status=Document.Status.ARCHIVED,
        archived_at=now,
        document_date=timezone.localdate(),
        reference=str(getattr(objet, "code", "") or "")[:200],
        type=DocumentType.objects.filter(code=type_code).first() if type_code else None,
        created_by=user,
    )
    nom = f"archivage_{objet_type.replace('.', '_')}_{getattr(objet, 'code', objet.pk)}_{statut}.pdf"
    version = Version.objects.create(
        document=doc, number=1, file=ContentFile(contenu, name=nom), sha256=sha, size=len(contenu),
        original_filename=nom, note=note, created_by=user,
    )
    doc.current_version = version
    doc.sha256 = sha
    doc.save(update_fields=["current_version", "sha256"])
    LienDocument.objects.create(
        document=doc, objet_type=objet_type, objet_id=str(objet.pk), objet_label=str(objet)[:255],
        module=OBJETS_LIEABLES.get(objet_type, "M12")[:4], note=note, created_by=user,
    )
    return doc


def _statut(objet):
    return getattr(objet, "statut", None) or getattr(objet, "status", None)


def traiter_objet(objet_type, pk):
    """Liage + archivage automatique d'un objet (appelé après commit)."""
    from .ecarts import parametre

    modele = apps.get_model(*objet_type.split("."))
    objet = modele.objects.filter(pk=pk).first()
    if objet is None:
        return
    lier_documents(objet, objet_type)
    regle = (parametre("archivage_auto") or {}).get(objet_type)
    if regle and _statut(objet) in (regle.get("statuts") or []):
        archiver_objet(objet, objet_type, _statut(objet), regle.get("type_document"))


def _on_save(objet_type):
    def handler(sender, instance, raw=False, **kwargs):
        if raw:
            return
        pk = instance.pk

        def run():
            try:
                traiter_objet(objet_type, pk)
            except Exception:  # noqa: BLE001 — ne jamais casser l'enregistrement métier
                logger.exception("Écarts M12 : liage / archivage automatique en échec (%s %s)", objet_type, pk)

        transaction.on_commit(run)

    return handler


_HANDLERS = []


def connecter():
    from .ecarts import PARAMETRES_DEFAUT
    from .services import OBJETS_LIEABLES

    types = set(OBJETS_LIEABLES) | set(PARAMETRES_DEFAUT["archivage_auto"][1])
    for objet_type in sorted(types):
        try:
            modele = apps.get_model(*objet_type.split("."))
        except LookupError:
            continue
        if objet_type not in PARAMETRES_DEFAUT["archivage_auto"][1] and not _document_fields(modele):
            continue
        handler = _on_save(objet_type)
        _HANDLERS.append(handler)
        post_save.connect(handler, sender=modele, dispatch_uid=f"m12-ecarts-{objet_type}")

    try:
        from celery.signals import task_postrun
    except ImportError:  # pragma: no cover
        return

    def apres_tache(sender=None, **kwargs):
        if getattr(sender, "name", "") != "analytics.tasks.notifier_echeances":
            return
        try:
            from .ecarts import notifier_echeances_juridiques

            notifier_echeances_juridiques()
        except Exception:  # noqa: BLE001
            logger.exception("Écarts M12 : notification des échéances juridiques en échec")

    _HANDLERS.append(apres_tache)
    task_postrun.connect(apres_tache, weak=False, dispatch_uid="m12-ecarts-notification")
