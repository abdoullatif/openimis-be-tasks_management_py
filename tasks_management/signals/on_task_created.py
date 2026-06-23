"""
Notification email aux exécuteurs à la création de tâche (asynchrone).
"""
import logging

from tasks_management.models import Task
from tasks_management.task_labels import source_label, entity_label
from tasks_management.email_delivery import (
    get_user_display_name,
    get_user_email,
    is_task_email_enabled,
    schedule_task_emails,
)

logger = logging.getLogger(__name__)


def on_task_created_notify_executors(**kwargs):
    """
    Planifie un email à chaque exécuteur du groupe lorsqu'une tâche est créée.
    S'exécute après task_service.create sans bloquer la réponse HTTP.
    """
    if not is_task_email_enabled():
        return

    result = kwargs.get("result")
    if not result or not result.get("success"):
        return

    data = result.get("data") or {}
    task_id = data.get("id")
    if not task_id:
        return

    try:
        task = (
            Task.objects.filter(id=task_id)
            .select_related("task_group")
            .prefetch_related(
                "task_group__taskexecutor_set__user",
                "task_group__taskexecutor_set__user__i_user",
            )
            .first()
        )
        if not task or not task.task_group:
            return

        executors = (
            task.task_group.taskexecutor_set.filter(is_deleted=False)
            .select_related("user", "user__i_user")
            .distinct()
        )
        if not executors:
            return

        source = source_label(task.source)
        entity_str = entity_label(task.source, task.business_event)
        subject = f"Nouvelle tâche à valider : {source}"
        if entity_str:
            subject = f"{subject} - {entity_str[:50]}{'…' if len(entity_str) > 50 else ''}"

        messages = []
        for executor in executors:
            user = executor.user
            email = get_user_email(user)
            if not email:
                logger.warning(
                    "Task %s: no email for executor user id=%s (%s), skipping.",
                    task_id,
                    user.id,
                    get_user_display_name(user),
                )
                continue

            display_name = get_user_display_name(user)
            message = (
                f"Bonjour {display_name},\n\n"
                f"Une nouvelle tâche nécessite votre validation.\n\n"
                f"Source : {source}\n"
            )
            if entity_str:
                message += f"Entité concernée : {entity_str}\n"
            message += (
                f"\nConnectez-vous à l'application pour traiter cette tâche.\n\n"
                f"Cordialement,\n"
                f"L'équipe NAFAMIS/ANIES"
            )
            messages.append(
                {
                    "subject": subject,
                    "message": message,
                    "recipient_list": [email],
                }
            )

        if messages:
            schedule_task_emails(messages)
            logger.info(
                "Task %s: scheduled notification email for %d executor(s).",
                task_id,
                len(messages),
            )
    except Exception as exc:
        logger.exception(
            "Error scheduling on_task_created_notify_executors for task %s: %s",
            task_id,
            exc,
        )
