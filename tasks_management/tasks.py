import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="tasks_management.tasks.send_task_notification_emails_task")
def send_task_notification_emails_task(messages):
    from tasks_management.email_delivery import send_email_messages_sync

    sent = send_email_messages_sync(messages)
    logger.info("Task notification emails sent: %s/%s", sent, len(messages or []))
    return sent
