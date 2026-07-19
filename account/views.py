import requests
from urllib.parse import urlparse

from django.utils import timezone
from django.utils import translation
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework.decorators import action
from rest_framework.generics import GenericAPIView
from rest_framework.viewsets import ModelViewSet
from django.conf import settings
from rest_framework.permissions import AllowAny
from django.utils.translation import gettext_lazy as _
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from account.models import CustomUser, generate_username, UserRoles
from account.serializers import UserListSerializer, CreateUserSerializer, RetrieveUserSerializer, UpdateUserSerializer, \
    UpdateRegionUserSerializer
from area.serializers import AreaSelectSerializer
from baseapp.utils import has_related_objects
from config.utils import CommonException


"""  User Views   """


class UserViewSet(ModelViewSet):
    queryset = CustomUser.objects.filter(is_active=True)
    serializer_class = UserListSerializer
    search_fields = ['full_name', 'pinfl']

    def get_serializer_class(self):
        if self.action == 'list':
            return UserListSerializer
        elif self.action == 'create':
            return CreateUserSerializer
        elif self.action in ('retrieve', 'me'):
            return RetrieveUserSerializer
        elif self.action in ('update', 'partial_update'):
            return UpdateUserSerializer
        elif self.action in ('change_region',):
            return UpdateRegionUserSerializer

    def perform_destroy(self, instance):
        if has_related_objects(instance):
            # If connected, just set is_active = False
            instance.username = generate_username()
            instance.pinfl = None
            instance.is_active = False
            instance.save()
        else:
            # Delete completely if there are no related objects
            instance.delete()

    @action(
        detail=False,
        methods=['GET'],
        url_path='me',
        filter_backends=None,
        pagination_class=None
    )
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @action(detail=False, methods=['POST'], url_path='change-region')
    def change_region(self, request):
        serializer = self.get_serializer(
            instance=request.user,
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=False, methods=['GET'], url_path='my-regions')
    def my_region(self, request):
        user = request.user
        serializer = AreaSelectSerializer(user.regions.all(), many=True)
        return Response(serializer.data)


""" AUTH Views """


def get_user_tokens(user):
    refresh = RefreshToken.for_user(user)
    return {
        "refresh_token": str(refresh),
        "access_token": str(refresh.access_token)
    }


class LoginView(GenericAPIView):
    serializer_class = RetrieveUserSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    pagination_class = None
    filter_backends = []

    @swagger_auto_schema(
        operation_description="login api",
        manual_parameters=[
            openapi.Parameter('code', openapi.IN_QUERY, required=True, type=openapi.TYPE_STRING)
        ],
    )
    def get(self, request):
        translation.activate(request.LANGUAGE_CODE)
        code = self.request.query_params.get('code')
        if not code:
            raise CommonException("code is required", 400)
        print("keldi")
        auth_request = requests.post(
            'https://sso.egov.uz/sso/oauth/Authorization.do',
            params={
                'grant_type': 'one_authorization_code',
                'client_id': settings.CLIENT_ID,
                'client_secret': settings.CLIENT_SECRET,
                'code': code
            }
        )
        print("auth request keldi")
        if auth_request.status_code == 404:
            raise CommonException(_("Doesn't exist such as user"), 404)
        elif auth_request.status_code != 200:
            raise CommonException(auth_request.json().get('error_description'), 400)

        access_token = auth_request.json().get('access_token')
        print(access_token)
        client_data = requests.post(
            'https://sso.egov.uz/sso/oauth/Authorization.do',
            params=f'grant_type=one_access_token_identify&client_id={settings.CLIENT_ID}&client_secret={settings.CLIENT_SECRET}&'
                   f'access_token={access_token}&scope={settings.SCOPE}'
        )
        print("clint")
        client_json = client_data.json()
        pin = client_json.get('pin')
        auth_method = client_json.get('auth_method')
        error_msg = _('To submit an application, log in through your legal entity profile.')
        domain_error_msg = _('No access allowed.')
        origin = request.headers.get('origin') or request.headers.get('Referer')
        parsed_url = urlparse(origin)
        origin = f"{parsed_url.scheme}://{parsed_url.netloc}"

        if not pin:
            raise CommonException(_("An unexpected error occurred. Please try again."), 400)

        try:
            user = CustomUser.objects.get(pinfl=pin)
            if user.role == UserRoles.LE and auth_method != 'LEPKCSMETHOD':
                raise CommonException(error_msg)
        except CustomUser.DoesNotExist:
            if auth_method != 'LEPKCSMETHOD':
                raise CommonException(error_msg)

            first_name = client_json.get('first_name', '').strip()
            last_name = client_json.get('sur_name', '').strip()
            full_name = f"{first_name} {last_name}".strip()

            user = CustomUser(pinfl=pin, role=UserRoles.LE, full_name=full_name, username=pin)
            user.save()

        if origin == settings.MAP_ORIGIN and user.role != UserRoles.ME:
            raise CommonException(domain_error_msg)

        if user.full_name is None or not len(user.full_name):
            try:
                first_name = client_json.get('first_name', '')
                last_name = client_json.get('sur_name', '')
                user.full_name = first_name + ' ' + last_name
                user.save()
            except:
                pass

        token = get_user_tokens(user)
        response = Response(data=RetrieveUserSerializer(user).data, status=200)
        response.set_cookie(
            key=settings.SIMPLE_JWT['AUTH_COOKIE'],
            value=token["access_token"],
            expires=(timezone.now() + settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME']).strftime("%a, %d-%b-%Y %H:%M:%S GMT"),
            # max_age=settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'],
            secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
            httponly=settings.SIMPLE_JWT['AUTH_COOKIE_HTTP_ONLY'],
            samesite=settings.SIMPLE_JWT['AUTH_COOKIE_SAMESITE']
        )
        response.set_cookie(
            key=settings.SIMPLE_JWT['AUTH_COOKIE_REFRESH'],
            value=token["refresh_token"],
            expires=(timezone.now() + settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME']).strftime("%a, %d-%b-%Y %H:%M:%S GMT"),
            # max_age=settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'],
            secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
            httponly=settings.SIMPLE_JWT['AUTH_COOKIE_HTTP_ONLY'],
            samesite=settings.SIMPLE_JWT['AUTH_COOKIE_SAMESITE']
        )
        return response


class LogoutView(GenericAPIView):

    @swagger_auto_schema(
        operation_description="Logout user",
        responses={204: 'No Content'}
    )
    def post(self, request, *args, **kwargs):
        response = Response(status=200)
        response.delete_cookie(settings.SIMPLE_JWT['AUTH_COOKIE'])
        response.delete_cookie(settings.SIMPLE_JWT['AUTH_COOKIE_REFRESH'])
        return response


class AuthorizationCodeView(GenericAPIView):
    permission_classes = [AllowAny]
    filter_backends = []
    pagination_class = None

    def get(self, request):
        from django.shortcuts import redirect
        url = 'https://sso.egov.uz/sso/oauth/Authorization.do'

        origin = request.headers.get('origin') or request.headers.get('Referer')
        parsed_url = urlparse(origin)
        origin = f"{parsed_url.scheme}://{parsed_url.netloc}"
        redirect_uri = origin + '/auth'
        params = {
            "response_type": "one_code",
            "client_id": settings.CLIENT_ID,
            "scope": settings.SCOPE,
            "redirect_uri": redirect_uri,
            "state": "authCode"
        }
        # Brauzerni URLga yo‘naltirish
        from urllib.parse import urlencode
        full_url = f"{url}?{urlencode(params)}"
        return redirect(full_url)


''' login view for developers '''


class DevLoginView(GenericAPIView):
    serializer_class = RetrieveUserSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    pagination_class = None
    filter_backends = []

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter('code', openapi.IN_QUERY, description="code is required",
                              type=openapi.TYPE_STRING, required=True)
        ]
    )
    def get(self, request):
        translation.activate(request.LANGUAGE_CODE)
        pin_list = settings.DEV_PIN_LIST
        code = self.request.query_params.get('code')
        if not code or code not in pin_list:
            raise CommonException("Invalid code", 400)

        try:
            user = CustomUser.objects.get(pinfl=code)
        except CustomUser.DoesNotExist:
            raise CommonException(_("Doesn't exist such as user"), 404)
        token = get_user_tokens(user)
        response = Response(data=RetrieveUserSerializer(user).data, status=200)
        response.set_cookie(
            key=settings.SIMPLE_JWT['AUTH_COOKIE'],
            value=token["access_token"],
            expires=(timezone.now() + settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME']).strftime(
                "%a, %d-%b-%Y %H:%M:%S GMT"),
            secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
            httponly=settings.SIMPLE_JWT['AUTH_COOKIE_HTTP_ONLY'],
            samesite=settings.SIMPLE_JWT['AUTH_COOKIE_SAMESITE']
        )
        response.set_cookie(
            key=settings.SIMPLE_JWT['AUTH_COOKIE_REFRESH'],
            value=token["refresh_token"],
            expires=(timezone.now() + settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME']).strftime(
                "%a, %d-%b-%Y %H:%M:%S GMT"),
            secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
            httponly=settings.SIMPLE_JWT['AUTH_COOKIE_HTTP_ONLY'],
            samesite=settings.SIMPLE_JWT['AUTH_COOKIE_SAMESITE']
        )
        return response
