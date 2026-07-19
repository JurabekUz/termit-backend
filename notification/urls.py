from django.urls import path

from notification.views import NotificationCounterView

urlpatterns = [
    path('notifications/counter', NotificationCounterView.as_view())
]
