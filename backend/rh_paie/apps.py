from django.apps import AppConfig


class RhPaieConfig(AppConfig):
    name = "rh_paie"
    verbose_name = "M9 — RH & Paie"

    def ready(self):
        from . import signals_m9c  # noqa: F401  (qualifications soudeur M6 -> dossier RH)