from rest_framework.generics import DestroyAPIView, GenericAPIView
from rest_framework.response import Response

from baseapp.mixins import SoftDeleteMixin, SelectMixin
from baseapp.serializers import SelectSerializer


class BaseDestroyAPIView(SoftDeleteMixin, DestroyAPIView):
    pass


class BaseSelectAPIView(SelectMixin, GenericAPIView):
    pagination_class = None
    serializer_class = SelectSerializer

    def get(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(serializer.data)


