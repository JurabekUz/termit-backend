from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    MinistryViewSet, OpenAreaTypeViewSet,
    MediaDestroyView, MediaCreateView
)

router = DefaultRouter(trailing_slash=False)
router.register(r'ministries', MinistryViewSet)
router.register(r'open-area-types', OpenAreaTypeViewSet)

urlpatterns = [
    path('media', MediaCreateView.as_view()),
    path('media/<int:pk>', MediaDestroyView.as_view()),

    path('info/', include(router.urls)),
]
