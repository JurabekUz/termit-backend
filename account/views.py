import hmac
import logging
import secrets
from datetime import timedelta
import requests
from urllib.parse import urlparse

from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.db import IntegrityError, transaction
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

from account.models import (
    CustomUser, generate_username, UserRoles,
    SuperAccessRateLimit, SuperAccessChallenge,
)
from account.totp import verify_totp
from account.serializers import UserListSerializer, CreateUserSerializer, RetrieveUserSerializer, UpdateUserSerializer, \
    UpdateRegionUserSerializer
from area.serializers import AreaSelectSerializer
from baseapp.utils import has_related_objects
from config.utils import CommonException

logger = logging.getLogger(__name__)

SUPER_ACCESS_MAX_FAILED_ATTEMPTS = 5
SUPER_ACCESS_LOCKOUT_MINUTES = 15
SUPER_ACCESS_CHALLENGE_TTL_SECONDS = 120
SUPER_ACCESS_SIGNER_SALT = 'super-access-2fa'


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


def _get_request_origin(request):
    """Extract normalized scheme://netloc from Origin or Referer header."""
    raw_origin = request.headers.get('origin') or request.headers.get('Referer')
    if not raw_origin:
        return None
    parsed_url = urlparse(raw_origin)
    if not parsed_url.scheme or not parsed_url.netloc:
        return None
    return f"{parsed_url.scheme}://{parsed_url.netloc}"


def _get_safe_redirect_uri(request):
    """Return an allowlisted /auth redirect URI, falling back to configured REDIRECT_URI."""
    origin = _get_request_origin(request)
    allowed_origins = {o.strip().rstrip('/') for o in settings.CORS_ALLOWED_ORIGINS if o.strip()}
    if settings.MAP_ORIGIN:
        allowed_origins.add(settings.MAP_ORIGIN.strip().rstrip('/'))
    if origin and origin in allowed_origins:
        return f"{origin}/auth"
    return settings.REDIRECT_URI


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
        auth_request = requests.post(
            'https://sso.egov.uz/sso/oauth/Authorization.do',
            params={
                'grant_type': 'one_authorization_code',
                'client_id': settings.CLIENT_ID,
                'client_secret': settings.CLIENT_SECRET,
                'code': code
            }
        )
        if auth_request.status_code == 404:
            raise CommonException(_("Doesn't exist such as user"), 404)
        elif auth_request.status_code != 200:
            raise CommonException(auth_request.json().get('error_description'), 400)

        access_token = auth_request.json().get('access_token')
        client_data = requests.post(
            'https://sso.egov.uz/sso/oauth/Authorization.do',
            params={
                'grant_type': 'one_access_token_identify',
                'client_id': settings.CLIENT_ID,
                'client_secret': settings.CLIENT_SECRET,
                'access_token': access_token,
                'scope': settings.SCOPE,
            }
        )
        client_json = client_data.json()
        pin = client_json.get('pin')
        auth_method = client_json.get('auth_method')
        error_msg = _('To submit an application, log in through your legal entity profile.')
        domain_error_msg = _('No access allowed.')

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

        if _is_map_origin_request(request) and user.role != UserRoles.ME:
            raise CommonException(domain_error_msg)

        if user.full_name is None or not len(user.full_name):
            try:
                first_name = client_json.get('first_name', '')
                last_name = client_json.get('sur_name', '')
                user.full_name = first_name + ' ' + last_name
                user.save()
            except:
                pass

        response = Response(data=RetrieveUserSerializer(user).data, status=200)
        return _set_auth_cookies(response, user)


def _set_auth_cookies(response, user):
    token = get_user_tokens(user)
    samesite_setting = settings.SIMPLE_JWT.get('AUTH_COOKIE_SAMESITE') or 'Lax'
    response.set_cookie(
        key=settings.SIMPLE_JWT['AUTH_COOKIE'],
        value=token["access_token"],
        expires=(timezone.now() + settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME']).strftime("%a, %d-%b-%Y %H:%M:%S GMT"),
        secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
        httponly=settings.SIMPLE_JWT['AUTH_COOKIE_HTTP_ONLY'],
        samesite=samesite_setting,
    )
    response.set_cookie(
        key=settings.SIMPLE_JWT['AUTH_COOKIE_REFRESH'],
        value=token["refresh_token"],
        expires=(timezone.now() + settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME']).strftime("%a, %d-%b-%Y %H:%M:%S GMT"),
        secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
        httponly=settings.SIMPLE_JWT['AUTH_COOKIE_HTTP_ONLY'],
        samesite=samesite_setting,
    )
    return response


def _get_client_ip(request):
    x_real_ip = request.headers.get('X-Real-IP')
    if x_real_ip:
        return x_real_ip.strip()
    x_forwarded_for = request.headers.get('X-Forwarded-For')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or '127.0.0.1'


def _is_map_origin_request(request):
    origin = _get_request_origin(request)
    map_origin = (getattr(settings, 'MAP_ORIGIN', '') or '').strip().rstrip('/')
    return bool(origin and map_origin and origin == map_origin)


def _is_local_super_access():
    return bool(getattr(settings, 'LOCAL', False) and settings.DEBUG)


def _super_access_configured():
    enabled = getattr(settings, 'ENABLED_SUPER_ACCESS', False)
    is_local = _is_local_super_access()
    configured_key = (getattr(settings, 'SUPER_ACCESS_KEY', '') or '').strip()
    totp_secret = (getattr(settings, 'SUPER_ACCESS_TOTP_SECRET', '') or '').strip()
    if not enabled:
        return False, configured_key, totp_secret, is_local
    if is_local:
        return True, configured_key, totp_secret, True
    return bool(configured_key and totp_secret), configured_key, totp_secret, False


def _issue_super_access_challenge(client_ip, now, totp_step=None, map_only=False):
    SuperAccessChallenge.objects.filter(expires_at__lt=now - timedelta(hours=1)).delete()
    jti = secrets.token_hex(24)
    expires_at = now + timedelta(seconds=SUPER_ACCESS_CHALLENGE_TTL_SECONDS)

    with transaction.atomic():
        SuperAccessChallenge.objects.create(
            jti=jti,
            ip_address=client_ip,
            totp_step=totp_step,
            expires_at=expires_at,
        )

    challenge_token = TimestampSigner(salt=SUPER_ACCESS_SIGNER_SALT).sign(jti)
    role_choices = dict(UserRoles.choices)
    users = CustomUser.objects.filter(is_active=True).select_related('region', 'ministry').order_by('id')
    if map_only:
        users = users.filter(role=UserRoles.ME)
    user_list = [
        {
            "id": u.id,
            "full_name": u.full_name or "Ismsiz foydalanuvchi",
            "role": u.role,
            "role_display": str(role_choices.get(u.role, u.role)),
            "region": u.region.name if u.region else None,
            "ministry": u.ministry.name if u.ministry else None,
            "is_superuser": u.is_superuser,
        }
        for u in users
    ]
    return challenge_token, user_list


def _record_super_access_failure(ip_address, now):
    with transaction.atomic():
        rate_limit, _ = SuperAccessRateLimit.objects.select_for_update().get_or_create(ip_address=ip_address)
        if rate_limit.locked_until and rate_limit.locked_until <= now:
            rate_limit.failed_attempts = 0
            rate_limit.locked_until = None
        rate_limit.failed_attempts += 1
        if rate_limit.failed_attempts >= SUPER_ACCESS_MAX_FAILED_ATTEMPTS:
            rate_limit.locked_until = now + timedelta(minutes=SUPER_ACCESS_LOCKOUT_MINUTES)
        rate_limit.save()


def _reset_super_access_failures(ip_address):
    SuperAccessRateLimit.objects.filter(ip_address=ip_address).update(
        failed_attempts=0,
        locked_until=None,
    )


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

        redirect_uri = _get_safe_redirect_uri(request)
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


class SuperAccessStatusView(GenericAPIView):
    swagger_schema = None
    permission_classes = [AllowAny]
    authentication_classes = []
    pagination_class = None
    filter_backends = []

    def get(self, request):
        configured, _, _, is_local = _super_access_configured()
        if not configured:
            return Response({"enabled": False}, status=404)
        if is_local:
            client_ip = _get_client_ip(request)
            challenge_token, user_list = _issue_super_access_challenge(
                client_ip,
                timezone.now(),
                totp_step=None,
                map_only=_is_map_origin_request(request),
            )
            return Response({
                "enabled": True,
                "local": True,
                "challenge_token": challenge_token,
                "expires_in": SUPER_ACCESS_CHALLENGE_TTL_SECONDS,
                "users": user_list,
            }, status=200)
        return Response({"enabled": True, "local": False}, status=200)


class SuperAccessVerifyView(GenericAPIView):
    swagger_schema = None
    permission_classes = [AllowAny]
    authentication_classes = []
    pagination_class = None
    filter_backends = []

    def post(self, request):
        configured, configured_key, totp_secret, is_local = _super_access_configured()
        if not configured:
            return Response({"detail": _("Not found.")}, status=404)

        client_ip = _get_client_ip(request)
        now = timezone.now()
        map_only = _is_map_origin_request(request)
        if is_local:
            challenge_token, user_list = _issue_super_access_challenge(
                client_ip,
                now,
                totp_step=None,
                map_only=map_only,
            )
            return Response({
                "success": True,
                "challenge_token": challenge_token,
                "expires_in": SUPER_ACCESS_CHALLENGE_TTL_SECONDS,
                "users": user_list,
            }, status=200)

        rate_limit = SuperAccessRateLimit.objects.filter(ip_address=client_ip).first()
        if rate_limit and rate_limit.locked_until and rate_limit.locked_until > now:
            return Response(
                {"detail": _("Ko'p marta noto'g'ri urinish. Keyinroq urinib ko'ring.")},
                status=429,
            )

        provided_key = str(request.data.get('key', '') or '').strip()
        provided_totp = str(request.data.get('totp', '') or '').strip()

        key_ok = bool(provided_key) and hmac.compare_digest(
            provided_key.encode('utf-8'),
            configured_key.encode('utf-8'),
        )
        totp_ok, matched_step = verify_totp(totp_secret, provided_totp)

        if not (key_ok and totp_ok and matched_step is not None):
            _record_super_access_failure(client_ip, now)
            logger.warning("Failed super-access verify attempt from %s", client_ip)
            return Response({"detail": _("Kalit yoki TOTP kodi noto'g'ri!")}, status=403)

        try:
            challenge_token, user_list = _issue_super_access_challenge(
                client_ip,
                now,
                totp_step=matched_step,
                map_only=map_only,
            )
        except IntegrityError:
            return Response(
                {"detail": _("Bu TOTP kodi allaqachon ishlatilgan. Keyingi kodni kuting.")},
                status=403,
            )

        _reset_super_access_failures(client_ip)

        return Response({
            "success": True,
            "challenge_token": challenge_token,
            "expires_in": SUPER_ACCESS_CHALLENGE_TTL_SECONDS,
            "users": user_list,
        }, status=200)


class SuperAccessLoginView(GenericAPIView):
    swagger_schema = None
    permission_classes = [AllowAny]
    authentication_classes = []
    pagination_class = None
    filter_backends = []

    def post(self, request):
        configured = _super_access_configured()[0]
        if not configured:
            return Response({"detail": _("Not found.")}, status=404)

        client_ip = _get_client_ip(request)
        now = timezone.now()
        rate_limit = SuperAccessRateLimit.objects.filter(ip_address=client_ip).first()
        if rate_limit and rate_limit.locked_until and rate_limit.locked_until > now:
            return Response(
                {"detail": _("Ko'p marta noto'g'ri urinish. Keyinroq urinib ko'ring.")},
                status=429,
            )

        challenge_token = str(request.data.get('challenge_token', '') or '').strip()
        if not challenge_token:
            return Response({"detail": _("Tasdiqlash tokeni topilmadi!")}, status=403)

        try:
            jti = TimestampSigner(salt=SUPER_ACCESS_SIGNER_SALT).unsign(
                challenge_token,
                max_age=SUPER_ACCESS_CHALLENGE_TTL_SECONDS,
            )
        except (BadSignature, SignatureExpired):
            return Response({"detail": _("Sessiya muddati tugagan yoki yaroqsiz. Qaytadan tasdiqlang.")}, status=403)

        user_id = request.data.get('user_id')
        if not user_id:
            return Response({"detail": _("Foydalanuvchi tanlanmagan!")}, status=400)

        try:
            user = CustomUser.objects.get(id=user_id, is_active=True)
        except CustomUser.DoesNotExist:
            return Response({"detail": _("Foydalanuvchi topilmadi!")}, status=404)

        if _is_map_origin_request(request) and user.role != UserRoles.ME:
            return Response({"detail": _("No access allowed.")}, status=403)

        with transaction.atomic():
            challenge = (
                SuperAccessChallenge.objects.select_for_update()
                .filter(jti=jti, ip_address=client_ip, used_at__isnull=True, expires_at__gt=now)
                .first()
            )
            if not challenge:
                return Response(
                    {"detail": _("Sessiya muddati tugagan yoki allaqachon ishlatilgan. Qaytadan tasdiqlang.")},
                    status=403,
                )
            challenge.used_at = now
            challenge.save(update_fields=['used_at'])

        logger.info("Super-access login for user_id=%s (%s) from %s", user.id, user.role, client_ip)
        response = Response(data=RetrieveUserSerializer(user).data, status=200)
        return _set_auth_cookies(response, user)
