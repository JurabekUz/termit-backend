from django.db.models import F
from drf_yasg.utils import swagger_auto_schema
from rest_framework.decorators import action
from rest_framework.response import Response

from area.serializers import AreaSelectSerializer


class AreaSelectMixin:
    @swagger_auto_schema(
        responses={200: AreaSelectSerializer(many=True)}
    )
    @action(
        detail=False,
        methods=['get'],
        pagination_class=None
    )
    def select(self, request):
        queryset = self.get_queryset().only('id', 'name', 'code').annotate(
            value=F('id'),
            label=F('name')
        ).values('value', 'label', 'code')
        filtered_queryset = self.filter_queryset(queryset)
        return Response(filtered_queryset)
