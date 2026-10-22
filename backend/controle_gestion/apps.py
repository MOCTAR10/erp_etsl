from django.apps import AppConfig


class ControleGestionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "controle_gestion"
    verbose_name = "Contrôle de gestion"

    def ready(self):
        from . import suivi  # noqa: F401 — abonné outbox `operations.marge_terminaison` (M3 → M11)