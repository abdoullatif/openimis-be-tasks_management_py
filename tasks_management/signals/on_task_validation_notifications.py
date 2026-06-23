import logging

from core.forms import User
from tasks_management.apps import TasksManagementConfig
from tasks_management.models import Task
from tasks_management.task_labels import source_label, entity_label
from tasks_management.email_delivery import (
    get_user_display_name,
    get_user_email,
    is_task_email_enabled,
    schedule_task_emails,
)

logger = logging.getLogger(__name__)


def _get_executor_status_sets(task, executors):
    status_by_user_id = task.business_status or {}
    approved = []
    pending = []
    for executor in executors:
        user = executor.user
        user_status = status_by_user_id.get(str(user.id), "PENDING")
        if user_status == TasksManagementConfig.task_user_approved:
            approved.append(user)
        else:
            pending.append(user)
    return approved, pending


def notify_other_executors_on_validation(**kwargs):
    """
    Lorsqu'un exécuteur valide une tâche, notifier les autres exécuteurs (asynchrone).
    """
    if not is_task_email_enabled():
        return

    result = kwargs.get("result")
    if not result or not result.get("success"):
        return

    try:
        data = result.get("data") or {}
        task_data = data.get("task") or {}
        task_id = task_data.get("id")
        action_user_id = (data.get("user") or {}).get("id")
        if not task_id or not action_user_id:
            return

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

        action_user = User.objects.filter(id=action_user_id).select_related("i_user").first()
        if not action_user:
            return

        approved, pending = _get_executor_status_sets(task, executors)
        pending_names = ", ".join(get_user_display_name(u) for u in pending) if pending else "Aucun"
        approved_names = ", ".join(get_user_display_name(u) for u in approved) if approved else "Aucun"
        validator_name = get_user_display_name(action_user)

        recipients = []
        for executor in executors:
            if str(executor.user_id) == str(action_user_id):
                continue
            recipient_email = get_user_email(executor.user)
            if recipient_email:
                recipients.append(recipient_email)

        if not recipients:
            return

        source = source_label(task.source)
        entity_lbl = entity_label(task.source, task.business_event)
        subject = f"Validation effectuee: {validator_name} a valide la tache {source}"
        body = (
            f"Bonjour,\n\n"
            f"{validator_name} vient de valider la tache '{source}'.\n"
            f"Entite concernee: {entity_lbl}\n\n"
            f"Utilisateurs ayant validé: {approved_names}\n"
            f"Utilisateurs en attente: {pending_names}\n\n"
            f"Merci de vous connecter à l'application pour continuer le traitement.\n\n"
            f"Cordialement,\n"
            f"L'équipe NAFAMIS/ANIES"
        )

        schedule_task_emails(
            [
                {
                    "subject": subject,
                    "message": body,
                    "recipient_list": list(set(recipients)),
                }
            ]
        )
        logger.info(
            "Task %s: scheduled validation alert for %d executor(s).",
            task_id,
            len(set(recipients)),
        )
    except Exception as exc:
        logger.error("Error scheduling notify_other_executors_on_validation", exc_info=exc)


def notify_task_initiator_on_completion(**kwargs):
    """
    Quand la tâche est COMPLETED, notifier l'initiateur (asynchrone).
    """
    if not is_task_email_enabled():
        return

    result = kwargs.get("result")
    if not result or not result.get("success"):
        return

    try:
        data = result.get("data") or {}
        task_data = data.get("task") or {}
        if task_data.get("status") != Task.Status.COMPLETED:
            return

        task_id = task_data.get("id")
        if not task_id:
            return

        task = (
            Task.objects.filter(id=task_id)
            .select_related("user_created", "user_created__i_user", "task_group")
            .prefetch_related(
                "task_group__taskexecutor_set__user",
                "task_group__taskexecutor_set__user__i_user",
            )
            .first()
        )
        if not task:
            return

        initiator = getattr(task, "user_created", None)
        if not initiator:
            logger.warning("Task %s: no task initiator found (user_created).", task_id)
            return

        initiator_email = get_user_email(initiator)
        if not initiator_email:
            logger.warning("Task %s: initiator has no email, completion alert skipped.", task_id)
            return

        executors = []
        if task.task_group:
            executors = list(
                task.task_group.taskexecutor_set.filter(is_deleted=False)
                .select_related("user", "user__i_user")
                .distinct()
            )
        approved, pending = _get_executor_status_sets(task, executors)
        approved_names = ", ".join(get_user_display_name(u) for u in approved) if approved else "Aucun"
        pending_names = ", ".join(get_user_display_name(u) for u in pending) if pending else "Aucun"

        source = source_label(task.source)
        entity_lbl = entity_label(task.source, task.business_event)
        subject = f"Tache finalisee: {source}"
        body = (
            f"Bonjour {get_user_display_name(initiator)},\n\n"
            f"La tache '{source}' que vous avez declenchee est maintenant entierement validee.\n"
            f"Entite concernee: {entity_lbl}\n\n"
            f"Utilisateurs ayant validé: {approved_names}\n"
            f"Utilisateurs encore en attente: {pending_names}\n\n"
            f"Cordialement,\n"
            f"L'équipe NAFAMIS/ANIES"
        )

        schedule_task_emails(
            [
                {
                    "subject": subject,
                    "message": body,
                    "recipient_list": [initiator_email],
                }
            ]
        )
        logger.info("Task %s: scheduled completion alert to initiator.", task_id)
    except Exception as exc:
        logger.error("Error scheduling notify_task_initiator_on_completion", exc_info=exc)
