from django.db import transaction
from rest_framework.fields import ListField, FloatField, IntegerField, CharField, ChoiceField
from rest_framework.serializers import ModelSerializer
from django.utils.translation import gettext_lazy as _

from appeal.models import Appeal, AppealStatus
from baseapp.serializers import IdNameSerializer
from config.utils import CommonException
from damaged_object.models import MahallaInfo, DamagedTypes, AppealObjectStatus, DamagedObject, OpenAreaInfo, \
    DamagedStatus
from damaged_object.validators import location_validator, coordinates_validator
from info.serializers import MediaSerializer
from notification.services import increment_counter_on_appeal_creation

""" Appeal """


class AppealListSerializer(ModelSerializer):
    region = IdNameSerializer(source='district.region')
    district = IdNameSerializer()

    class Meta:
        model = Appeal
        fields = ('id', 'district', 'obj_count', 'status', 'damaged_type', 'region', 'created_at', 'unread')


class AppealCheckSerializer(ModelSerializer):
    status = ChoiceField(choices=(AppealStatus.approved, AppealStatus.rejected))

    class Meta:
        model = Appeal
        fields = ('status', 'director_comment',)


class AppealDamagedObjectCheckSerializer(ModelSerializer):
    apl_status = ChoiceField(choices=(AppealObjectStatus.apl_approved, AppealObjectStatus.apl_rejected), required=True)

    class Meta:
        model = DamagedObject
        fields = ('apl_status', 'apl_images', 'director_comment')


""" Mahalla """


class AppealMahallaObjectSerializer(ModelSerializer):
    location = ListField(child=FloatField(), write_only=True)

    class Meta:
        model = MahallaInfo
        fields = (
            'id', 'mahalla', 'object_type', 'property_type',
            'cadastral_number', 'location', 'date',
            'owner_name', 'owner_phone', 'address',
            'videos', 'images'
        )

    def validate_location(self, value):
        return location_validator(value)

    def validate_cadastral_number(self, value):
        if value:
            msg = _(
                "You cannot enter this cadastral digital object because"
                " an action is currently being performed on this object.")
            queryset = MahallaInfo.objects.filter(cadastral_number=value).exclude(
                status__in=[DamagedStatus.cleaned, DamagedStatus.completed, DamagedStatus.rejected]
            )
            if queryset.exists():
                raise CommonException(msg)
        return value


class AppealMahallaObjectListSerializer(ModelSerializer):
    mahalla = IdNameSerializer(source='mahallainfo.mahalla')
    object_type = IntegerField(source='mahallainfo.object_type')
    owner_phone = CharField(source='mahallainfo.owner_phone')
    address = CharField(source='mahallainfo.address')

    class Meta:
        model = DamagedObject
        fields = (
            'id', 'mahalla',
            'object_type', 'apl_status',
            'date', 'owner_phone', 'address'
        )


class AppealMahallaSerializer(ModelSerializer):
    damaged_objects = AppealMahallaObjectSerializer(many=True, write_only=True)

    class Meta:
        model = Appeal
        fields = ('district', 'damaged_objects')

    @transaction.atomic
    def create(self, validated_data):
        request = self.context['request']
        damaged_objects_data = validated_data.pop('damaged_objects')
        district = validated_data['district']

        validated_data.update({
            "sender": request.user,
            "damaged_type": DamagedTypes.mahalla,
        })
        appeal = Appeal.objects.create(**validated_data)
        for obj_data in damaged_objects_data:
            obj_data.update({
                'district': district,
                'appeal': appeal,
                'type': DamagedTypes.mahalla,
                'status': None,
                'apl_status': AppealObjectStatus.apl_new
            })
            videos = obj_data.pop('videos', [])
            images = obj_data.pop('images', [])
            mahalla_obj = MahallaInfo.objects.create(**obj_data)
            mahalla_obj.videos.set(videos)
            mahalla_obj.images.set(images)
        increment_counter_on_appeal_creation(region_id=district.region_id)
        return appeal


class AppealMahallaRetrieveSerializer(ModelSerializer):
    region = IdNameSerializer(source='district.region')
    district = IdNameSerializer()
    damaged_objects = AppealMahallaObjectListSerializer(many=True)

    class Meta:
        model = Appeal
        fields = (
            'id', 'district', 'region',
            'obj_count', 'status', 'damaged_type', 'created_at', 'director_comment',
            'damaged_objects'
        )


class AppealMahallaObjectRetrieveSerializer(ModelSerializer):
    district = IdNameSerializer()
    mahalla = IdNameSerializer()
    images = MediaSerializer(many=True)
    videos = MediaSerializer(many=True)
    location = ListField(read_only=True, source='location.coords')
    apl_images = MediaSerializer(many=True)

    class Meta:
        model = MahallaInfo
        fields = (
            'id', 'district', 'mahalla',
            'object_type', 'status', 'property_type',
            'date', 'location',
            'cadastral_number', 'owner_phone',  'owner_name', 'address',
            'created_at', 'updated_at',
            'images', 'videos',
            'apl_images', 'apl_status', 'appeal', 'director_comment'
        )


""" Open Area """


class AppealOpenAreaObjectSerializer(ModelSerializer):
    location = ListField(child=FloatField(), write_only=True)
    coordinates = ListField(child=ListField(child=ListField(child=FloatField())), write_only=True)

    class Meta:
        model = OpenAreaInfo
        fields = (
            'id', 'area_type', 'property_type',
            'location', 'date',
            'owner_name', 'owner_phone', 'address',
            'hectares', 'coordinates',
            'videos', 'images'
        )

    def validate_location(self, value):
        return location_validator(value)

    def validate_coordinates(self, value):
        return coordinates_validator(value)


class AppealOpenAreaObjectListSerializer(ModelSerializer):
    area_type = IdNameSerializer(source='openareainfo.area_type')
    owner_phone = CharField(source='openareainfo.owner_phone')
    address = CharField(source='openareainfo.address')
    hectares = FloatField(source='openareainfo.hectares')

    class Meta:
        model = DamagedObject
        fields = (
            'id', 'area_type', 'apl_status', 'property_type',
            'date', 'owner_phone', 'address', 'hectares'
        )


class AppealOpenAreaSerializer(ModelSerializer):
    damaged_objects = AppealOpenAreaObjectSerializer(many=True, write_only=True)

    class Meta:
        model = Appeal
        fields = ('district', 'damaged_objects')

    @transaction.atomic
    def create(self, validated_data):
        request = self.context['request']
        damaged_objects_data = validated_data.pop('damaged_objects')
        district = validated_data['district']

        validated_data.update({
            "sender": request.user,
            "damaged_type": DamagedTypes.open_area,
        })
        appeal = Appeal.objects.create(**validated_data)
        for obj_data in damaged_objects_data:
            obj_data.update({
                'district': district,
                'appeal': appeal,
                'type': DamagedTypes.open_area,
                'status': None,
                'apl_status': AppealObjectStatus.apl_new
            })
            videos = obj_data.pop('videos', [])
            images = obj_data.pop('images', [])
            open_area_obj = OpenAreaInfo.objects.create(**obj_data)
            open_area_obj.videos.set(videos)
            open_area_obj.images.set(images)
        increment_counter_on_appeal_creation(region_id=district.region_id)
        return appeal


class AppealOpenAreaRetrieveSerializer(ModelSerializer):
    region = IdNameSerializer(source='district.region')
    district = IdNameSerializer()
    damaged_objects = AppealOpenAreaObjectListSerializer(many=True)

    class Meta:
        model = Appeal
        fields = (
            'id', 'district', 'region',
            'obj_count', 'status', 'damaged_type', 'created_at', 'director_comment',
            'damaged_objects'
        )


class AppealOpenAreaObjectRetrieveSerializer(ModelSerializer):
    district = IdNameSerializer()
    area_type = IdNameSerializer()
    images = MediaSerializer(many=True)
    location = ListField(read_only=True, source='location.coords')
    coordinates = ListField(read_only=True, source='coordinates.coords')
    apl_images = MediaSerializer(many=True)

    class Meta:
        model = OpenAreaInfo
        fields = (
            'id', 'district', 'area_type', 'property_type',
            'status',
            'date', 'location',
            'owner_phone',  'owner_name', 'address', 'hectares',
            'coordinates',
            'created_at', 'updated_at',
            'images',
            'apl_images', 'apl_status', 'appeal', 'director_comment'
        )
