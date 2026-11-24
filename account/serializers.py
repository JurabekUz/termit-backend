from django.utils import timezone
from rest_framework import serializers
from rest_framework.fields import CharField
from rest_framework.serializers import ModelSerializer, SerializerMethodField

from account.models import CustomUser, UserActivityLog, UserRoles, UserSession, random_password
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
        fields = ('id', 'full_name', 'pinfl', 'role', 'ministry', 'regions')
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
        regions = validated_data.pop('regions', [])
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
        fields = ('id', 'full_name', 'role', 'ministry', 'regions')

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


class ActivityUserSerializer(ModelSerializer):
    region_name = CharField(source='region.name', read_only=True, allow_null=True)
    ministry_name = CharField(source='ministry.name', read_only=True, allow_null=True)

    class Meta:
        model = CustomUser
        fields = ('id', 'full_name', 'pinfl', 'role', 'region_name', 'ministry_name')


class UserSessionSerializer(ModelSerializer):
    user = ActivityUserSerializer(read_only=True)
    ip_address = serializers.CharField(read_only=True, allow_null=True)
    login_at = serializers.DateTimeField(format="%d-%m-%Y %H:%M:%S", read_only=True)
    logout_at = serializers.DateTimeField(format="%d-%m-%Y %H:%M:%S", read_only=True, allow_null=True)
    last_seen_at = serializers.DateTimeField(format="%d-%m-%Y %H:%M:%S", read_only=True)
    actions_count = serializers.IntegerField(read_only=True, default=0)
    duration_seconds = SerializerMethodField()

    class Meta:
        model = UserSession
        fields = (
            'id',
            'user',
            'login_method',
            'login_at',
            'logout_at',
            'last_seen_at',
            'logout_reason',
            'ip_address',
            'user_agent',
            'last_page',
            'is_active',
            'actions_count',
            'duration_seconds',
        )

    def get_duration_seconds(self, obj):
        end_time = obj.logout_at or (timezone.now() if obj.is_active else obj.last_seen_at)
        if not end_time or not obj.login_at:
            return 0
        return max(0, int((end_time - obj.login_at).total_seconds()))


class UserActivityLogSerializer(ModelSerializer):
    user = ActivityUserSerializer(read_only=True)
    ip_address = serializers.CharField(read_only=True, allow_null=True)
    session_id = serializers.UUIDField(read_only=True, allow_null=True)
    login_at = serializers.DateTimeField(
        source='session.login_at', format="%d-%m-%Y %H:%M:%S", read_only=True, allow_null=True
    )
    logout_at = serializers.DateTimeField(
        source='session.logout_at', format="%d-%m-%Y %H:%M:%S", read_only=True, allow_null=True
    )
    session_is_active = serializers.BooleanField(
        source='session.is_active', read_only=True, allow_null=True
    )
    login_method = serializers.CharField(
        source='session.login_method', read_only=True, allow_null=True
    )
    created_at = serializers.DateTimeField(format="%d-%m-%Y %H:%M:%S", read_only=True)

    class Meta:
        model = UserActivityLog
        fields = (
            'id',
            'user',
            'session_id',
            'login_at',
            'logout_at',
            'session_is_active',
            'login_method',
            'action',
            'method',
            'endpoint',
            'from_page',
            'to_page',
            'page_title',
            'resource_type',
            'resource_id',
            'object_repr',
            'description',
            'status_code',
            'ip_address',
            'changes',
            'metadata',
            'created_at',
        )


class PageNavigationSerializer(serializers.Serializer):
    from_page = serializers.CharField(max_length=500, required=False, allow_blank=True, default='')
    to_page = serializers.CharField(max_length=500, required=True, allow_blank=False)
    page_title = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
