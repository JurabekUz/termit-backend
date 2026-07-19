from django.db.models import Sum, Count
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework.views import APIView
from rest_framework.response import Response

from account.models import UserRoles
from appeal.models import Appeal, AppealStatus
from notification.counter_services import plan_region_user_counter, appeal_region_user_counter, \
    damaged_objects_region_user_counter, appeal_legal_user_counter, plan_center_user_counter, \
    plan_director_user_counter, appeal_director_user_counter, damaged_object_director_user_counter
from notification.models import NotificationCounter, ModuleChoices
from plan.models import Plan, PlanStatus
from damaged_object.models import DamagedObject, DamagedStatus, DamagedTypes


class NotificationCounterView(APIView):

    def get(self, request):
        """
        response format:
            [
                {
                    'module': module name,
                    'number': number,
                    'counters': [
                        {"status": status_value, "number": number}
                    ]
                },
                ...
            ]
        """
        user = request.user
        response = []

        if user.role == UserRoles.RM:  # regional manager
            # plans
            plan_data = plan_region_user_counter(user)
            response.append(plan_data)

            # appeals
            appeal_data = appeal_region_user_counter(user)
            response.append(appeal_data)

            # damaged objects
            damaged_data = damaged_objects_region_user_counter(user)
            response.append(damaged_data)
        elif user.role == UserRoles.LE:  # legal user
            appeal_data = appeal_legal_user_counter(user)
            response.append(appeal_data)
        elif user.role == UserRoles.CM:  # center manager
            plan_data = plan_center_user_counter()
            response.append(plan_data)
        elif user.role == UserRoles.CD:  # center director
            # plans
            plan_data = plan_director_user_counter()
            response.append(plan_data)

            # appeals
            appeal_data = appeal_director_user_counter()
            response.append(appeal_data)

            # damaged objects
            damaged_data = damaged_object_director_user_counter()
            response.append(damaged_data)


        # data = []
        # for module in [ModuleChoices.plan, ModuleChoices.appeal]:
        #     number = queryset.filter(module=module).aggregate(number=Sum('number'))['number']
        #     counters = queryset.filter(module=module).values('status', 'number')
        #     data.append(
        #      {
        #          'module': module,
        #          'number': number,
        #          'counters': counters
        #      }
        #     )
        #
        # # damaged objects
        # damaged_modules = [ModuleChoices.mahalla, ModuleChoices.open_area]
        # damaged_counters_data = []
        # for module in damaged_modules:
        #     number = queryset.filter(module=module).aggregate(number=Sum('number'))['number']
        #     counters = queryset.filter(module=module).values('status', 'number')
        #     damaged_counters_data.append(
        #      {
        #          'module': module,
        #          'number': number,
        #          'counters': counters
        #      }
        #     )
        # number = queryset.filter(module__in=damaged_modules).aggregate(number=Sum('number'))['number']
        # data.append(
        #     {
        #         'module': 'damaged_object',
        #         'number': number,
        #         'counters': damaged_counters_data
        #     }
        # )

        return Response(response)

    # @swagger_auto_schema(
    #     manual_parameters=[
    #         openapi.Parameter(
    #             'module', openapi.IN_QUERY, description="module", type=openapi.TYPE_STRING
    #         ),
    #         openapi.Parameter(
    #             'status', openapi.IN_QUERY, description="status", type=openapi.TYPE_STRING
    #         )
    #     ]
    # )
    # def post(self, request):
    #     user = request.user
    #     module = request.query_params.get('module')
    #     status = request.query_params.get('status')
    #     NotificationCounter.objects.filter(user=user, module=module, status=status).update(number=0)
    #     return Response(status=200)
