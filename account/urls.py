from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    UserViewSet, LoginView, LogoutView, AuthorizationCodeView,
    # SuperAccessVerifyView, SuperAccessLoginView
)

router = DefaultRouter(trailing_slash=False)
router.register(r'accounts', UserViewSet)

urlpatterns = [
    path('auth/code', AuthorizationCodeView.as_view()),
    path('auth/login', LoginView.as_view()),
    path('auth/logout', LogoutView.as_view()),
    # path('auth/super-access/verify', SuperAccessVerifyView.as_view()),
    # path('auth/super-access/login', SuperAccessLoginView.as_view()),

    path('', include(router.urls)),
]