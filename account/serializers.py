from rest_framework.fields import CharField
from rest_framework.serializers import ModelSerializer, SerializerMethodField

from account.models import CustomUser, random_password, UserRoles
from account.validators import user_role_validator
from area.serializers import AreaSelectSerializer
from baseapp.serializers import IdNameSerializer
from config.utils import CommonException


class UserListSerializer(ModelSerializer):
    ministry_name = CharField(source='ministry.name', read_only=True, allow_null=True)
    region_name = CharField(source='region.name', read_only=True, allow_null=True)
    region_names = SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = ('id', 'full_name', 'pinfl', 'role', 'ministry_name', 'region_name', 'region_names')

    def get_region_names(self, obj):
        return [region.name for region in obj.regions.all()]


class CreateUserSerializer(ModelSerializer):

    class Meta:
        model = CustomUser
        fields = ('id', 'pinfl', 'role', 'ministry', 'regions')
        extra_kwargs = {
            'pinfl': {'required': True, 'allow_blank': False}
        }

    def validate(self, attrs):
        role = attrs.get('role')
        regions = attrs.get('regions')
        region = regions[0] if regions else None
        ministry = attrs.get('ministry')
        user_role_validator(role, ministry, region)
        attrs['region'] = region
        return attrs

    def create(self, validated_data):
        regions = validated_data.pop('regions')
        validated_data['username'] = validated_data['pinfl']
        validated_data['password'] = random_password()
        user = CustomUser.objects.create_user(**validated_data)
        user.regions.set(regions)
        return user


class RetrieveUserSerializer(ModelSerializer):
    ministry = IdNameSerializer(allow_null=True)
    region = AreaSelectSerializer(allow_null=True)
    regions = AreaSelectSerializer(many=True, allow_null=True)

    class Meta:
        model = CustomUser
        fields = ('id', 'full_name', 'pinfl', 'role', 'ministry', 'region', 'regions')


class UpdateUserSerializer(ModelSerializer):

    class Meta:
        model = CustomUser
        fields = ('id', 'role', 'ministry', 'regions')

    def validate(self, attrs):
        role = attrs.get('role')
        regions = attrs.get('regions')
        region = regions[0] if regions else None
        ministry = attrs.get('ministry')
        user_role_validator(role, ministry, region)
        attrs['region'] = region

        role = attrs.get('role')
        if role:
            if role != UserRoles.RM:
                attrs['region'] = None
                attrs['regions'] = []
            if role != UserRoles.ME:
                attrs['ministry'] = None
        return attrs


class UserFullNameSerializer(ModelSerializer):

    class Meta:
        model = CustomUser
        fields = ('id', 'full_name',)


class UpdateRegionUserSerializer(ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['region']

    def validate_region(self, value):
        user = self.context['request'].user
        if not user.regions.filter(id=value.id).exists():
            raise CommonException("You do not select this region")
        return value
