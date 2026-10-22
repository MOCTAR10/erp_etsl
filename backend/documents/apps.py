from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'documents'

    def ready(self):
        # Signaux : indexation full-text automatique (RF-23/26/27).
        from . import signals  # noqa: F401
        # Piste d'audit générique avant / après des objets métier (écarts transverses EX-G-06).
        from .audit_generique import connecter

        connecter()
