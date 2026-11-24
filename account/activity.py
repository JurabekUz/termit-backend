import logging
import re
import uuid
from datetime import timedelta

import jwt
from django.conf import settings
from django.utils import timezone

from account.models import ActivityAction, CustomUser, LoginMethod, UserActivityLog, UserSession

logger = logging.getLogger(__name__)

SESSION_TOUCH_INTERVAL_SECONDS = 60

# Ordered rules for classifying API endpoints into human-readable activity logs.
# Each entry: (method_set_or_None, regex, default_action, resource_type, description)
ENDPOINT_RULES = [
    (
        {'POST'},
        re.compile(r'^/api/accounts/change-region/?$'),
        ActivityAction.ACTION,
        'user',
        "Hududni o'zgartirdi",
    ),
    (
        None,
        re.compile(r'^/api/accounts(?:/(?P<pk>\d+))?/?$'),
        None,
        'user',
        None,
    ),
    (
        {'POST'},
        re.compile(r'^/api/appeals/mahalla/?$'),
        ActivityAction.CREATE,
        'appeal',
        "Mahalla bo'yicha murojaat yubordi",
    ),
    (
        {'POST'},
        re.compile(r'^/api/appeals/open-area/?$'),
        ActivityAction.CREATE,
        'appeal',
        "Ochiq maydon bo'yicha murojaat yubordi",
    ),
    (
        {'POST'},
        re.compile(r'^/api/appeals/(?P<pk>\d+)/checking/?$'),
        None,
        'appeal',
        None,
    ),
    (
        {'POST'},
        re.compile(r'^/api/appeals/objects/(?P<pk>\d+)/checking/?$'),
        None,
        'appeal_object',
        None,
    ),
    (
        {'POST'},
        re.compile(r'^/api/damaged-object/mahalla/(?P<pk>\d+)/check/?$'),
        None,
        'damaged_object',
        None,
    ),
    (
        {'POST'},
        re.compile(r'^/api/damaged-object/open-area/(?P<pk>\d+)/check/?$'),
        None,
        'damaged_open_area',
        None,
    ),
    (
        {'POST'},
        re.compile(r'^/api/damaged-object/mahalla/(?P<pk>\d+)/take-action/?$'),
        ActivityAction.ACTION,
        'damaged_object',
        "Mahalla obyekti bo'yicha chora-tadbir kiritdi",
    ),
    (
        {'POST'},
        re.compile(r'^/api/damaged-object/open-area/(?P<pk>\d+)/take-action/?$'),
        ActivityAction.ACTION,
        'damaged_open_area',
        "Ochiq maydon bo'yicha chora-tadbir kiritdi",
    ),
    (
        None,
        re.compile(r'^/api/damaged-object/mahalla(?:/(?P<pk>\d+))?/?$'),
        None,
        'damaged_object',
        None,
    ),
    (
        None,
        re.compile(r'^/api/damaged-object/open-area(?:/(?P<pk>\d+))?/?$'),
        None,
        'damaged_open_area',
        None,
    ),
    (
        {'POST'},
        re.compile(r'^/api/plans/(?P<pk>\d+)/check/?$'),
        None,
        'plan',
        None,
    ),
    (
        None,
        re.compile(r'^/api/plans(?:/(?P<pk>\d+))?/?$'),
        None,
        'plan',
        None,
    ),
    (
        None,
        re.compile(r'^/api/area/mahalla(?:/(?P<pk>\d+))?/?$'),
        None,
        'mahalla',
        None,
    ),
    (
        None,
        re.compile(r'^/api/area/open-areas(?:/(?P<pk>\d+))?/?$'),
        None,
        'open_area',
        None,
    ),
    (
        None,
        re.compile(r'^/api/info/ministries(?:/(?P<pk>\d+))?/?$'),
        None,
        'ministry',
        None,
    ),
    (
        None,
        re.compile(r'^/api/info/open-area-types(?:/(?P<pk>\d+))?/?$'),
        None,
        'open_area_type',
        None,
    ),
    (
        None,
        re.compile(r'^/api/media(?:/(?P<pk>\d+))?/?$'),
        None,
        'media',
        None,
    ),
]

RESOURCE_LABELS_UZ = {
    'user': 'Foydalanuvchi',
    'appeal': 'Murojaat',
    'appeal_object': 'Murojaat obyekti',
    'damaged_object': 'Zararlangan obyekt',
    'damaged_open_area': 'Zararlangan ochiq maydon',
    'plan': 'Reja',
    'mahalla': 'Mahalla',
    'open_area': 'Ochiq maydon',
    'ministry': 'Vazirlik',
    'open_area_type': 'Ochiq maydon turi',
    'media': 'Fayl / media',
}

METHOD_ACTION_MAP = {
    'POST': ActivityAction.CREATE,
    'PUT': ActivityAction.UPDATE,
    'PATCH': ActivityAction.UPDATE,
    'DELETE': ActivityAction.DELETE,
}

ACTION_VERBS_UZ = {
    ActivityAction.CREATE: "yaratdi",
    ActivityAction.UPDATE: "tahrirladi",
    ActivityAction.DELETE: "o'chirdi",
    ActivityAction.APPROVE: "tasdiqladi",
    ActivityAction.REJECT: "rad etdi",
    ActivityAction.ACTION: "amal bajardi",
}


def get_client_ip(request):
    x_real_ip = request.headers.get('X-Real-IP')
    if x_real_ip:
        return x_real_ip.strip()
    x_forwarded_for = request.headers.get('X-Forwarded-For')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or '127.0.0.1'


def get_user_agent(request):
    return (request.headers.get('User-Agent') or '')[:512]


def normalize_page_path(raw_path):
    if not raw_path or not isinstance(raw_path, str):
        return ''
    path = raw_path.strip()
    if not path:
        return ''
    # Drop query/fragment if passed accidentally
    path = path.split('?')[0].split('#')[0].strip()
    if not path:
        return ''
    if not path.startswith('/'):
        path = '/' + path
    return path[:500]


def _decode_jwt_payload(raw_token):
    if not raw_token:
        return None
    signing_key = settings.SIMPLE_JWT.get('SIGNING_KEY', settings.SECRET_KEY)
    algorithm = settings.SIMPLE_JWT.get('ALGORITHM', 'HS256')
    try:
        return jwt.decode(
            raw_token,
            signing_key,
            algorithms=[algorithm],
            options={'verify_exp': False},
        )
    except Exception:
        return None


def resolve_user_and_session_from_request(request):
    """Resolve (user, session) from request cookies or Authorization header."""
    user = getattr(request, '_activity_user', None)
    token = getattr(request, '_activity_token', None)

    if user and getattr(user, 'is_authenticated', False):
        session = get_session_from_token(token, user=user)
        return user, session

    raw_tokens = []
    access_cookie = request.COOKIES.get(settings.SIMPLE_JWT['AUTH_COOKIE'])
    refresh_cookie = request.COOKIES.get(settings.SIMPLE_JWT['AUTH_COOKIE_REFRESH'])
    if access_cookie:
        raw_tokens.append(access_cookie)
    if refresh_cookie:
        raw_tokens.append(refresh_cookie)

    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        raw_tokens.append(auth_header[7:].strip())

    for raw_token in raw_tokens:
        payload = _decode_jwt_payload(raw_token)
        if not payload:
            continue
        user_id = payload.get('user_id')
        if not user_id:
            continue
        resolved_user = CustomUser.objects.filter(id=user_id, is_active=True).first()
        if not resolved_user:
            continue
        session = get_session_from_token(payload, user=resolved_user)
        return resolved_user, session

    return None, None


def get_session_from_token(token_or_payload, user=None):
    if not token_or_payload:
        return None
    sid = None
    try:
        sid = token_or_payload.get('sid')
    except Exception:
        return None
    if not sid:
        return None
    try:
        sid_uuid = uuid.UUID(str(sid))
    except (ValueError, TypeError):
        return None

    qs = UserSession.objects.filter(id=sid_uuid)
    if user is not None:
        qs = qs.filter(user=user)
    return qs.first()


def close_replaced_cookie_session(request, now=None):
    """Close an existing session from the browser's current auth cookie when logging in again."""
    now = now or timezone.now()
    access_cookie = request.COOKIES.get(settings.SIMPLE_JWT['AUTH_COOKIE'])
    payload = _decode_jwt_payload(access_cookie)
    if not payload or not payload.get('sid'):
        return
    try:
        sid_uuid = uuid.UUID(str(payload['sid']))
    except (ValueError, TypeError):
        return
    UserSession.objects.filter(id=sid_uuid, is_active=True, logout_at__isnull=True).update(
        logout_at=now,
        last_seen_at=now,
        logout_reason='replaced',
        is_active=False,
    )


def start_user_session(user, request, login_method=LoginMethod.ONE_ID, from_page='/auth'):
    now = timezone.now()
    close_replaced_cookie_session(request, now=now)

    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)
    normalized_from = normalize_page_path(from_page)

    session = UserSession.objects.create(
        user=user,
        login_method=login_method,
        login_at=now,
        last_seen_at=now,
        ip_address=ip_address,
        user_agent=user_agent,
        last_page=normalized_from,
        is_active=True,
    )

    method_label = 'OneID' if login_method == LoginMethod.ONE_ID else 'Super Access'
    UserActivityLog.objects.create(
        user=user,
        session=session,
        action=ActivityAction.LOGIN,
        method=request.method,
        endpoint=request.path[:500],
        from_page=normalized_from,
        to_page='',
        resource_type='auth',
        resource_id=str(user.id),
        description=f"{method_label} orqali tizimga kirdi",
        status_code=200,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={'login_method': login_method},
        created_at=now,
    )
    return session


def end_user_session(request, user=None, session=None, reason='manual', from_page=''):
    now = timezone.now()
    if user is None or session is None:
        resolved_user, resolved_session = resolve_user_and_session_from_request(request)
        user = user or resolved_user
        session = session or resolved_session

    if user is not None and session is None:
        session = UserSession.objects.filter(
            user=user, is_active=True, logout_at__isnull=True
        ).order_by('-login_at').first()

    normalized_from = normalize_page_path(from_page or request.headers.get('X-Current-Page', ''))

    if session is not None and session.logout_at is None:
        update_fields = {
            'logout_at': now,
            'last_seen_at': now,
            'logout_reason': reason,
            'is_active': False,
        }
        if normalized_from:
            update_fields['last_page'] = normalized_from
        UserSession.objects.filter(id=session.id, logout_at__isnull=True).update(**update_fields)
        session.refresh_from_db()

    if user is not None:
        UserActivityLog.objects.create(
            user=user,
            session=session,
            action=ActivityAction.LOGOUT,
            method=request.method,
            endpoint=request.path[:500],
            from_page=normalized_from,
            to_page='/auth',
            resource_type='auth',
            resource_id=str(user.id),
            description="Tizimdan chiqdi",
            status_code=200,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            metadata={'reason': reason},
            created_at=now,
        )
    return session


def touch_session(session, current_page=None):
    if session is None or not session.is_active:
        return
    now = timezone.now()
    normalized_page = normalize_page_path(current_page) if current_page else ''
    should_update_time = (now - session.last_seen_at) >= timedelta(seconds=SESSION_TOUCH_INTERVAL_SECONDS)
    page_changed = bool(normalized_page and normalized_page != session.last_page)

    if not (should_update_time or page_changed):
        return

    update_fields = {'last_seen_at': now}
    if page_changed:
        update_fields['last_page'] = normalized_page
    UserSession.objects.filter(id=session.id, is_active=True).update(**update_fields)


def record_page_navigation(user, session, request, from_page, to_page, page_title=''):
    now = timezone.now()
    norm_from = normalize_page_path(from_page)
    norm_to = normalize_page_path(to_page)
    if not norm_to:
        return None

    if session is not None and session.is_active:
        UserSession.objects.filter(id=session.id, is_active=True).update(
            last_seen_at=now,
            last_page=norm_to,
        )

    title = (page_title or '').strip()[:255]
    if norm_from and norm_from != norm_to:
        description = f"{norm_from} sahifasidan {norm_to} sahifasiga o'tdi"
    else:
        description = f"{norm_to} sahifasiga kirdi"

    return UserActivityLog.objects.create(
        user=user,
        session=session,
        action=ActivityAction.PAGE_VIEW,
        method='NAV',
        endpoint='',
        from_page=norm_from,
        to_page=norm_to,
        page_title=title,
        resource_type='navigation',
        resource_id='',
        description=description,
        status_code=200,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        metadata={'page_title': title} if title else {},
        created_at=now,
    )


def _extract_safe_status(payload):
    if not isinstance(payload, dict):
        return None
    status_val = payload.get('status') or payload.get('apl_status')
    if isinstance(status_val, str) and len(status_val) <= 32:
        return status_val
    return None


def describe_api_action(method, path, status_code=None, payload=None):
    method = (method or '').upper()
    matched_action = None
    resource_type = 'api'
    resource_id = ''
    description = None
    extra_meta = {}

    for allowed_methods, pattern, default_action, r_type, desc in ENDPOINT_RULES:
        if allowed_methods is not None and method not in allowed_methods:
            continue
        match = pattern.match(path)
        if not match:
            continue
        resource_type = r_type
        resource_id = match.groupdict().get('pk') or ''
        matched_action = default_action
        description = desc
        break

    status_value = _extract_safe_status(payload)
    if status_value:
        extra_meta['status'] = status_value

    if matched_action is None:
        if path.endswith('/check') or path.endswith('/check/') or path.endswith('/checking') or path.endswith('/checking/'):
            if status_value == 'rejected':
                matched_action = ActivityAction.REJECT
            elif status_value == 'approved':
                matched_action = ActivityAction.APPROVE
            else:
                matched_action = ActivityAction.ACTION
        else:
            matched_action = METHOD_ACTION_MAP.get(method, ActivityAction.ACTION)

    if not description:
        label = RESOURCE_LABELS_UZ.get(resource_type, resource_type)
        verb = ACTION_VERBS_UZ.get(matched_action, "amal bajardi")
        if resource_id:
            description = f"{label} (#{resource_id}) bo'yicha {verb}"
        else:
            description = f"{label} bo'yicha {verb}"

    return matched_action, resource_type, str(resource_id), description, extra_meta


def record_api_action(user, session, request, response, payload=None, changes=None):
    method = request.method.upper()
    path = request.path[:500]
    current_page = normalize_page_path(request.headers.get('X-Current-Page', ''))
    action, resource_type, resource_id, description, extra_meta = describe_api_action(
        method, path, response.status_code, payload=payload
    )

    changes_dict = changes or {}
    if not resource_id and changes_dict.get('object_id'):
        resource_id = str(changes_dict['object_id'])[:64]
    object_repr = str(changes_dict.get('object_repr', '') or '')[:255]

    return UserActivityLog.objects.create(
        user=user,
        session=session,
        action=action,
        method=method,
        endpoint=path,
        from_page=current_page,
        to_page=current_page,
        resource_type=resource_type,
        resource_id=resource_id,
        object_repr=object_repr,
        description=description[:500],
        status_code=response.status_code,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        changes=changes_dict,
        metadata=extra_meta,
    )
