from django.apps import AppConfig


class WorkflowConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'workflow'

    def ready(self):
        from django.db.models.signals import post_save

        from .models import Notification
        from .notifications import _courriel_a_la_creation

        post_save.connect(_courriel_a_la_creation, sender=Notification, dispatch_uid="etls_notification_courriel")
