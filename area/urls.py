from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views


router = DefaultRouter(trailing_slash=False)
router.register(r'regions', views.RegionViewSet, basename='regions')
router.register(r'districts', views.DistrictViewSet, basename='districts')
router.register(r'mahalla', views.MahallaViewSet, basename='mahalla')
router.register(r'open-areas', views.OpenAreaViewSet, basename='open-areas')



urlpatterns = [
    # path('load-region', views.LoadRegionApiView.as_view(), name=''),
    # path('load-district', views.LoadDistrictApiView.as_view(), name=''),
    # path('load-mahalla', views.LoadMahallaApiView.as_view(), name=''),

    path('statistics/number', views.NumberStatView.as_view()),
    path('statistics/area', views.AreaStatView.as_view()),
    path('statistics/area/damaged-status', views.AreaDamagedStatusView.as_view()),

    path('districts/by-code/<int:code>', views.DistrictRetrieveView.as_view()),
    path('districts/mahalla-status/<int:code>', views.MahallaStatusView.as_view()),

    path('', include(router.urls)),
]