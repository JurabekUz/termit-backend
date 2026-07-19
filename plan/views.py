from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from django.utils.translation import gettext_lazy as _

from account.models import UserRoles
from account.permissions import IsCenterDirector
from config.utils import CommonException
from damaged_object.models import DamagedStatus
from notification.models import ModuleChoices
from notification.services import increment_counter_on_plan_checking, decrement_counter_on_retrieve
from plan.filters import PlanFilter
from plan.models import Plan, PlanStatus
from plan.serializers import PlanSerializer, PlanListSerializer, PlanRetrieveSerializer, PlanCheckSerializer


class PlanViewSet(ModelViewSet):
    queryset = Plan.objects.all()
    serializer_class = PlanSerializer
    filterset_class = PlanFilter
    search_fields = ('name',)

    def get_queryset(self):
        user = self.request.user
        queryset = self.queryset
        if user.role in (UserRoles.ADMIN, UserRoles.CM):
            return queryset
        elif user.role == UserRoles.CD:
            queryset = queryset.exclude(status=PlanStatus.draft)
        elif user.role == UserRoles.RM:
            queryset = queryset.filter(
                region_statuses__region=user.region,
                status__in=[PlanStatus.approved, PlanStatus.in_process, PlanStatus.completed]
            )
        else:
            queryset = queryset.none()
        return queryset

    def get_serializer_class(self):
        if self.action == 'list':
            return PlanListSerializer
        elif self.action == 'retrieve':
            return PlanRetrieveSerializer
        return self.serializer_class

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        user = request.user
        if instance.status != PlanStatus.draft and user.role == UserRoles.RM:
            if instance.region_statuses.filter(status=PlanStatus.approved, region_id=user.region_id).exists():
                # update plan-region-status
                instance.update_region_status(region_id=user.region_id)

                for item in instance.items.filter(item__district__region=user.region_id, is_performed=False):
                    damaged_object = item.item
                    # update damaged object status
                    damaged_object.update_status(status=DamagedStatus.in_process, plan_item_id=item.id)

            # update plan status
            instance.status = PlanStatus.in_process
            instance.save(update_fields=['status'])

        # update notification counter
        decrement_counter_on_retrieve(instance, request.user, ModuleChoices.plan)

        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(
        detail=True, methods=['POST'], url_path='check',
        permission_classes=[IsCenterDirector],
        serializer_class=PlanCheckSerializer
    )
    def check(self, request, pk=None):
        instance = self.get_object()
        if instance.status != PlanStatus.new:
            raise CommonException(_('This object is already checked'))
        serializer = self.get_serializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        # update notification counter
        region_ids = [item.region_id for item in instance.region_statuses.all()]
        increment_counter_on_plan_checking(
            status=serializer.validated_data['status'], region_ids=region_ids)
        return Response(serializer.data)
