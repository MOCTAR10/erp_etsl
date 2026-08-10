"""Signaux Django — indexation full-text automatique (RF-23/26/27)."""

from django.contrib.postgres.search import SearchVector
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Document


def rebuild_search_vector(document):
    """Reconstruit le tsvector du document (métadonnées + OCR invisible)."""
    vector = (
        SearchVector("title", weight="A", config="french")
        + SearchVector("counterparty", "project", "reference", weight="B", config="french")
        + SearchVector("extracted_text", weight="D", config="french")
    )
    Document.objects.filter(pk=document.pk).update(search_vector=vector)


@receiver(post_save, sender=Document)
def on_document_save(sender, instance, **kwargs):
    rebuild_search_vector(instance)
