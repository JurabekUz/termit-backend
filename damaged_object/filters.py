from django_filters import rest_framework as filters
from django.db.models import Subquery, OuterRef, Q, CharField

from area.models import Region
from damaged_object.models import MahallaInfo, OpenAreaInfo, DamagedStatus, DamagedObject
from plan.models import PlanItem, PlanStatus, Plan


def filter_is_free(queryset, name, value):
    if value:
        latest_plan_status = PlanItem.objects.filter(
            item=OuterRef('id')
        ).order_by('-id').values('plan__status')[:1]

        return queryset.filter(
            status=DamagedStatus.approved
        ).annotate(
            latest_plan_status=Subquery(latest_plan_status, output_field=CharField(null=True))
        ).filter(
            # Q(plan_items__isnull=True) |
            # Q(latest_plan_status__in=[PlanStatus.cleaned, PlanStatus.rejected])
            Q(latest_plan_status__in=[PlanStatus.completed, PlanStatus.rejected]) | Q(latest_plan_status__isnull=True)
        )
    return queryset


class MahallaInfoFilter(filters.FilterSet):
    region = filters.ModelChoiceFilter(
        queryset=Region.objects.all(),
        field_name="district__region"
    )
    is_free = filters.BooleanFilter(method=filter_is_free)
    plan = filters.ModelChoiceFilter(
        queryset=Plan.objects.all(),
        field_name="plan_items__plan"
    )

    class Meta:
        model = MahallaInfo
        fields = ['mahalla', 'object_type', 'district', 'region', 'status', 'plan', 'is_free']


class OpenAreaInfoFilter(filters.FilterSet):
    region = filters.ModelChoiceFilter(
        queryset=Region.objects.all(),
        field_name="district__region"
    )
    is_free = filters.BooleanFilter(method=filter_is_free)
    plan = filters.ModelChoiceFilter(
        queryset=Plan.objects.all(),
        field_name="plan_items__plan"
    )

    class Meta:
        model = OpenAreaInfo
        fields = ['area_type', 'district', 'region', 'status', 'plan', 'is_free']


class FreeDamagedObjectFilter(filters.FilterSet):
    region = filters.ModelChoiceFilter(
        queryset=Region.objects.all(),
        field_name="district__region"
    )

    class Meta:
        model = DamagedObject
        fields = ['type', 'district', 'region']
