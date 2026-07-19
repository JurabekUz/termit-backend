from django.shortcuts import get_object_or_404
from django.utils import translation
from rest_framework.decorators import action
from rest_framework.mixins import RetrieveModelMixin, UpdateModelMixin, ListModelMixin
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet, GenericViewSet, ModelViewSet
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema

from account.models import UserRoles
from baseapp.mixins import FilteredSelectMixin, DistrictQuerysetMixin, RegionQuerysetMixin
from scripts.region import load_region, district_geojson, load_mahalla
from .filters import DistrictFilter, MahallaFilter, OpenAreaFilter
from .mixins import AreaSelectMixin
from .models import Region, District, Mahalla, OpenArea
from .serializers import (
    RegionListSerializer, RegionRetrieveSerializer,
    DistrictListSerializer, DistrictRetrieveSerializer,
    MahallaUpdateSerializer, MahallaListSerializer, MahallaRetrieveSerializer,
    OpenAreaSerializer, OpenAreaUpdateRetrieveSerializer, MahallaStatusWithCoordinatesSerializer, AreaSelectSerializer
)
from .services import number_statistics, area_statistics, area_damaged_status


# Create your views here.

class LoadRegionApiView(APIView):
    def get(self, request, format=None):
        count = load_region()
        return Response({
            "count": count
        })

class LoadDistrictApiView(APIView):
    def get(self, request, format=None):
        count = district_geojson()
        return Response({
            "count": count
        })


class LoadMahallaApiView(APIView):
    def get(self, request, format=None):
        count = load_mahalla()
        return Response({
            "count": count
        })


class RegionViewSet(AreaSelectMixin, ReadOnlyModelViewSet):
    queryset = Region.objects.all()
    search_fields = ('name',)

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return RegionRetrieveSerializer
        return RegionListSerializer

    def get_queryset(self):
        if self.action == 'retrieve':
            return self.queryset.defer(None)
        return self.queryset


class DistrictViewSet(AreaSelectMixin,
                      RegionQuerysetMixin,
                      ReadOnlyModelViewSet):
    queryset = District.objects.all()
    filterset_class = DistrictFilter
    search_fields = ('name',)

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return DistrictRetrieveSerializer
        return DistrictListSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action == 'list':
            queryset = queryset.select_related('region').defer('coordinates', 'region__coordinates')
        elif self.action == 'retrieve':
            queryset = queryset.select_related('region').defer('region__coordinates')
        return queryset

    @action(detail=True, methods=['get'], url_path='mahalla-status',
            serializer_class=MahallaStatusWithCoordinatesSerializer)
    def mahalla_with_status(self, request, pk, *args, **kwargs):
        instance = self.get_object()
        serializer = MahallaStatusWithCoordinatesSerializer(instance.mahalla_set.all(), many=True)
        return Response(serializer.data, status=200)


class DistrictRetrieveView(APIView):
    def get(self, request, code, *args, **kwargs):
        instance = get_object_or_404(District, code=code)
        serializer = DistrictRetrieveSerializer(instance)
        return Response(serializer.data, status=200)


class MahallaStatusView(APIView):
    def get(self, request, code, *args, **kwargs):
        instance = get_object_or_404(District, code=code)
        serializer = MahallaStatusWithCoordinatesSerializer(instance.mahalla_set.all(), many=True)
        return Response(serializer.data, status=200)


class MahallaViewSet(AreaSelectMixin,
                     DistrictQuerysetMixin,
                     RetrieveModelMixin,
                     UpdateModelMixin,
                     ListModelMixin,
                     GenericViewSet):
    queryset = Mahalla.objects.all()
    filterset_class = MahallaFilter
    search_fields = ('name', )

    def get_serializer_class(self):
        if self.action in ['partial_update', 'update']:
            return MahallaUpdateSerializer
        elif self.action == 'retrieve':
            return MahallaRetrieveSerializer
        return MahallaListSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action == 'list':
            queryset = queryset.select_related('district').defer('coordinates', 'district__coordinates')
        elif self.action == 'retrieve':
            queryset = queryset.select_related('district').defer('district__coordinates')
        elif self.action in ('partial_update', 'update'):
            queryset = queryset.defer(None)
        return queryset


class OpenAreaViewSet(DistrictQuerysetMixin, ModelViewSet):
    queryset = OpenArea.objects.all()
    serializer_class = OpenAreaSerializer
    filterset_class = OpenAreaFilter
    search_fields = ('district__name',)
    http_method_names = ('get', 'patch')

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action == 'list':
            queryset = queryset.select_related('district').defer(
                'district__coordinates',
            )
        if self.action == 'retrieve':
            queryset = queryset.select_related('district__region').defer(
                'district__region__coordinates',
            )
        return queryset

    # def get_serializer_class(self):
    #     if self.action in ('list', 'create'):
    #         return OpenAreaSerializer
    #     return OpenAreaUpdateRetrieveSerializer


""" Integration views """


class CadastreInfo(APIView):

    def get(self, request):

        return



""" Statistic views """


class NumberStatView(APIView):

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter('region', openapi.IN_QUERY, description="region code", type=openapi.TYPE_INTEGER),
            openapi.Parameter('district', openapi.IN_QUERY, description="district code", type=openapi.TYPE_INTEGER),
            openapi.Parameter('mahalla', openapi.IN_QUERY, description="mahalla code", type=openapi.TYPE_INTEGER)
        ]
    )
    def get(self, request, *args, **kwargs):
        translation.activate(request.LANGUAGE_CODE)
        region_code = request.query_params.get('region', '')
        district_code = request.query_params.get('district', '')
        mahalla_code = request.query_params.get('mahalla', '')

        region_code = int(region_code) if region_code.isdigit() else None
        district_code = int(district_code) if district_code.isdigit() else None
        mahalla_code = int(mahalla_code) if mahalla_code.isdigit() else None

        user = request.user
        if user.role == UserRoles.RM:
            region_code = user.region.code

        data = number_statistics(
            mahalla_code=mahalla_code,
            district_code=district_code,
            region_code=region_code
        )
        return Response(data=data, status=200)


class AreaStatView(APIView):
    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter('region', openapi.IN_QUERY, description="region code", type=openapi.TYPE_INTEGER),
            openapi.Parameter('district', openapi.IN_QUERY, description="district code", type=openapi.TYPE_INTEGER)
        ]
    )
    def get(self, request, *args, **kwargs):
        translation.activate(request.LANGUAGE_CODE)
        region_code = request.query_params.get('region', '')
        district_code = request.query_params.get('district', '')

        region_code = int(region_code) if region_code.isdigit() else None
        district_code = int(district_code) if district_code.isdigit() else None

        user = request.user
        if user.role == UserRoles.RM:
            region_code = user.region.code

        data = area_statistics(
            district_code=district_code,
            region_code=region_code
        )
        return Response(data=data, status=200)


class AreaDamagedStatusView(APIView):
    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter('region', openapi.IN_QUERY, description="region code", type=openapi.TYPE_INTEGER),
        ]
    )
    def get(self, request, *args, **kwargs):
        translation.activate(request.LANGUAGE_CODE)
        region_code = request.query_params.get('region', '')

        region_code = int(region_code) if region_code.isdigit() else None

        user = request.user
        if user.role == UserRoles.RM:
            region_code = user.region.code

        data = area_damaged_status(
            region_code=region_code
        )
        return Response(data=data, status=200)
