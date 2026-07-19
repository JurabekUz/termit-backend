from django.db.models import Count
from rest_framework.serializers import ModelSerializer, Serializer
from rest_framework.fields import CharField, ListField, IntegerField, SerializerMethodField

from baseapp.serializers import IdNameSerializer
from damaged_object.models import ObjectTypes
from .models import Region, Mahalla, District, OpenArea


class AreaSelectSerializer(Serializer):
    value = IntegerField(source='id')
    label = CharField(source='name')
    code = IntegerField()


class RegionRetrieveSerializer(ModelSerializer):
    coordinates = ListField(read_only=True, source='coordinates.coords')

    class Meta:
        model = Region
        fields = '__all__'


class RegionListSerializer(ModelSerializer):

    class Meta:
        model = Region
        fields = ('id', 'name', 'center_lan', 'center_lat')


class DistrictListSerializer(ModelSerializer):
    region_name = CharField(source='region.name')

    class Meta:
        model = District
        fields = ('id', 'name', 'region_name', 'center_lan', 'center_lat')


class DistrictRetrieveSerializer(ModelSerializer):
    region = IdNameSerializer()
    coordinates = ListField(read_only=True, source='coordinates.coords')

    class Meta:
        model = District
        fields = '__all__'


class MahallaUpdateSerializer(ModelSerializer):

    class Meta:
        model = Mahalla
        fields = ('phone_number', 'address', 'households', 'social_objects', 'historical_sites', 'adm_buildings')

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        # update status
        instance.update_status_and_percentage()
        return instance


class MahallaRetrieveSerializer(ModelSerializer):
    district = IdNameSerializer()
    coordinates = ListField(read_only=True, source='coordinates.coords')
    percentage_display = CharField(read_only=True)
    damaged_by_type = SerializerMethodField()

    class Meta:
        model = Mahalla
        fields = '__all__'

    def get_damaged_by_type(self, obj):
        object_types_data = {
            1: "households",
            2: "social_objects",
            3: "historical_sites",
            4: "adm_buildings",
        }

        qs = (
            obj.damaged_objects
            .values('object_type')
            .annotate(count=Count('id'))
        )

        # convert to dict: {1: X, 2: Y, ...}
        result = {item['object_type']: item['count'] for item in qs}

        # always include all types
        return {value: result.get(value, 0) for value in object_types_data.values()}


class MahallaListSerializer(ModelSerializer):
    district_name = CharField(source='district.name')

    class Meta:
        model = Mahalla
        fields = (
            'id', 'name', 'district_name', 'address', 'phone_number',
            'info_last_updated', 'objects_count', 'percentage_display'
        )


class MahallaStatusWithCoordinatesSerializer(ModelSerializer):
    coordinates = ListField(read_only=True, source='coordinates.coords')

    class Meta:
        model = Mahalla
        fields = ('id', 'name', 'coordinates', 'status', 'percentage_display')


class OpenAreaSerializer(ModelSerializer):
    district_name = CharField(source='district.name', read_only=True)

    class Meta:
        model = OpenArea
        fields = ('id', 'district', 'hectare', 'district_name')
        extra_kwargs = {'district': {'read_only': True}}


class OpenAreaUpdateRetrieveSerializer(ModelSerializer):
    # district = DistrictRetrieveSerializer(read_only=True)

    class Meta:
        model = OpenArea
        fields = ('id', 'district', 'hectare')
