from django_filters import rest_framework as filters

from account.models import UserActivityLog, UserSession


class UserSessionFilter(filters.FilterSet):
    role = filters.CharFilter(field_name='user__role')
    date_from = filters.DateFilter(field_name='login_at__date', lookup_expr='gte')
    date_to = filters.DateFilter(field_name='login_at__date', lookup_expr='lte')

    class Meta:
        model = UserSession
        fields = ['user', 'role', 'login_method', 'is_active', 'date_from', 'date_to']


class UserActivityLogFilter(filters.FilterSet):
    role = filters.CharFilter(field_name='user__role')
    session = filters.UUIDFilter(field_name='session_id')
    date_from = filters.DateFilter(field_name='created_at__date', lookup_expr='gte')
    date_to = filters.DateFilter(field_name='created_at__date', lookup_expr='lte')

    class Meta:
        model = UserActivityLog
        fields = ['user', 'role', 'session', 'action', 'resource_type', 'date_from', 'date_to']
