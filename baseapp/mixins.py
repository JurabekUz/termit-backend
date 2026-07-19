from django.db.models import F
from drf_yasg.utils import swagger_auto_schema
from rest_framework.decorators import action
from rest_framework.mixins import DestroyModelMixin
from rest_framework.response import Response

from account.models import UserRoles
from .utils import has_related_objects
from .serializers import SelectSerializer


class SoftDeleteMixin(DestroyModelMixin):
    """
    If the model is linked to other objects, it will be set to `is_active=False`.
    Otherwise, it will be completely removed from the model.
    """

    def perform_destroy(self, instance):
        if has_related_objects(instance):
            instance.is_active = False
            instance.save()
        else:
            instance.delete()


class SelectMixin:
    """
        This Mixin only works to retrieve the `id` and `name` fields in the model.
    """

    @swagger_auto_schema(
        responses={200: SelectSerializer(many=True)}
    )
    @action(
        detail=False,
        methods=['get'],
        pagination_class=None,
        filter_backends=None
    )
    def select(self, request):
        queryset = self.get_queryset().only('id', 'name').annotate(
            value=F('id'),
            label=F('name')
        ).values('value', 'label')
        return Response(queryset)


class FilteredSelectMixin:
    """
        This Mixin only works to retrieve the `id` and `name` fields in the model.
    """

    @swagger_auto_schema(
        responses={200: SelectSerializer(many=True)}
    )
    @action(
        detail=False,
        methods=['get'],
        pagination_class=None,
    )
    def select(self, request):
        queryset = self.get_queryset().only('id', 'name').annotate(
            value=F('id'),
            label=F('name')
        ).values('value', 'label')
        filtered_queryset = self.filter_queryset(queryset)
        return Response(filtered_queryset)


class RegionQuerysetMixin:

    def get_queryset(self):
        user = self.request.user
        if user.role == UserRoles.RM:
            return self.queryset.filter(region_id=user.region_id)
        return self.queryset


class DistrictQuerysetMixin:

    def get_queryset(self):
        user = self.request.user
        if user.role == UserRoles.RM:
            return self.queryset.filter(district__region_id=user.region_id)
        return self.queryset

