from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _

from .models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ['username', 'role', 'pinfl', 'full_name', 'is_active', 'region', 'ministry']
    list_filter = ['role', 'is_active', 'ministry', 'region', 'is_superuser', 'is_staff']
    search_fields = ['username', 'full_name', 'pinfl']

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {"fields": ("full_name", "pinfl", "role", "email", "ministry", "region", "regions")}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                ),
            },
        )
    )


admin.site.unregister(Group)
