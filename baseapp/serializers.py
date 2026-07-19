from rest_framework.fields import IntegerField, CharField
from rest_framework.serializers import Serializer


class IdNameSerializer(Serializer):
    id = IntegerField()
    name = CharField()


class SelectSerializer(Serializer):
    value = IntegerField(source='id')
    label = CharField(source='name')
