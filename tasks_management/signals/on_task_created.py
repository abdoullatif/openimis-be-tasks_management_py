"""
Envoi d'un email aux exécuteurs (utilisateurs chargés de valider) lorsqu'une tâche est créée.
"""
import logging
from django.core.mail import send_mail
from django.conf import settings

from tasks_management.apps import TasksManagementConfig
from tasks_management.models import Task
from tasks_management.task_labels import source_label, entity_label

logger = logging.getLogger(__name__)


def _get_user_email(user):
    """Récupère l'email de l'utilisateur (core.User peut exposer email ou email_id)."""
    for attr in ("email", "email_id"):
        if hasattr(user, attr):
            value = getattr(user, attr)
            if value and isinstance(value, str) and value.strip() and "@" in value:
                return value.strip()
    return None


def _get_user_display_name(user):
    """Nom affiché pour l'utilisateur (pour le corps du mail)."""
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


def on_task_created_notify_executors(**kwargs):
    """
    Envoie un email à chaque exécuteur du groupe de la tâche lorsqu'une tâche est créée.
    S'exécute après le signal task_service.create.
    """
    print("[tasks_management] on_task_created_notify_executors: handler appelé")
    send_on_create = getattr(TasksManagementConfig, "send_email_on_task_create", True)
    if send_on_create in (False, "false", "False", "0", 0):
        print("[tasks_management] envoi email désactivé (send_email_on_task_create=False)")
        return

    result = kwargs.get("result")
    if not result or not result.get("success"):
        print("[tasks_management] pas de result success dans kwargs, abandon")
        return

    data = result.get("data") or {}
    task_id = data.get("id")
    if not task_id:
        print("[tasks_management] pas d'id dans result['data'], abandon")
        return

    print("[tasks_management] task_id=%s, chargement tâche..." % task_id)
    try:
        task = (
            Task.objects.filter(id=task_id)
            .select_related("task_group")
            .prefetch_related("task_group__taskexecutor_set__user", "task_group__taskexecutor_set__user__i_user")
            .first()
        )
        if not task:
            print("[tasks_management] tâche introuvable en base, abandon")
            return
        if not task.task_group:
            print("[tasks_management] tâche sans groupe (task_group), aucun exécuteur à notifier")
            return

        executors = (
            task.task_group.taskexecutor_set.filter(is_deleted=False)
            .select_related("user", "user__i_user")
            .distinct()
        )
        if not executors:
            print("[tasks_management] groupe sans exécuteurs, aucun email envoyé")
            return
        print("[tasks_management] %d exécuteur(s) trouvé(s), envoi des emails..." % executors.count())

        source = source_label(task.source)
        entity_str = entity_label(task.source, task.business_event)
        subject = f"Nouvelle tâche à valider : {source}"
        if entity_str:
            subject = f"{subject} - {entity_str[:50]}{'…' if len(entity_str) > 50 else ''}"

        default_from = getattr(
            settings,
            "DEFAULT_FROM_EMAIL",
            getattr(settings, "EMAIL_HOST_USER", "noreply@openimis.local"),
        )
        if not default_from:
            default_from = "noreply@openimis.local"

        sent = 0
        for executor in executors:
            user = executor.user
            email = _get_user_email(user)
            if not email:
                print("[tasks_management] exécuteur %s (%s) sans email, ignoré" % (user.id, _get_user_display_name(user)))
                logger.warning(
                    "Task %s: no email for executor user id=%s (%s), skipping email.",
                    task_id,
                    user.id,
                    _get_user_display_name(user),
                )
                continue

            display_name = _get_user_display_name(user)
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

            try:
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=default_from,
                    recipient_list=[email],
                    fail_silently=False,
                )
                sent += 1
                print("[tasks_management] email envoyé à %s" % email)
            except Exception as e:
                print("[tasks_management] ERREUR envoi email à %s: %s" % (email, e))
                logger.exception(
                    "Failed to send task creation email to %s for task %s: %s",
                    email,
                    task_id,
                    e,
                )

        if sent:
            print("[tasks_management] total: %d email(s) envoyé(s) pour la tâche %s" % (sent, task_id))
            logger.info("Task %s: notification email sent to %d executor(s).", task_id, sent)
        else:
            print("[tasks_management] aucun email envoyé (exécuteurs sans email?)")
    except Exception as e:
        print("[tasks_management] ERREUR dans on_task_created_notify_executors: %s" % e)
        logger.exception(
            "Error in on_task_created_notify_executors for task %s: %s",
            data.get("id") if data else "?",
            e,
        )
        return [str(e)]
