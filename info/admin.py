from django.contrib import admin

from .models import Ministry, OpenAreaType, Media


@admin.register(Ministry, OpenAreaType)
class MinistryAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name']


@admin.register(Media)
class MediaAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'created_at']
