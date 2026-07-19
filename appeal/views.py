from django.db import transaction
from rest_framework.generics import ListAPIView, CreateAPIView, RetrieveAPIView, GenericAPIView
from django.utils.translation import gettext_lazy as _
from rest_framework.response import Response

from account.models import UserRoles
from account.permissions import IsCenterDirector, IsRegionalManager, IsLegalEntity
from appeal.filters import AppealFilter
from appeal.mixins import AppealQuerysetMixin
from appeal.models import Appeal, AppealStatus
from appeal.serializers import (
    AppealListSerializer,
    AppealMahallaSerializer, AppealMahallaRetrieveSerializer,
    AppealOpenAreaSerializer, AppealOpenAreaRetrieveSerializer,
    AppealMahallaObjectRetrieveSerializer, AppealOpenAreaObjectRetrieveSerializer, AppealDamagedObjectCheckSerializer,
    AppealCheckSerializer
)
from config.utils import CommonException
from damaged_object.models import MahallaInfo, OpenAreaInfo, DamagedObject, AppealObjectStatus, DamagedStatus
from notification.models import ModuleChoices
from notification.services import increment_counter_on_appeal_sending, increment_counter_on_appeal_checking, \
    increment_counter_on_appeal_damaged_object_checking, decrement_counter_on_retrieve

''' Appeals '''


class AppealListView(AppealQuerysetMixin, ListAPIView):
    queryset = Appeal.objects.all().select_related(
        'district__region'
    )
    serializer_class = AppealListSerializer
    filterset_class = AppealFilter

    def get_queryset(self):
        queryset = self.queryset
        user = self.request.user
        if user.role == UserRoles.RM:
            queryset = queryset.filter(district__region_id=user.region_id)
        elif user.role == UserRoles.LE:
            queryset = queryset.filter(sender=user)
        elif user.role == UserRoles.ME:
            queryset = queryset.none()
        else:
            queryset = queryset.filter(status__in=[AppealStatus.sent, AppealStatus.approved, AppealStatus.rejected])
        return queryset


class AppealObjectCheckingView(GenericAPIView):
    queryset = DamagedObject.objects.filter(appeal__isnull=False)
    serializer_class = AppealDamagedObjectCheckSerializer
    permission_classes = [IsRegionalManager]

    def post(self, request, pk):
        instance = self.get_object()
        if instance.apl_status != AppealObjectStatus.apl_new:
            raise CommonException(_('This object is already checked'))
        serializer = self.get_serializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.validated_data['created_by'] = request.user
        with transaction.atomic():
            serializer.save()
            appeal = instance.appeal
            # if instance is first objects, update appeal status to in process
            if appeal.status != AppealStatus.in_process:
                appeal.status = AppealStatus.in_process
                appeal.save(update_fields=['status'])

            # if all objects are checked, update appeal status
            if not appeal.damaged_objects.filter(
                    apl_status=AppealObjectStatus.apl_new
            ).exclude(id=instance.id).exists():
                appeal.status = AppealStatus.sent
                appeal.save(update_fields=['status'])
                increment_counter_on_appeal_sending()
        return Response(serializer.data)


class AppealCheckingView(GenericAPIView):
    queryset = Appeal.objects.all()
    serializer_class = AppealCheckSerializer
    permission_classes = [IsCenterDirector]

    def post(self, request, pk):
        instance = self.get_object()
        if instance.status != AppealStatus.sent:
            raise CommonException(_('This object is already checked'))
        serializer = self.get_serializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        status = serializer.validated_data['status']
        with transaction.atomic():
            serializer.save()
            # if appeal is approved, update damaged objects status
            if status == AppealStatus.approved:
                damaged_objects = list(instance.damaged_objects.all())
                for obj in damaged_objects:
                    obj.status = (
                        DamagedStatus.approved
                        if obj.apl_status == AppealObjectStatus.apl_approved else
                        DamagedStatus.rejected
                    )
                DamagedObject.objects.bulk_update(damaged_objects, ['status'])

                # update counter
                approved_number = 0
                rejected_number = 0
                for i in damaged_objects:
                    if i.apl_status == AppealObjectStatus.apl_approved:
                        approved_number += 1
                    else:
                        rejected_number += 1
                increment_counter_on_appeal_damaged_object_checking(
                    region_id=instance.district.region_id,
                    damaged_type=instance.damaged_type,
                    appeal_sender=instance.sender,
                    approved_number=approved_number,
                    rejected_number=rejected_number
                )
            else:
                damaged_objects = list(instance.damaged_objects.all())
                for obj in damaged_objects:
                    obj.status = DamagedStatus.rejected
                DamagedObject.objects.bulk_update(damaged_objects, ['status'])


            # update notification counter for appeal module
            increment_counter_on_appeal_checking(
                status=status,
                region_id=instance.district.region_id,
                appeal_sender=instance.sender
            )
        return Response(serializer.data)


''' Mahalla Appeals '''


class AppealMahallaCreateView(CreateAPIView):
    serializer_class = AppealMahallaSerializer
    permission_classes = [IsLegalEntity]


class AppealMahallaRetrieveView(AppealQuerysetMixin, RetrieveAPIView):
    queryset = Appeal.objects.select_related('district__region').prefetch_related(
        'damaged_objects__mahallainfo'
    )
    serializer_class = AppealMahallaRetrieveSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # update notification counter
        decrement_counter_on_retrieve(instance, request.user, ModuleChoices.appeal)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class AppealMahallaObjectRetrieveView(RetrieveAPIView):
    queryset = MahallaInfo.objects.select_related('district', 'mahalla').prefetch_related(
        'images', 'videos', 'apl_images'
    )
    serializer_class = AppealMahallaObjectRetrieveSerializer


''' Open Area Appeals '''


class AppealOpenAreaCreateView(CreateAPIView):
    serializer_class = AppealOpenAreaSerializer
    permission_classes = [IsLegalEntity]


class AppealOpenAreaRetrieveView(AppealQuerysetMixin, RetrieveAPIView):
    queryset = Appeal.objects.select_related('district__region').prefetch_related(
        'damaged_objects__openareainfo__area_type'
    ).defer('damaged_objects__openareainfo__coordinates')
    serializer_class = AppealOpenAreaRetrieveSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # update notification counter
        decrement_counter_on_retrieve(instance, request.user, ModuleChoices.appeal)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class AppealOpenAreaObjectRetrieveView(RetrieveAPIView):
    queryset = OpenAreaInfo.objects.select_related('district', 'area_type').prefetch_related(
        'images', 'videos', 'apl_images'
    )
    serializer_class = AppealOpenAreaObjectRetrieveSerializer


