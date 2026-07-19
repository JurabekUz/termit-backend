from django.contrib import admin


from notification.models import NotificationCounter


@admin.register(NotificationCounter)
class NotificationCounterAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'module', 'status', 'number']
