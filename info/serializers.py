from rest_framework.serializers import ModelSerializer

from .models import Ministry, OpenAreaType, Media


class MinistrySerializer(ModelSerializer):
    class Meta:
        model = Ministry
        fields = ['id', 'name', 'created_at', 'updated_at']


class OpenAreaTypeSerializer(ModelSerializer):
    class Meta:
        model = OpenAreaType
        fields = ['id', 'name', 'created_at', 'updated_at']


class MediaSerializer(ModelSerializer):

    class Meta:
        model = Media
        fields = ("id", "file", 'name')
        extra_kwargs = {'name': {'read_only': True}}
