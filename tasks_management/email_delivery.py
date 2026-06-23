"""
Envoi d'emails tâches : hors chemin critique (Celery ou thread daemon).
"""
import logging
import threading

from django.conf import settings
from django.core.mail import send_mail

from tasks_management.apps import TasksManagementConfig

logger = logging.getLogger(__name__)


def is_task_email_enabled():
    flag = getattr(TasksManagementConfig, "send_email_on_task_create", True)
    return flag not in (False, "false", "False", "0", 0)


def get_user_email(user):
    for attr in ("email", "email_id"):
        if hasattr(user, attr):
            value = getattr(user, attr)
            if value and isinstance(value, str) and value.strip() and "@" in value:
                return value.strip()
    return None


def get_user_display_name(user):
    if hasattr(user, "i_user") and user.i_user:
        i_user = user.i_user
        parts = []
        if getattr(i_user, "other_names", None):
            parts.append(i_user.other_names)
        if getattr(i_user, "last_name", None):
            parts.append(i_user.last_name)
        if parts:
            return " ".join(parts)
    return getattr(user, "login_name", None) or str(user)


def default_from_email():
    default_from = getattr(
        settings,
        "DEFAULT_FROM_EMAIL",
        getattr(settings, "EMAIL_HOST_USER", "noreply@openimis.local"),
    )
    return default_from or "noreply@openimis.local"


def send_email_messages_sync(messages):
    """Envoie une liste de mails ; les erreurs sont journalisées, jamais propagées."""
    if not messages:
        return 0
    sent = 0
    from_email = default_from_email()
    for item in messages:
        recipients = item.get("recipient_list") or []
        if not recipients:
            continue
        try:
            send_mail(
                subject=item["subject"],
                message=item["message"],
                from_email=item.get("from_email") or from_email,
                recipient_list=recipients,
                fail_silently=False,
            )
            sent += 1
        except Exception as exc:
            logger.exception(
                "Task email not sent (subject=%r, recipients=%s): %s",
                item.get("subject"),
                recipients,
                exc,
            )
    return sent


def _dispatch_in_background_thread(messages):
    thread = threading.Thread(
        target=send_email_messages_sync,
        args=(messages,),
        name="task-email-delivery",
        daemon=True,
    )
    thread.start()


def schedule_task_emails(messages):
    """
    Planifie l'envoi sans bloquer le signal / la mutation GraphQL.
    Celery si broker disponible (et pas en mode eager), sinon thread daemon.
    """
    if not messages or not is_task_email_enabled():
        return

    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        _dispatch_in_background_thread(messages)
        logger.debug("Scheduled %d task email(s) via background thread (CELERY_TASK_ALWAYS_EAGER).", len(messages))
        return

    try:
        from tasks_management.tasks import send_task_notification_emails_task

        send_task_notification_emails_task.delay(messages)
        logger.debug("Scheduled %d task email(s) via Celery.", len(messages))
    except Exception as exc:
        logger.warning(
            "Celery unavailable for task emails (%s), falling back to background thread.",
            exc,
        )
        _dispatch_in_background_thread(messages)
