from core.service_signals import ServiceSignalBindType
from core.signals import bind_service_signal
from tasks_management.signals.on_task_resolve import on_task_resolve
from tasks_management.signals.on_task_created import on_task_created_notify_executors


def bind_service_signals():
    bind_service_signal(
        'task_service.resolve_task',
        on_task_resolve,
        bind_type=ServiceSignalBindType.AFTER
    )
    bind_service_signal(
        'task_service.create',
        on_task_created_notify_executors,
        bind_type=ServiceSignalBindType.AFTER
    )
