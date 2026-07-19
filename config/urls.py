"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path, include

from django.conf import settings
from django.conf.urls.static import static
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions
# from debug_toolbar.toolbar import debug_toolbar_urls

schema_view = get_schema_view(
    openapi.Info(
        title="Project Termite API",
        default_version='v1',
        description="Your API description",
        terms_of_service="https://www.your-terms.com/",
        contact=openapi.Contact(email="contact@your-api.com"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)

urlpatterns = [
    path('api/swagger', schema_view.with_ui('swagger', cache_timeout=0)),
    path('admin/', admin.site.urls),

    path('api/area/', include('area.urls')),
    path('api/', include('account.urls')),
    path('api/', include('info.urls')),
    path('api/', include('damaged_object.urls')),
    path('api/', include('appeal.urls')),
    path('api/', include('plan.urls')),
    path('api/', include('notification.urls'))
]

# if settings.DEBUG:
#     urlpatterns = debug_toolbar_urls() + urlpatterns
