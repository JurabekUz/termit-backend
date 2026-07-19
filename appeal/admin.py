from django.contrib import admin

from appeal.models import Appeal
from damaged_object.admin import DamagedObjectInline


@admin.register(Appeal)
class AppealAdmin(admin.ModelAdmin):
    list_display = ('id', 'sender', 'district', 'status', 'damaged_type', 'created_at')
    list_filter = ('status', 'district__region', 'damaged_type')
    inlines = [DamagedObjectInline]