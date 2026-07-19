from django_filters import rest_framework as filters

from .models import District, Mahalla, Region, OpenArea


class DistrictFilter(filters.FilterSet):
    region = filters.NumberFilter(field_name="region")

    class Meta:
        model = District
        fields = ['region', 'parent_code']


class MahallaFilter(filters.FilterSet):
    region = filters.ModelChoiceFilter(
        queryset=Region.objects.all(),
        field_name="district__region"
    )

    class Meta:
        model = Mahalla
        fields = ('district', 'region', 'parent_code')


class OpenAreaFilter(filters.FilterSet):
    region = filters.ModelChoiceFilter(
        queryset=Region.objects.all(),
        field_name="district__region"
    )
    district_code = filters.NumberFilter(field_name="district__code")
    region_code = filters.NumberFilter(field_name="district__region__code")

    class Meta:
        model = OpenArea
        fields = ('district', 'region', 'district_code', 'region_code')

