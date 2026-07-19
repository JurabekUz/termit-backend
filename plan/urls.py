from django.urls import path, include
from rest_framework.routers import DefaultRouter
from plan.views import PlanViewSet


router = DefaultRouter(trailing_slash=False)
router.register(r'plans', PlanViewSet, basename='plans')

urlpatterns = [

    path('', include(router.urls)),
]