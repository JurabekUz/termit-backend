from django.db import transaction
from django.utils import translation
from rest_framework.decorators import action
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from django.utils.translation import gettext_lazy as _

from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema

from account.models import UserRoles
from account.permissions import IsRegionalManager, IsCenterDirector, IsCenterManager
from baseapp.integrations import get_cadastres_info_by_pin
from config.utils import CommonException
from damaged_object.filters import MahallaInfoFilter, OpenAreaInfoFilter, filter_is_free, FreeDamagedObjectFilter
from damaged_object.models import MahallaInfo, OpenAreaInfo, DamagedStatus, DamagedObject
from damaged_object.serializers import (
    MahallaInfoSerializer, MahallaInfoListSerializer, MahallaInfoRetrieveSerializer, MahallaInfoCheckSerializer,
    OpenAreaInfoSerializer, OpenAreaInfoListSerializer, OpenAreaInfoRetrieveSerializer,
    OpenAreaInfoCheckSerializer, DamagedObjectFreeListSerializer

)
from damaged_object.services import mahalla_status_statistics, object_statistics, object_statistics_by_types, \
    open_area_statistics, get_cadastral_object
from notification.models import ModuleChoices
from notification.services import increment_counter_on_damaged_object_checking, decrement_counter_on_retrieve
from plan.models import PlanStatus
from plan.serializers import PlanItemUpdateSerializer


class MahallaInfoViewSet(ModelViewSet):
    queryset = MahallaInfo.objects.filter(status__isnull=False)
    serializer_class = MahallaInfoSerializer
    filterset_class = MahallaInfoFilter
    search_fields = ('cadastral_number', 'address')
    http_method_names = ('get', 'post')

    def get_queryset(self):
        user = self.request.user
        queryset = self.queryset
        if user.role == UserRoles.RM:
            queryset = queryset.filter(district__region_id=user.region_id)
        elif user.role == UserRoles.LE:
            queryset = queryset.filter(appeal__sender_id=user.id)

        if self.action == 'list':
            queryset = queryset.select_related(
                'district', 'mahalla', 'created_by').defer(
                'mahalla__coordinates', 'district__coordinates')
        elif self.action == 'retrieve':
            queryset = queryset.select_related(
                'district', 'mahalla').prefetch_related(
                'images', 'videos', 'flows'
            )
        return queryset

    def get_serializer_class(self):
        if self.action == 'list':
            return MahallaInfoListSerializer
        elif self.action == 'retrieve':
            return MahallaInfoRetrieveSerializer
        return self.serializer_class

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # update notification counter
        decrement_counter_on_retrieve(instance, request.user, ModuleChoices.mahalla)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


    @action(
        detail=True, methods=['POST'], url_path='check',
        permission_classes=[IsCenterDirector],
        serializer_class=MahallaInfoCheckSerializer
    )
    def check(self, request, pk=None):
        instance = self.get_object()
        if instance.status != DamagedStatus.new:
            raise CommonException(_('This object is already checked'))
        serializer = MahallaInfoCheckSerializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)

    @action(
        detail=True, methods=['POST'], url_path='take-action',
        permission_classes=[IsRegionalManager],
        serializer_class=PlanItemUpdateSerializer
    )
    def take_action(self, request, pk=None):
        instance = self.get_object()
        plan_item = instance.plan_items.filter(plan__status=PlanStatus.in_process).first()
        if not plan_item:
            raise CommonException(_('This object is not in process'))
        if instance.status != DamagedStatus.in_process:
            raise CommonException(_('This object is already checked'))
        serializer = PlanItemUpdateSerializer(instance=plan_item, data=request.data, partial=False)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            serializer.validated_data['is_performed'] = True
            serializer.validated_data['performer'] = request.user
            serializer.save()
            instance.update_status(DamagedStatus.completed, plan_item.id)

            # update region status
            if not instance.plan_items.filter(is_performed=False).exclude(id=plan_item.id).exists():
                plan = plan_item.plan
                region_status = plan.region_statuses.filter(region_id=instance.district.region_id).first()
                region_status.status = PlanStatus.completed
                region_status.save()

        return Response(serializer.data)


class OpenAreaInfoViewSet(ModelViewSet):
    queryset = OpenAreaInfo.objects.filter(status__isnull=False)
    serializer_class = OpenAreaInfoSerializer
    filterset_class = OpenAreaInfoFilter
    search_fields = ('address',)
    http_method_names = ('get', 'post')

    def get_queryset(self):
        user = self.request.user
        queryset = self.queryset
        if user.role == UserRoles.RM:
            queryset = queryset.filter(district__region_id=user.region_id)
        elif user.role == UserRoles.LE:
            queryset = queryset.filter(appeal__sender_id=user.id)

        if self.action == 'list':
            queryset = queryset.select_related(
                'district', 'area_type', 'created_by').defer(
                'coordinates', 'district__coordinates')
        elif self.action == 'retrieve':
            queryset = queryset.select_related(
                'district', 'area_type').prefetch_related(
                'images', 'flows'
            )

        return queryset

    def get_serializer_class(self):
        if self.action == 'list':
            return OpenAreaInfoListSerializer
        elif self.action == 'retrieve':
            return OpenAreaInfoRetrieveSerializer
        return self.serializer_class

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # update notification counter
        decrement_counter_on_retrieve(instance, request.user, ModuleChoices.open_area)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(
        detail=True, methods=['POST'], url_path='check',
        permission_classes=[IsCenterDirector],
        serializer_class=OpenAreaInfoCheckSerializer
    )
    def check(self, request, pk=None):
        instance = self.get_object()
        if instance.status != DamagedStatus.new:
            raise CommonException(_('This object is already checked'))
        serializer = self.get_serializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            serializer.save()
            if serializer.validated_data['status'] == DamagedStatus.approved:
                instance.create_flow(status=DamagedStatus.approved)
            increment_counter_on_damaged_object_checking(
                status=serializer.validated_data['status'],
                region_id=instance.district.region_id,
                module=ModuleChoices.open_area
            )
        return Response(serializer.data)

    @action(
        detail=True, methods=['POST'], url_path='take-action',
        permission_classes=[IsRegionalManager],
        serializer_class=PlanItemUpdateSerializer
    )
    def take_action(self, request, pk=None):
        instance = self.get_object()
        plan_item = instance.plan_items.first()
        if instance.status != DamagedStatus.in_process:
            raise CommonException(_('This object is already checked'))
        serializer = PlanItemUpdateSerializer(plan_item, data=request.data, partial=False)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            serializer.validated_data['is_performed'] = True
            serializer.validated_data['performer'] = request.user
            serializer.save()
            instance.update_status(DamagedStatus.completed)
        return Response(serializer.data)


class FreeDamagedObjectsListView(ListAPIView):
    queryset = DamagedObject.objects.filter(
        status=DamagedStatus.approved).select_related('district').prefetch_related('mahallainfo', 'openareainfo')
    serializer_class = DamagedObjectFreeListSerializer
    filterset_class = FreeDamagedObjectFilter
    search_fields = ('mahallainfo__cadastral_number', 'mahallainfo__address', 'openareainfo__address')
    permission_classes = [IsCenterManager]

    def get_queryset(self):
        return filter_is_free(self.queryset, 'is_free', True)


class MahallaStatusStatView(APIView):

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter('region', openapi.IN_QUERY, description="region code", type=openapi.TYPE_INTEGER)
        ]
    )
    def get(self, request, *args, **kwargs):
        translation.activate(request.LANGUAGE_CODE)
        region_code = request.query_params.get('region', '')
        region_code = int(region_code) if region_code.isdigit() else None
        user = request.user
        if user.role == UserRoles.RM:
            region_code = user.region.code
        data = mahalla_status_statistics(region_code=region_code)
        return Response(data=data, status=200)


class ObjectStatView(APIView):

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter('region', openapi.IN_QUERY, description="region code", type=openapi.TYPE_INTEGER),
            openapi.Parameter('district', openapi.IN_QUERY, description="district code", type=openapi.TYPE_INTEGER),
            openapi.Parameter('type', openapi.IN_QUERY, description="type", type=openapi.TYPE_STRING,
                              enum=['households', 'social_objects', 'historical_sites', 'adm_buildings']),
        ]
    )
    def get(self, request, *args, **kwargs):
        translation.activate(request.LANGUAGE_CODE)
        region_code = request.query_params.get('region', '')
        district_code = request.query_params.get('district', '')
        type_label = request.query_params.get('type', '')

        region_code = int(region_code) if region_code.isdigit() else None
        district_code = int(district_code) if district_code.isdigit() else None
        user = request.user
        if user.role == UserRoles.RM:
            region_code = user.region.code

        if type_label:
            type_labels = ['households', 'social_objects', 'historical_sites', 'adm_buildings']
            if type_label not in type_labels:
                raise CommonException(_('Invalid type'))
            data = object_statistics_by_types(region_code=region_code, district_code=district_code, type_label=type_label)
        else:
            data = object_statistics(region_code=region_code, district_code=district_code)
        return Response(data=data, status=200)


class OpenAreaStatusStatView(APIView):

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter('region', openapi.IN_QUERY, description="region code", type=openapi.TYPE_INTEGER)
        ]
    )
    def get(self, request, *args, **kwargs):
        translation.activate(request.LANGUAGE_CODE)
        region_code = request.query_params.get('region', '')
        region_code = int(region_code) if region_code.isdigit() else None
        user = request.user
        if user.role == UserRoles.RM:
            region_code = user.region.code
        data = open_area_statistics(region_code=region_code)
        return Response(data=data, status=200)


class CadastralObjectView(APIView):

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter('cadastral_number',
                openapi.IN_QUERY, description="cadastral number", type=openapi.TYPE_STRING)
        ]
    )
    def get(self, request, *args, **kwargs):
        translation.activate(request.LANGUAGE_CODE)
        cadastral_number = request.query_params.get('cadastral_number')
        if not cadastral_number:
            raise CommonException(_('Cadastral number is required'))

        # validate damaged object
        if MahallaInfo.objects.filter(cadastral_number=cadastral_number).exclude(
            status__in=[DamagedStatus.rejected, DamagedStatus.completed, DamagedStatus.cleaned, None]
        ).exists():
            raise CommonException(
                _("This cadastral digital object was previously included and work on it has not yet been completed."))

        data = get_cadastral_object(number=cadastral_number, user=request.user)
        return Response(data=data, status=200)


class CadastralNumbersView(APIView):

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter('pinfl',
                openapi.IN_QUERY, description="PINFL", type=openapi.TYPE_STRING)
        ]
    )
    def get(self, request, *args, **kwargs):
        translation.activate(request.LANGUAGE_CODE)
        pinfl = request.query_params.get('pinfl')

        if request.user.role != UserRoles.RM:
            raise CommonException("You have not permission")

        if not pinfl:
            raise CommonException(_('PINFL is required'))
        data = get_cadastres_info_by_pin(pinfl)
        return Response(data=data, status=200)
