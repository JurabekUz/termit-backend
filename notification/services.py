from typing import Literal

from django.db.models import Q

from account.models import CustomUser, UserRoles
from damaged_object.models import DamagedStatus, DamagedTypes
from notification.models import NotificationCounter, ModuleChoices
from plan.models import PlanStatus
from appeal.models import AppealStatus


def increment_counter(users, module, status, number: int = 1):
    """
    Increments the notification counter for each user in the given list
    for the specified module and status.

    Parameters:
        users (QuerySet): List of CustomUser objects.
        module (ModuleChoices): The module for which the counter is updated.
        status (Status): The status associated with the notification.
        number (int):
    """
    for user in users:
        counter, created = NotificationCounter.objects.get_or_create(
            user=user,
            module=module,
            status=status
        )
        counter.number += number
        counter.save()


def increment_counter_on_plan_checking(
        status: Literal[PlanStatus.approved, PlanStatus.rejected],
        region_ids
):
    """
    Updates notification counters for Center Manager and Regional Manager
    users after a plan is either approved or rejected.

    Module: plan
    Roles: Center Manager, Regional Manager
    Statuses: approved, rejected
    """
    module = ModuleChoices.plan
    if status == PlanStatus.approved:
        users = CustomUser.objects.filter(is_active=True).filter(Q(role=UserRoles.CM) | Q(region_id__in=region_ids))
    else:
        users = CustomUser.objects.filter(is_active=True, role=UserRoles.CM)
    return increment_counter(users, module, status)


def increment_counter_on_plan_creation():
    """
    Updates notification counters for Center Director users when a new
    plan is created.

    Module: plan
    Role: Center Director
    Status: new
    """
    status = PlanStatus.new
    module = ModuleChoices.plan
    users = CustomUser.objects.filter(is_active=True, role=UserRoles.CD)
    return increment_counter(users, module, status)


def increment_counter_on_appeal_creation(region_id):
    """
    Updates notification counters for Regional Manager users when a new
    appeal is created.

    Module: appeal
    Role: Regional Manager
    Status: new
    """
    status = AppealStatus.new
    module = ModuleChoices.appeal
    users = CustomUser.objects.filter(is_active=True, role=UserRoles.RM, region_id=region_id)
    return increment_counter(users, module, status)


def increment_counter_on_appeal_sending():
    """
    Updates notification counters for Center Director users when a new
    appeal is sent to checking.

    Module: appeal
    Role: Regional Manager
    Status: sent
    """
    status = AppealStatus.sent
    module = ModuleChoices.appeal
    users = CustomUser.objects.filter(is_active=True, role=UserRoles.CD)
    return increment_counter(users, module, status)


def increment_counter_on_appeal_checking(
        status: Literal[AppealStatus.approved, AppealStatus.rejected],
        region_id,
        appeal_sender
):
    """
    Updates notification counters for Regional Manager and appeal sender
    users after an appeal is either approved or rejected.

    Module: appeal
    Roles: Regional Manager, Legal entity
    Statuses: approved, rejected
    """
    module = ModuleChoices.appeal
    regional_managers = CustomUser.objects.filter(is_active=True, role=UserRoles.RM, region_id=region_id)
    users = list(regional_managers) + [appeal_sender]
    return increment_counter(users, module, status)


def increment_counter_on_damaged_object_creation(module):
    """
    Updates notification counters for Center Director users when a new
    damaged objects is created.

    Module: mahalla or open area
    Role: Center Director
    Status: new
    """
    status = DamagedStatus.new
    users = CustomUser.objects.filter(is_active=True, role=UserRoles.CD)
    return increment_counter(users, module, status)


def increment_counter_on_damaged_object_checking(
        status: Literal[DamagedStatus.approved, DamagedStatus.rejected],
        region_id,
        module
):
    """
    Updates notification counters for Regional Manager
    users after a damaged object is either approved or rejected.

    Module: mahalla or open area
    Roles: Regional Manager
    Statuses: approved, rejected
    """
    users = CustomUser.objects.filter(is_active=True, role=UserRoles.RM, region_id=region_id)
    return increment_counter(users, module, status)


def increment_counter_on_appeal_damaged_object_checking(
        region_id,
        appeal_sender,
        damaged_type,
        approved_number,
        rejected_number
):
    """
    Updates notification counters for Regional Manager
    users after a damaged object is either approved or rejected.

    Module: mahalla or open area
    Roles: Regional Manager
    Statuses: approved
    """
    module = ModuleChoices.mahalla if damaged_type == DamagedTypes.mahalla else ModuleChoices.open_area
    regional_managers = CustomUser.objects.filter(is_active=True, role=UserRoles.RM, region_id=region_id)
    users = list(regional_managers) + [appeal_sender]
    increment_counter(users, module, DamagedStatus.approved, approved_number)
    increment_counter(users, module, DamagedStatus.rejected, rejected_number)


def decrement_counter_on_retrieve(instance, user, module):
    if instance.unread == True:
        instance.unread = False
        instance.save()
        try:
            counter = NotificationCounter.objects.get(user=user, module=module, status=instance.status)
            counter.number -= 1
            counter.save()
        except:
            pass
