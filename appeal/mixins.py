from account.models import UserRoles
from appeal.models import Appeal


class AppealQuerysetMixin:
    """Filtering queryset based on user role."""

    def get_queryset(self):
        user = self.request.user
        queryset = self.queryset
        if user.role == UserRoles.LE:
            return queryset.filter(sender=user)
        elif user.role == UserRoles.RM:
            return queryset.filter(district__region_id=user.region_id)
        return queryset
