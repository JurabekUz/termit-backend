from django.contrib import admin

from damaged_object.models import MahallaInfo, OpenAreaInfo, DamagedObjectFlow, DamagedObject
from plan.admin import PlanItemInline, PlanRegionStatusInline


class DamagedObjectFlowInline(admin.TabularInline):
    model = DamagedObjectFlow
    extra = 0


class DamagedObjectInline(admin.TabularInline):
    model = DamagedObject
    extra = 0


@admin.register(MahallaInfo)
class MahallaInfoAdmin(admin.ModelAdmin):
    list_display = ('id', 'district', 'mahalla', 'object_type', 'status', 'date', )
    list_filter = ('object_type', 'status', 'district', 'district__region')
    list_select_related = ('district', 'mahalla')
    search_fields = ['mahalla__name', 'district__name']
    inlines = [DamagedObjectFlowInline]


@admin.register(OpenAreaInfo)
class OpenAreaInfoAdmin(admin.ModelAdmin):
    list_display = ('id', 'district', 'area_type', 'status', 'date', )
    list_filter = ('area_type', 'status', 'district',)
    list_select_related = ('district', 'area_type')
    inlines = [DamagedObjectFlowInline]


@admin.register(DamagedObject)
class DamagedObjectAdmin(admin.ModelAdmin):
    list_display = ('id', 'status', 'district', 'date', 'type', 'appeal')
    list_filter = ('status', 'district', 'type', 'district__region')
    list_select_related = ('district', 'appeal')
    inlines = [DamagedObjectFlowInline, PlanItemInline]
    search_fields = ['district__name']
