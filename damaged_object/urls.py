from django.urls import path, include
from rest_framework.routers import DefaultRouter
from damaged_object.views import (
    MahallaInfoViewSet,
    OpenAreaInfoViewSet,
    FreeDamagedObjectsListView,
    MahallaStatusStatView,
    ObjectStatView,
    OpenAreaStatusStatView,
    CadastralObjectView, CadastralNumbersView
)

router = DefaultRouter(trailing_slash=False)
router.register(r'mahalla', MahallaInfoViewSet)
router.register(r'open-area', OpenAreaInfoViewSet)

urlpatterns = [
    path('damaged-object/free', FreeDamagedObjectsListView.as_view()),
    path('statistics/mahalla', MahallaStatusStatView.as_view()),
    path('statistics/objects', ObjectStatView.as_view()),
    path('statistics/open-area', OpenAreaStatusStatView.as_view()),

    path('damaged-object/', include(router.urls)),

    path('cadastral-object/', CadastralObjectView.as_view()),
    path('cadastral-numbers/', CadastralNumbersView.as_view()),
]
