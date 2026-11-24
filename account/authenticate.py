from rest_framework_simplejwt.authentication import JWTAuthentication

from django.contrib.auth import get_user_model
from django.conf import settings


class CustomAuthentication(JWTAuthentication):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_model = get_user_model()

    def authenticate(self, request):
        result = None
        raw_token = request.COOKIES.get(settings.SIMPLE_JWT['AUTH_COOKIE'])
        if raw_token is not None:
            try:
                validated_token = self.get_validated_token(raw_token)
                result = (self.get_user(validated_token), validated_token)
            except Exception:
                result = None

        if result is None:
            result = super().authenticate(request)

        if result is not None:
            user, validated_token = result
            raw_request = getattr(request, '_request', request)
            raw_request._activity_user = user
            raw_request._activity_token = validated_token

        return result
