"""Notifications (RF-34/35) — enregistrement + envoi email."""

from django.conf import settings
from django.core.mail import send_mail

from .models import Notification


def courriel_actif():
    """Paramètre transverse provisoire NOTIF_EMAIL_ACTIF (1 = courriel pour chaque notification interne)."""
    from users.parametres import valeur_transverse

    return valeur_transverse("NOTIF_EMAIL_ACTIF") != 0


def envoyer_courriel(notification):
    """Courriel d'une notification interne (RF-34, EX-G-05) ; jamais bloquant."""
    user = notification.user
    if not (user.email and user.is_active and courriel_actif()):
        return False
    try:
        return bool(send_mail(
            subject=f"[ETSL ERP] {notification.subject}",
            message=notification.message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        ))
    except Exception:
        # L'email ne doit jamais faire échouer le reste du traitement.
        return False


def _courriel_a_la_creation(sender, instance, created, raw=False, **kwargs):
    """Toute notification créée par `Notification.objects.create` (tâches planifiées, modules) part aussi par
    courriel ; `notify` envoie lui-même (drapeau `_courriel_envoye`)."""
    if created and not raw and not getattr(instance, "_courriel_envoye", False):
        envoyer_courriel(instance)


def notify(user, subject, message, task=None, kind="info", sms=False):
    """Crée une notification en base (RF-37) et envoie un email (RF-34) ; `sms=True` : aussi par SMS si configuré."""
    notification = Notification(user=user, subject=subject, message=message, task=task, kind=kind)
    notification._courriel_envoye = True
    notification.save()
    envoyer_courriel(notification)
    if sms:
        from django.db import transaction

        from .sms import envoyer_sms

        transaction.on_commit(lambda: envoyer_sms(user, f"{subject} : {message}"))
    return notification


def remind_assignee(task):
    """Relance de l'assigné (RF-35, RF-34)."""
    subject = f"Tâche en retard : {task.step.name} — {task.document.title}"
    message = (
        f"Le document « {task.document.title} » (étape {task.step.name}, circuit "
        f"{task.circuit.label}) devait être traité avant le {task.due_date:%d/%m/%Y}.\n"
        f"Merci de traiter ou déléguer cette tâche."
    )
    return notify(task.assigned_to, subject, message, task=task, kind="reminder")


def escalate_task(task, admin):
    """Escalade N+1 vers l'administration (RF-35)."""
    subject = f"Escalade : {task.step.name} en retard — {task.document.title}"
    message = (
        f"La tâche « {task.step.name} » du document « {task.document.title} » "
        f"(assignée à {task.assigned_to.email if task.assigned_to else '—'}) "
        f"est en retard depuis le {task.due_date:%d/%m/%Y}."
    )
    return notify(admin, subject, message, task=task, kind="escalation")
