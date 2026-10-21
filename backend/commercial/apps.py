from django.apps import AppConfig


class CommercialConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "commercial"
    verbose_name = "Commercial (CRM / CLM)"

    def ready(self):
        from celery.signals import task_success

        def _relances_m1(sender=None, **kwargs):
            if getattr(sender, "name", "") == "analytics.tasks.notifier_echeances":
                from .ecarts_m1 import relances_commerciales

                relances_commerciales()

        task_success.connect(_relances_m1, weak=False, dispatch_uid="commercial_relances_m1")