import importlib
import copy

import graphene
from django.db.models import Q
from graphene_django import DjangoObjectType

from core import ExtendedConnection, prefix_filterset
from core.gql_queries import UserGQLType
from tasks_management.apps import TasksManagementConfig
from tasks_management.models import TaskGroup, TaskExecutor, Task

DICT_STRING = "{}"


class ExecutorStatusType(graphene.ObjectType):
    """Type GraphQL pour représenter le statut d'un exécuteur"""
    userId = graphene.String()
    username = graphene.String()
    fullName = graphene.String()
    status = graphene.String()
    statusDisplay = graphene.String()

"""
def is_task_triage(user):
    perms = []
    if hasattr(TasksManagementConfig, 'gql_task_group_create_perms'):
        perms.extend(TasksManagementConfig.gql_task_group_create_perms)
    if hasattr(TasksManagementConfig, 'gql_task_group_search_perms'):
        perms.extend(TasksManagementConfig.gql_task_group_search_perms)
    if hasattr(TasksManagementConfig, 'gql_task_group_update_perms'):
        perms.extend(TasksManagementConfig.gql_task_group_update_perms)
    if hasattr(TasksManagementConfig, 'gql_task_group_delete_perms'):
        perms.extend(TasksManagementConfig.gql_task_group_delete_perms)
    return user.has_perms(perms)

"""

def is_task_triage(user):
    return user.has_perms(TasksManagementConfig.gql_task_group_create_perms
                          + TasksManagementConfig.gql_task_group_search_perms
                          + TasksManagementConfig.gql_task_group_update_perms
                          + TasksManagementConfig.gql_task_group_delete_perms)




class TaskListGQLType(DjangoObjectType):
    """Type GraphQL pour la liste des tâches avec executorsStatus"""
    uuid = graphene.String(source='uuid')
    business_data = graphene.JSONString()
    entity_string = graphene.String()
    executors_status = graphene.List(ExecutorStatusType)

    class Meta:
        model = Task
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "entity_type": ["exact"],
            "entity_id": ["exact"],
            "source": ["exact", "iexact", "istartswith", "icontains"],
            "status": ["exact", "iexact", "istartswith", "icontains"],
            "executor_action_event": ["exact", "iexact", "istartswith", "icontains"],
            "business_event": ["exact", "iexact", "istartswith", "icontains"],
            "date_created": ["exact", "lt", "lte", "gt", "gte"],
            "date_updated": ["exact", "lt", "lte", "gt", "gte"],
            "is_deleted": ["exact"],
            "version": ["exact"],
        }
        connection_class = ExtendedConnection

    def resolve_business_data(self, info):
        data = self.data
        serializer_path = self.business_data_serializer
        serialized_data = copy.deepcopy(data)
        if serializer_path:
            module_path, class_name, method_name = serializer_path.rsplit('.', 2)

            try:
                service_module = importlib.import_module(module_path)

                if hasattr(service_module, class_name):
                    service_class = getattr(service_module, class_name)
                    instance = service_class(info.context.user)

                    serializer_method = getattr(instance, method_name, None)

                    if callable(serializer_method):
                        serialized_data = serializer_method(serialized_data)

            except ImportError:
                return f"Error: Module '{module_path}' not found."
            except AttributeError:
                return f"Error: Attribute not found in the module or class."
            except Exception as e:
                return f"Error: {str(e)}"

        return serialized_data

    def resolve_entity_string(self, info):
        return self.entity.__str__()

    def resolve_executors_status(self, info):
        """
        Retourne le statut de validation de chaque exécuteur assigné à la tâche.
        Récupère les vraies informations utilisateur sans déclencher la récursion.
        """
        if not self.task_group:
            return []
        
        executors_status = []
        
        # Récupérer les exécuteurs avec une requête qui évite select_related('user')
        # pour prévenir la récursion
        executors = self.task_group.taskexecutor_set.filter(is_deleted=False)
        
        # Récupérer tous les IDs d'utilisateurs
        user_ids = [executor.user_id for executor in executors]
        
        # Récupérer les informations utilisateur directement depuis la base
        from core.models import User
        users_data = {}
        for user_id in user_ids:
            try:
                # Récupérer l'utilisateur directement sans passer par les relations
                user = User.objects.filter(id=user_id).first()
                if user:
                    # Récupérer les informations sans déclencher __getattr__
                    username = user.username
                    full_name = TaskListGQLType._get_user_full_name(user)
                    users_data[str(user_id)] = {
                        'username': username,
                        'fullName': full_name
                    }
                else:
                    users_data[str(user_id)] = {
                        'username': f"User_{user_id}",
                        'fullName': f"User_{user_id}"
                    }
            except Exception:
                users_data[str(user_id)] = {
                    'username': f"User_{user_id}",
                    'fullName': f"User_{user_id}"
                }
        
        for executor in executors:
            user_id = str(executor.user_id)
            
            # Déterminer le statut de validation
            business_status = self.business_status or {}
            user_status = business_status.get(user_id, "PENDING")
            
            # Récupérer les informations utilisateur
            user_info = users_data.get(user_id, {
                'username': f"User_{user_id}",
                'fullName': f"User_{user_id}"
            })
            
            # Construire l'objet ExecutorStatusType avec les vraies informations
            executor_status = ExecutorStatusType(
                userId=user_id,
                username=user_info['username'],
                fullName=user_info['fullName'],
                status=user_status,
                statusDisplay=TaskListGQLType._get_status_display(user_status)
            )
            
            executors_status.append(executor_status)
        
        return executors_status

    @staticmethod
    def _get_user_full_name(user):
        """Récupérer le nom complet de l'utilisateur sans déclencher la récursion"""
        try:
            # Essayer de récupérer les informations directement depuis les champs
            if hasattr(user, 'i_user_id') and user.i_user_id:
                # Récupérer l'Individual directement
                from individual.models import Individual
                individual = Individual.objects.filter(id=user.i_user_id).first()
                if individual:
                    last_name = individual.last_name or ""
                    other_names = individual.other_names or ""
                    full_name = f"{other_names} {last_name}".strip()
                    # Retourner le nom complet seulement s'il n'est pas vide
                    if full_name:
                        return full_name
            
            # Fallback: utiliser le username comme nom complet
            # (car il n'y a pas d'Individual dans la base)
            return user.username or "Utilisateur inconnu"
            
        except Exception:
            # En cas d'erreur, retourner le username
            return user.username or "Utilisateur inconnu"

    @staticmethod
    def _get_status_display(status):
        """Convertir le statut en texte lisible"""
        status_mapping = {
            "APPROVED": "Tâche validée",
            "REJECTED": "Tâche rejetée",
            "PENDING": "En attente de validation",
            "ESCALATED": "Tâche escaladée",
            "CANCELLED": "Tâche annulée",
            "EXPIRED": "Tâche expirée",
            "FORWARDED": "Tâche transférée",
            "RETURNED": "Tâche retournée",
        }
        return status_mapping.get(status, status)

    @classmethod
    def get_queryset(cls, queryset, info):
        user = info.context.user
        if user.is_imis_admin or is_task_triage(user):
            return queryset.filter(is_deleted=False)
        return queryset.filter(
            Q(task_group__taskexecutor__user=user) & ~Q(status=Task.Status.RECEIVED),
            is_deleted=False
        )


class TaskGQLType(DjangoObjectType):
    """Type GraphQL pour le détail des tâches sans executorsStatus"""
    uuid = graphene.String(source='uuid')
    business_data = graphene.JSONString()
    entity_string = graphene.String()

    class Meta:
        model = Task
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "entity_type": ["exact"],
            "entity_id": ["exact"],

            "source": ["exact", "iexact", "istartswith", "icontains"],
            "status": ["exact", "iexact", "istartswith", "icontains"],
            "executor_action_event": ["exact", "iexact", "istartswith", "icontains"],
            "business_event": ["exact", "iexact", "istartswith", "icontains"],

            "date_created": ["exact", "lt", "lte", "gt", "gte"],
            "date_updated": ["exact", "lt", "lte", "gt", "gte"],
            "is_deleted": ["exact"],
            "version": ["exact"],
        }
        connection_class = ExtendedConnection

    def resolve_business_data(self, info):
        data = self.data
        serializer_path = self.business_data_serializer
        serialized_data = copy.deepcopy(data)
        if serializer_path:
            module_path, class_name, method_name = serializer_path.rsplit('.', 2)

            try:
                service_module = importlib.import_module(module_path)

                if hasattr(service_module, class_name):
                    service_class = getattr(service_module, class_name)
                    instance = service_class(info.context.user)

                    serializer_method = getattr(instance, method_name, None)

                    if callable(serializer_method):
                        serialized_data = serializer_method(serialized_data)

            except ImportError:
                return f"Error: Module '{module_path}' not found."
            except AttributeError:
                return f"Error: Attribute not found in the module or class."
            except Exception as e:
                return f"Error: {str(e)}"

        return serialized_data

    def resolve_entity_string(self, info):
        return self.entity.__str__()

    @classmethod
    def get_queryset(cls, queryset, info):
        user = info.context.user
        if user.is_imis_admin or is_task_triage(user):
            return queryset.filter(is_deleted=False)
        return queryset.filter(
            Q(task_group__taskexecutor__user=user) & ~Q(status=Task.Status.RECEIVED),
            is_deleted=False
        )


class TaskHistoryGQLType(DjangoObjectType):
    uuid = graphene.String(source='uuid')
    business_data = graphene.JSONString()
    entity_string = graphene.String()

    class Meta:
        model = Task.history.model
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "entity_type": ["exact"],
            "entity_id": ["exact"],

            "source": ["exact", "iexact", "istartswith", "icontains"],
            "status": ["exact", "iexact", "istartswith", "icontains"],
            "executor_action_event": ["exact", "iexact", "istartswith", "icontains"],
            "business_event": ["exact", "iexact", "istartswith", "icontains"],

            "date_created": ["exact", "lt", "lte", "gt", "gte"],
            "date_updated": ["exact", "lt", "lte", "gt", "gte"],
            "is_deleted": ["exact"],
            "version": ["exact"],
        }
        connection_class = ExtendedConnection

    def resolve_business_data(self, info):
        data = self.data
        serializer_path = self.business_data_serializer
        serialized_data = copy.deepcopy(data)
        if serializer_path:
            module_path, class_name, method_name = serializer_path.rsplit('.', 2)

            try:
                service_module = importlib.import_module(module_path)

                if hasattr(service_module, class_name):
                    service_class = getattr(service_module, class_name)
                    instance = service_class(info.context.user)

                    serializer_method = getattr(instance, method_name, None)

                    if callable(serializer_method):
                        serialized_data = serializer_method(serialized_data)

            except ImportError:
                return f"Error: Module '{module_path}' not found."
            except AttributeError:
                return f"Error: Attribute not found in the module or class."
            except Exception as e:
                return f"Error: {str(e)}"

        return serialized_data

    def resolve_entity_string(self, info):
        return self.entity.__str__()

    
    

    @classmethod
    def get_queryset(cls, queryset, info):
        user = info.context.user
        if user.is_imis_admin or is_task_triage(user):
            return queryset.filter(is_deleted=False)
        return queryset.filter(
            Q(task_group__taskexecutor__user=user) & ~Q(status=Task.Status.RECEIVED),
            is_deleted=False
        )


class TaskGroupGQLType(DjangoObjectType):
    uuid = graphene.String(source='uuid')
    user = graphene.List(UserGQLType)

    class Meta:
        model = TaskGroup
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "code": ["exact", "iexact", "startswith", "istartswith", "contains", "icontains"],
            "completion_policy": ["exact", "iexact"],

            "date_created": ["exact", "lt", "lte", "gt", "gte"],
            "date_updated": ["exact", "lt", "lte", "gt", "gte"],
            "is_deleted": ["exact"],
            "version": ["exact"],
        }
        connection_class = ExtendedConnection

    def resolve_user(self, info):
        task_group_id = self.id
        return TaskExecutor.objects.filter(task_group_id=task_group_id)


class TaskExecutorGQLType(DjangoObjectType):
    uuid = graphene.String(source='uuid')

    class Meta:
        model = TaskExecutor
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            **prefix_filterset("user__", UserGQLType._meta.filter_fields),
            **prefix_filterset("task_group__", TaskGroupGQLType._meta.filter_fields),
            "date_created": ["exact", "lt", "lte", "gt", "gte"],
            "date_updated": ["exact", "lt", "lte", "gt", "gte"],
            "is_deleted": ["exact"],
            "version": ["exact"],
        }
        connection_class = ExtendedConnection