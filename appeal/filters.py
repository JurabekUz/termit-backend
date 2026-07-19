from django_filters import rest_framework as filters

from appeal.models import Appeal
from area.models import Region


class AppealFilter(filters.FilterSet):
    region = filters.ModelChoiceFilter(
        queryset=Region.objects.all(),
        field_name="district__region"
    )

    class Meta:
        model = Appeal
        fields = ['status', 'district', 'damaged_type', 'region']
