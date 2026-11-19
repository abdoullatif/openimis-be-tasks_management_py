import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="tasks_management.tasks.send_task_notification_emails_task",
    ignore_result=True,
)
def send_task_notification_emails_task(messages):
    """Send task emails asynchronously. ignore_result avoids Redis result-backend auth issues."""
    from tasks_management.email_delivery import send_email_messages_sync

    try:
        sent = send_email_messages_sync(messages)
        logger.info("Task notification emails sent: %s/%s", sent, len(messages or []))
        return sent
    except Exception as exc:
        logger.exception("Task notification emails failed: %s", exc)
        return 0
