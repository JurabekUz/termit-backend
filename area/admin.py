from django.contrib import admin
from .models import Region, District, Mahalla, OpenArea


# Register your models here.

@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ('name', 'code')


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'region')
    list_filter = ('region', )
    search_fields = ('name', 'code')


@admin.register(Mahalla)
class MahallaAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'district', 'status', 'damaged_percent', 'updated_at')
    list_filter = ('district', 'district__region', 'status')
    search_fields = ('name', 'code', 'parent_code')


@admin.register(OpenArea)
class OpenAreaAdmin(admin.ModelAdmin):
    list_display = ('id', 'district', 'hectare')
    list_filter = ('district__region',)
