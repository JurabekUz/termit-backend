from rest_framework.generics import CreateAPIView, DestroyAPIView
from rest_framework.response import Response
from rest_framework.status import HTTP_201_CREATED, HTTP_400_BAD_REQUEST
from rest_framework.viewsets import ModelViewSet

from account.permissions import IsAdminOrReadOnly
from .models import Ministry, OpenAreaType, Media
from .serializers import MinistrySerializer, OpenAreaTypeSerializer, MediaSerializer
from baseapp.mixins import SoftDeleteMixin, SelectMixin


class MinistryViewSet(SelectMixin, SoftDeleteMixin, ModelViewSet):
    queryset = Ministry.objects.filter(is_active=True)
    serializer_class = MinistrySerializer
    permission_classes = [IsAdminOrReadOnly]


class OpenAreaTypeViewSet(SelectMixin, SoftDeleteMixin, ModelViewSet):
    queryset = OpenAreaType.objects.filter(is_active=True)
    serializer_class = OpenAreaTypeSerializer
    permission_classes = [IsAdminOrReadOnly]


class MediaCreateView(CreateAPIView):
    queryset = Media.objects.all()
    serializer_class = MediaSerializer

    def create(self, request, *args, **kwargs):
        files = request.FILES.getlist('file')
        media_objects = []

        for file in files:
            media_data = {'file': file}
            serializer = MediaSerializer(data=media_data, context={'request': request})
            if serializer.is_valid():
                serializer.save()
                media_objects.append(serializer.data)
            else:
                return Response(serializer.errors, status=HTTP_400_BAD_REQUEST)

        return Response(media_objects, status=HTTP_201_CREATED)


class MediaDestroyView(DestroyAPIView):
    queryset = Media.objects.all()
