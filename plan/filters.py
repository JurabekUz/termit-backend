from django_filters import rest_framework as filters
from plan.models import Plan


class PlanFilter(filters.FilterSet):
    from_date = filters.DateFilter(field_name="date", lookup_expr='gte')
    to_date = filters.DateFilter(field_name="date", lookup_expr='lte')

    class Meta:
        model = Plan
        fields = ['status', 'from_date', 'to_date']
