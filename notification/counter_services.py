from django.db.models import Count

from appeal.models import Appeal, AppealStatus
from damaged_object.models import DamagedObject, DamagedTypes, DamagedStatus
from notification.models import ModuleChoices
from plan.models import Plan, PlanStatus


def plan_region_user_counter(user):
    number = Plan.objects.filter(
        region_statuses__region=user.region,
        status=PlanStatus.approved
    ).distinct().count()

    data = {
        'module': ModuleChoices.plan,
        'number': number,
        'counters': [{
            "status": PlanStatus.approved,
            "number": number
        }]
    }
    return data


def appeal_region_user_counter(user):
    queryset = Appeal.objects.filter(
        district__region=user.region,
        status__in=[
            AppealStatus.new,
            AppealStatus.approved
        ]
    )
    grouped_queryset = queryset.values('status').annotate(number=Count('id'))
    rej_number = Appeal.objects.filter(status=AppealStatus.rejected, unread=True, district__region=user.region).count()
    grouped_queryset = list(grouped_queryset)
    grouped_queryset.append({'status': AppealStatus.rejected, 'number': rej_number})
    data = {
        'module': ModuleChoices.appeal,
        'number': queryset.count() + rej_number,
        'counters': [
            {
                'status': item['status'],
                'number': item['number']
            }
            for item in grouped_queryset
        ]
    }
    return data


def damaged_objects_region_user_counter(user):
    open_area_qs = DamagedObject.objects.filter(type=DamagedTypes.open_area, district__region=user.region)
    open_area_grouped_qs = open_area_qs.filter(
        status__in=[
            DamagedStatus.new,
            DamagedStatus.approved
        ]
    )
    open_area_grouped = open_area_grouped_qs.values('status').annotate(number=Count('id'))
    rej_number = open_area_qs.filter(status=DamagedStatus.rejected, unread=True).count()
    open_area_grouped = list(open_area_grouped)
    open_area_grouped.append({'status': DamagedStatus.rejected, 'number': rej_number})
    open_area_number = open_area_grouped_qs.count() + rej_number
    open_area_data = {
        'module': ModuleChoices.open_area,
        'number': open_area_number,
        'counters': [
            {
                'status': item['status'],
                'number': item['number']
            }
            for item in open_area_grouped
        ]
    }

    mahalla_qs = DamagedObject.objects.filter(type=DamagedTypes.mahalla).filter(
        district__region=user.region,
        status__in=[
            DamagedStatus.new,
            DamagedStatus.approved
        ]
    )
    mahalla_grouped = mahalla_qs.values('status').annotate(number=Count('id'))
    rej_number = DamagedObject.objects.filter(type=DamagedTypes.mahalla).filter(
        district__region=user.region,
        status=DamagedStatus.rejected
    ).count()
    mahalla_grouped = list(mahalla_grouped)
    mahalla_grouped.append({'status': DamagedStatus.rejected, 'number': rej_number})
    mahalla_number = mahalla_qs.count() + rej_number
    mahalla_data = {
        'module': ModuleChoices.mahalla,
        'number': mahalla_number,
        'counters': [
            {
                'status': item['status'],
                'number': item['number']
            }
            for item in mahalla_grouped
        ]
    }

    data = {
        'module': 'damaged_object',
        'number': open_area_number + mahalla_number,
        'counters': [open_area_data, mahalla_data]
    }
    return data


def appeal_legal_user_counter(user):
    queryset = Appeal.objects.filter(
        sender=user,
        status__in=[
            AppealStatus.new,
            AppealStatus.approved
        ]
    )
    grouped_queryset = queryset.values('status').annotate(number=Count('id'))
    rej_number = Appeal.objects.filter(sender=user, status=AppealStatus.rejected, unread=True).count()
    grouped_list = list(grouped_queryset)
    grouped_list.append({'status': AppealStatus.rejected, 'number': rej_number})
    data = {
        'module': ModuleChoices.appeal,
        'number': queryset.count(),
        'counters': [
            {
                'status': item['status'],
                'number': item['number']
            }
            for item in grouped_list
        ]
    }
    return data


def plan_center_user_counter():
    app_number = Plan.objects.filter(status=PlanStatus.approved).count()
    rej_number = Plan.objects.filter(status=PlanStatus.rejected, unread=True).count()


    data = {
        'module': ModuleChoices.plan,
        'number': app_number + rej_number,
        'counters': [
            {
                "status": PlanStatus.approved,
                "number": app_number
            },
            {
                "status": PlanStatus.rejected,
                "number": rej_number
            }
        ]
    }
    return data


def plan_director_user_counter():
    new_number = Plan.objects.filter(status=PlanStatus.new).count()
    app_number = Plan.objects.filter(status=PlanStatus.approved).count()

    data = {
        'module': ModuleChoices.plan,
        'number': new_number + app_number,
        'counters': [
            {
                "status": PlanStatus.new,
                "number": new_number
            },
            {
                "status": PlanStatus.approved,
                "number": app_number
            }
        ]
    }
    return data


def appeal_director_user_counter():
    number = Appeal.objects.filter(status=AppealStatus.new).count()
    data = {
        'module': ModuleChoices.appeal,
        'number': number,
        'counters': [
            {
                "status": AppealStatus.new,
                "number": number
            }
        ]
    }
    return data


def damaged_object_director_user_counter():
    area_number = DamagedObject.objects.filter(type=DamagedTypes.open_area, status=DamagedStatus.new).count()
    mahalla_number = DamagedObject.objects.filter(type=DamagedTypes.mahalla, status=DamagedStatus.new).count()

    open_area_data = {
        'module': ModuleChoices.open_area,
        'number': area_number,
        'counters': [
            {
                'status': DamagedStatus.new,
                'number': area_number
            }
        ]
    }

    mahalla_data = {
        'module': ModuleChoices.mahalla,
        'number': mahalla_number,
        'counters': [
            {
                'status': DamagedStatus.new,
                'number': mahalla_number
            }
        ]
    }

    data = {
        'module': 'damaged_object',
        'number': area_number + mahalla_number,
        'counters': [open_area_data, mahalla_data]
    }

    return data
