from django.db import transaction
from rest_framework.exceptions import ValidationError
from rest_framework.fields import ListField, ChoiceField, FloatField, CharField, IntegerField, SerializerMethodField
from rest_framework.serializers import ModelSerializer, Serializer
from django.utils.translation import gettext_lazy as _

from account.models import UserRoles
from config.utils import CommonException
from damaged_object.models import MahallaInfo, OpenAreaInfo, DamagedTypes, DamagedStatus, DamagedObjectFlow, \
    DamagedObject
from baseapp.serializers import IdNameSerializer
from damaged_object.validators import location_validator, coordinates_validator
from info.serializers import MediaSerializer
from notification.models import ModuleChoices
from notification.services import increment_counter_on_damaged_object_creation, \
    increment_counter_on_damaged_object_checking
from plan.serializers import PlanItemSerializer


""" ItemStatusFlow """


class DamagedObjectFlowSerializer(ModelSerializer):

    class Meta:
        model = DamagedObjectFlow
        fields = ('id', 'status', 'created_at')


""" DamagedObject """


class DamagedObjectFreeListSerializer(ModelSerializer):
    district = IdNameSerializer()

    class Meta:
        model = DamagedObject
        fields = ('id', 'status', 'district', 'date', 'type')

    def to_representation(self, instance):
        data = super().to_representation(instance)
        related_name = 'mahallainfo' if instance.type == DamagedTypes.mahalla else 'openareainfo'
        related_obj = getattr(instance, related_name)
        data['owner_name'] = related_obj.owner_name
        data['owner_phone'] = related_obj.owner_phone
        data['address'] = related_obj.address
        return data


""" MahallaInfo """


class MahallaInfoSerializer(ModelSerializer):
    location = ListField(child=FloatField(), write_only=True)

    class Meta:
        model = MahallaInfo
        fields = (
            'id', 'district', 'mahalla', 'object_type', 'property_type',
            'cadastral_number', 'location', 'date',
            'owner_name', 'owner_phone', 'address',
            'videos', 'images'
        )

    def validate_location(self, value):
        return location_validator(value)

    def validate_cadastral_number(self, value):
        if value:
            msg = _("You cannot enter this cadastral digital object because an action is currently being performed on this object.")
            queryset = MahallaInfo.objects.filter(cadastral_number=value).exclude(
                    status__in=[DamagedStatus.cleaned, DamagedStatus.completed, DamagedStatus.rejected]
            )
            if self.instance and queryset.exclude(id=self.instance.id).exists():
                raise CommonException(msg)
            elif queryset.exists():
                raise CommonException(msg)
        return value

    def validate(self, attrs):
        request = self.context['request']
        if request.user.role != UserRoles.RM:
            raise ValidationError("You do not have permission to perform this action.")
        if attrs['district'].region_id != request.user.region_id:
            raise ValidationError(_("You cannot create damaged object in this region."))
        elif attrs['mahalla'].district_id != attrs['district'].id:
            raise ValidationError("Mahalla and district do not match.")
        return attrs


    @transaction.atomic
    def create(self, validated_data):
        request = self.context['request']
        validated_data.update({
            "created_by": request.user,
            "type": DamagedTypes.mahalla,
        })
        # update counter
        increment_counter_on_damaged_object_creation(module=ModuleChoices.mahalla)
        return super().create(validated_data)


class MahallaInfoListSerializer(ModelSerializer):
    district = IdNameSerializer()
    mahalla = IdNameSerializer()
    created_by = SerializerMethodField(method_name='get_created_by_name', allow_null=True)

    class Meta:
        model = MahallaInfo
        fields = (
            'id', 'district', 'mahalla',
            'object_type', 'status',
            'date', 'owner_phone', 'address', 'owner_name',
            'created_by', 'created_at', 'unread'
        )

    def get_created_by_name(self, obj):
        try:
            return obj.created_by.full_name
        except:
            return None


class MahallaInfoRetrieveSerializer(ModelSerializer):
    district = IdNameSerializer()
    mahalla = IdNameSerializer()
    images = MediaSerializer(many=True)
    videos = MediaSerializer(many=True)
    location = ListField(read_only=True, source='location.coords')
    flows = DamagedObjectFlowSerializer(many=True, read_only=True)

    class Meta:
        model = MahallaInfo
        fields = (
            'id', 'district', 'mahalla',
            'object_type', 'status', 'property_type',
            'date', 'location',
            'cadastral_number', 'owner_phone',  'owner_name', 'address',
            'created_at', 'updated_at',
            'images', 'videos',
            'director_comment', 'apl_images',
            'flows'
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['plan_items'] = PlanItemSerializer(
            instance.plan_items.filter(is_performed=True).select_related(
                'document', 'performer').prefetch_related('images'),
            many=True, allow_null=True, context=self.context
        ).data or None
        return data


class MahallaInfoCheckSerializer(ModelSerializer):
    status = ChoiceField(choices=(DamagedStatus.approved, DamagedStatus.rejected))

    class Meta:
        model = MahallaInfo
        fields = ('status', 'director_comment')

    def update(self, instance, validated_data):
        instance.status = validated_data.get('status', instance.status)
        instance.director_comment = validated_data.get('director_comment', instance.director_comment)
        instance.save()

        if validated_data['status'] == DamagedStatus.approved:
            instance.create_flow(status=DamagedStatus.approved)
            # update mahalla
            mahalla = instance.mahalla
            mahalla.update_status_and_percentage()
        increment_counter_on_damaged_object_checking(
            status=validated_data['status'],
            region_id=instance.district.region_id,
            module=ModuleChoices.mahalla
        )
        return instance


class OpenAreaInfoSerializer(ModelSerializer):
    location = ListField(child=FloatField(), write_only=True)
    coordinates = ListField(child=ListField(child=ListField(child=FloatField())), write_only=True)

    class Meta:
        model = OpenAreaInfo
        fields = (
            'id', 'district', 'area_type', 'property_type',
            'location', 'date',
            'owner_name', 'owner_phone', 'address', 'hectares',
            'coordinates',
            'images'
        )

    def validate_location(self, value):
        return location_validator(value)

    def validate_coordinates(self, value):
        return coordinates_validator(value)

    def validate(self, attrs):
        request = self.context['request']
        if request.user.role != UserRoles.RM:
            raise ValidationError("You do not have permission to perform this action.")
        if attrs['district'].region_id != request.user.region_id:
            raise ValidationError(_("You cannot create damaged object in this region."))
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context['request']

        validated_data.update({
            "created_by": request.user,
            "type": DamagedTypes.open_area,
        })
        # update counter
        increment_counter_on_damaged_object_creation(module=ModuleChoices.open_area)
        return super().create(validated_data)


class OpenAreaInfoListSerializer(ModelSerializer):
    district = IdNameSerializer()
    area_type = IdNameSerializer()
    created_by = SerializerMethodField(method_name='get_created_by_name', allow_null=True)

    class Meta:
        model = OpenAreaInfo
        fields = (
            'id', 'district', 'area_type',
            'status',
            'date', 'owner_phone', 'address', 'hectares', 'owner_name',
            'created_by', 'created_at', 'unread'
        )

    def get_created_by_name(self, obj):
        try:
            return obj.created_by.full_name
        except:
            return None


class OpenAreaInfoRetrieveSerializer(ModelSerializer):
    district = IdNameSerializer()
    area_type = IdNameSerializer()
    images = MediaSerializer(many=True)
    location = ListField(read_only=True, source='location.coords')
    coordinates = ListField(read_only=True, source='coordinates.coords')
    flows = DamagedObjectFlowSerializer(many=True, read_only=True)

    class Meta:
        model = OpenAreaInfo
        fields = (
            'id', 'district', 'area_type', 'property_type',
            'status',
            'date', 'location',
            'owner_phone',  'owner_name', 'address', 'hectares',
            'coordinates',
            'created_at', 'updated_at',
            'images', 'director_comment', 'apl_images',
            'flows'
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['plan_items'] = PlanItemSerializer(
            instance.plan_items.filter(is_performed=True).select_related(
                'document', 'performer').prefetch_related('images'),
            many=True, allow_null=True, context=self.context
        ).data or None
        return data


class OpenAreaInfoCheckSerializer(ModelSerializer):
    status = ChoiceField(choices=(DamagedStatus.approved, DamagedStatus.rejected))

    class Meta:
        model = OpenAreaInfo
        fields = ('status', 'director_comment')


""" Statistic Serializers """


class ObjectStatSerializer(Serializer):
    label = CharField()
    total_damaged_object = IntegerField()
    total = IntegerField()
    percentage = SerializerMethodField(method_name='round_percentage')

    def round_percentage(self, obj):
        return round(obj['percentage'], 2)


class OpenAreaStatSerializer(Serializer):
    label = CharField(source='name')
    total_damaged_object = FloatField()
    total = FloatField()
    percentage = SerializerMethodField(method_name='round_percentage')

    def round_percentage(self, obj):
        return round(obj.percentage, 2)



