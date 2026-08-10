from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'documents'

    def ready(self):
        # Signaux : indexation full-text automatique (RF-23/26/27).
        from . import signals  # noqa: F401
