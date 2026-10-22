from django.apps import AppConfig


class ReferentielsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'referentiels'

    def ready(self):
        from .signals import brancher

        brancher()
