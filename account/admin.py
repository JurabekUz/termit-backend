from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _

from .models import CustomUser, UserActivityLog, UserSession


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


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ['user', 'login_method', 'login_at', 'logout_at', 'is_active', 'ip_address', 'last_page']
    list_filter = ['login_method', 'is_active']
    search_fields = ['user__full_name', 'user__pinfl', 'ip_address', 'last_page']
    readonly_fields = ['id', 'user', 'login_method', 'login_at', 'logout_at', 'last_seen_at', 'ip_address', 'user_agent']


@admin.register(UserActivityLog)
class UserActivityLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'action', 'method', 'from_page', 'to_page', 'resource_type', 'created_at', 'ip_address']
    list_filter = ['action', 'resource_type', 'method']
    search_fields = ['user__full_name', 'user__pinfl', 'from_page', 'to_page', 'description', 'endpoint']
    readonly_fields = [
        'user', 'session', 'action', 'method', 'endpoint', 'from_page', 'to_page',
        'page_title', 'resource_type', 'resource_id', 'description', 'status_code',
        'ip_address', 'user_agent', 'metadata', 'created_at',
    ]


admin.site.unregister(Group)
