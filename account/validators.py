from account.models import UserRoles
from config.utils import CommonException
from django.utils.translation import gettext_lazy as _


def user_role_validator(role: UserRoles, ministry=None, region=None):
    if region and ministry:
        raise CommonException(_("Region or Ministry cannot be entered together."))

    if role == UserRoles.ME:
        if ministry is None:
            raise CommonException(_("Ministry is required"))
    elif role == UserRoles.RM:
        if region is None:
            raise CommonException(_("Region is required"))
    elif region or ministry:
        raise CommonException(_("Region or Ministry cannot be entered."))
