from django.contrib import admin

from plan.models import Plan, PlanItem, PlanRegionStatus, DraftItem


class PlanRegionStatusInline(admin.TabularInline):
    model = PlanRegionStatus
    # list_display = ('id', 'plan', 'region', 'is_read', 'read_time')
    extra = 0
    # readonly_fields = ('id', 'plan', 'region', 'is_read', 'read_time')
    can_delete = False


class PlanItemInline(admin.TabularInline):
    model = PlanItem
    extra = 0
    # readonly_fields = ('id', 'plan', 'item', 'is_performed')
    can_delete = False


@admin.register(PlanItem)
class PlanItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'plan', 'item', 'is_performed')
    list_filter = ('is_performed', 'plan')


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'from_date', 'to_date')
    list_filter = ('status',)
    inlines = [PlanRegionStatusInline, PlanItemInline]


@admin.register(DraftItem)
class DraftItemAdmin(admin.ModelAdmin):
    list_display = ['id', 'plan', 'item']


