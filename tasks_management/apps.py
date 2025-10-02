from django.apps import AppConfig

DEFAULT_CONFIG = {
    "gql_task_group_search_perms": ["190001"],
    "gql_task_group_create_perms": ["190002"],
    "gql_task_group_update_perms": ["190003"],
    "gql_task_group_delete_perms": ["190004"],
    
    "gql_task_search_perms": ["191001"],
    "gql_task_create_perms": ["191002"],
    "gql_task_update_perms": ["191003"],
    "gql_task_delete_perms": ["191004"],
    "gql_task_search_all_perms": ["191005"],
    # To be used if task should use generic resolver
    "default_executor_event": "default",
    "task_user_approved": "APPROVED",
}


class TasksManagementConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tasks_management'

    gql_task_group_search_perms = None
    gql_task_group_create_perms = None
    gql_task_group_update_perms = None
    gql_task_group_delete_perms = None
    gql_task_search_perms = None
    gql_task_create_perms = None
    gql_task_update_perms = None
    gql_task_delete_perms = None
    gql_task_search_all_perms = None
    default_executor_event = None
    task_user_approved = None

    def ready(self):
        from core.models import ModuleConfiguration
        from tasks_management.signals import bind_service_signals

        cfg = ModuleConfiguration.get_or_default(self.name, DEFAULT_CONFIG)
        self.__load_config(cfg)
        
        # Bind service signals
        bind_service_signals()
        

    @classmethod
    def __load_config(cls, cfg):
        """
        Load all config fields that match current AppConfig class fields, all custom fields have to be loaded separately
        """
        for field in cfg:
            if hasattr(TasksManagementConfig, field):
                setattr(TasksManagementConfig, field, cfg[field])
