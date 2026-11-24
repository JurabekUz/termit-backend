import json
import logging

from account.activity import (
    get_session_from_token,
    normalize_page_path,
    record_api_action,
    touch_session,
)
from account.audit import (
    begin_audit_context,
    build_standard_changes_json,
    end_audit_context,
    get_audit_collector,
    sanitize_payload,
)

logger = logging.getLogger(__name__)

MUTATING_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}
EXCLUDED_PREFIXES = (
    '/api/auth/',
    '/api/activity-logs',
)


def _extract_json_body(request):
    content_type = (request.content_type or '').lower()
    if 'application/json' not in content_type:
        return None
    try:
        raw = request.body
        if not raw or len(raw) > 262144:
            return None
        data = json.loads(raw.decode('utf-8'))
        return sanitize_payload(data)
    except Exception:
        return None


def _extract_form_payload(request):
    content_type = (request.content_type or '').lower()
    if 'application/json' in content_type:
        return None
    data = {}
    try:
        if request.POST:
            for key in request.POST.keys():
                vals = request.POST.getlist(key)
                data[key] = vals[0] if len(vals) == 1 else vals
        if request.FILES:
            for key in request.FILES.keys():
                files = request.FILES.getlist(key)
                data[f"{key}_files"] = [f.name for f in files]
    except Exception:
        return None
    return sanitize_payload(data) if data else None


class ActivityLogMiddleware:
    """Record authenticated user mutating API actions, field diffs, and refresh session last_seen_at."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path or ''
        method = (request.method or '').upper()
        should_track_action = (
            method in MUTATING_METHODS
            and path.startswith('/api/')
            and not any(path.startswith(prefix) for prefix in EXCLUDED_PREFIXES)
        )
        json_payload = _extract_json_body(request) if should_track_action else None
        audit_token = begin_audit_context() if should_track_action else None

        try:
            response = self.get_response(request)
            collector = get_audit_collector() if should_track_action else None
            events = list(collector.events) if collector else []
        finally:
            if audit_token is not None:
                end_audit_context(audit_token)

        try:
            user = getattr(request, '_activity_user', None)
            if not user or not getattr(user, 'is_authenticated', False):
                return response

            token = getattr(request, '_activity_token', None)
            session = get_session_from_token(token, user=user)
            current_page = normalize_page_path(request.headers.get('X-Current-Page', ''))

            if session is not None:
                touch_session(session, current_page=current_page or None)

            if should_track_action and 200 <= response.status_code < 400:
                request_payload = json_payload if json_payload is not None else _extract_form_payload(request)
                changes = build_standard_changes_json(events, request_payload=request_payload)
                summary_payload = (
                    {k: request_payload[k] for k in ('status', 'apl_status') if k in request_payload}
                    if isinstance(request_payload, dict)
                    else None
                )
                record_api_action(
                    user,
                    session,
                    request,
                    response,
                    payload=summary_payload,
                    changes=changes,
                )
        except Exception:
            logger.exception("Failed to record user activity log for %s %s", method, path)

        return response
