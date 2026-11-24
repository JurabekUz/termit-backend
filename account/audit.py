import contextvars
import datetime
import decimal
import uuid

from django.db.models.fields.files import FieldFile
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.utils import timezone

TRACKED_APPS = {'account', 'appeal', 'area', 'damaged_object', 'info', 'plan'}
EXCLUDED_MODELS = {
    'account.UserSession',
    'account.UserActivityLog',
    'account.SuperAccessRateLimit',
    'account.SuperAccessChallenge',
}
SENSITIVE_FIELDS = {'password', 'last_login', 'secret', 'token'}
AUTO_TIMESTAMP_FIELDS = {'created_at', 'updated_at'}
SENSITIVE_PAYLOAD_KEYS = {
    'password',
    'new_password',
    'old_password',
    'key',
    'totp',
    'secret',
    'token',
    'access_token',
    'refresh_token',
    'challenge_token',
    'code',
}

_audit_ctx = contextvars.ContextVar('activity_audit_ctx', default=None)


class AuditCollector:
    def __init__(self):
        self.events = []
        self.snapshots = {}


def begin_audit_context():
    return _audit_ctx.set(AuditCollector())


def end_audit_context(token):
    _audit_ctx.reset(token)


def get_audit_collector():
    return _audit_ctx.get()


def _model_label(model_cls):
    return f"{model_cls._meta.app_label}.{model_cls.__name__}"


def _is_tracked_model(model_cls):
    if model_cls._meta.app_label not in TRACKED_APPS:
        return False
    return _model_label(model_cls) not in EXCLUDED_MODELS


def _safe_object_repr(instance):
    try:
        default_repr = f"{instance.__class__.__name__} object ({instance.pk})"
        text = str(instance).strip()
        if text and text != default_repr:
            return text[:255]
        for attr in ('full_name', 'name', 'title', 'cadastral_number', 'address'):
            val = getattr(instance, attr, None)
            if isinstance(val, str) and val.strip():
                return val.strip()[:255]
        return text[:255] if text else f"{instance.__class__.__name__} #{instance.pk}"
    except Exception:
        return f"{instance.__class__.__name__} #{getattr(instance, 'pk', '')}"


def _serialize_scalar(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime.datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.strftime('%d-%m-%Y %H:%M:%S')
    if isinstance(value, datetime.date):
        return value.strftime('%Y-%m-%d')
    if isinstance(value, datetime.time):
        return value.strftime('%H:%M:%S')
    if isinstance(value, FieldFile):
        return value.name or None
    if hasattr(value, 'geom_type'):
        try:
            if value.geom_type == 'Point':
                return [round(value.x, 6), round(value.y, 6)]
            return {'type': value.geom_type, 'num_coords': value.num_coords}
        except Exception:
            return str(value)[:200]
    if isinstance(value, str):
        return value[:1000] if len(value) > 1000 else value
    if isinstance(value, (list, tuple, dict)):
        return sanitize_payload(value)
    return str(value)[:500]


def _serialize_field_value(instance, field):
    raw_val = getattr(instance, field.attname, None)
    if raw_val is None:
        return None
    if field.is_relation and field.many_to_one:
        try:
            rel_obj = getattr(instance, field.name, None)
            if rel_obj is not None:
                return f"{str(rel_obj)[:120]} (#{raw_val})"
        except Exception:
            pass
    return _serialize_scalar(raw_val)


def sanitize_payload(data, depth=0):
    if depth > 5:
        return '...'
    if isinstance(data, dict):
        cleaned = {}
        for idx, (k, v) in enumerate(data.items()):
            if idx >= 60:
                cleaned['...'] = f"+{len(data) - 60} keys"
                break
            key_str = str(k)
            if key_str.lower() in SENSITIVE_PAYLOAD_KEYS:
                cleaned[key_str] = '***'
            elif key_str == 'coordinates' and isinstance(v, list):
                cleaned[key_str] = f"[geometry coordinates ({len(v)} items)]"
            else:
                cleaned[key_str] = sanitize_payload(v, depth + 1)
        return cleaned
    if isinstance(data, (list, tuple)):
        if len(data) > 50:
            return [sanitize_payload(item, depth + 1) for item in data[:50]] + [
                f"... (+{len(data) - 50} items)"
            ]
        return [sanitize_payload(item, depth + 1) for item in data]
    if isinstance(data, str):
        return data[:1000] + '...' if len(data) > 1000 else data
    if isinstance(data, (bool, int, float)) or data is None:
        return data
    return str(data)[:500]


def _on_pre_save(sender, instance, raw=False, update_fields=None, **kwargs):
    if raw:
        return
    collector = get_audit_collector()
    if collector is None or not _is_tracked_model(sender):
        return
    if instance.pk is None or instance._state.adding:
        return
    try:
        old_obj = sender._default_manager.filter(pk=instance.pk).first()
        if old_obj is not None:
            collector.snapshots[(id(instance), sender)] = old_obj
    except Exception:
        pass


def _on_post_save(sender, instance, created, raw=False, update_fields=None, **kwargs):
    if raw:
        return
    collector = get_audit_collector()
    if collector is None or not _is_tracked_model(sender):
        return

    model_name = _model_label(sender)
    object_id = str(instance.pk) if instance.pk is not None else ''
    object_repr = _safe_object_repr(instance)

    if created:
        fields_diff = {}
        for field in sender._meta.concrete_fields:
            if field.name in SENSITIVE_FIELDS or field.name in AUTO_TIMESTAMP_FIELDS:
                continue
            if field.primary_key:
                continue
            new_val = _serialize_field_value(instance, field)
            if new_val is not None and new_val != '':
                fields_diff[field.name] = {'old': None, 'new': new_val}

        collector.events.append({
            'model': model_name,
            'object_id': object_id,
            'object_repr': object_repr,
            'operation': 'create',
            'fields': fields_diff,
        })
        return

    old_obj = collector.snapshots.pop((id(instance), sender), None)
    if old_obj is None:
        return

    allowed_fields = set(update_fields) if update_fields is not None else None
    fields_diff = {}
    for field in sender._meta.concrete_fields:
        if field.name in SENSITIVE_FIELDS or field.name in AUTO_TIMESTAMP_FIELDS:
            continue
        if field.primary_key:
            continue
        if allowed_fields is not None and field.name not in allowed_fields and field.attname not in allowed_fields:
            continue
        old_raw = getattr(old_obj, field.attname, None)
        new_raw = getattr(instance, field.attname, None)
        if old_raw != new_raw:
            fields_diff[field.name] = {
                'old': _serialize_field_value(old_obj, field),
                'new': _serialize_field_value(instance, field),
            }

    if fields_diff:
        collector.events.append({
            'model': model_name,
            'object_id': object_id,
            'object_repr': object_repr,
            'operation': 'update',
            'fields': fields_diff,
        })


def _on_post_delete(sender, instance, **kwargs):
    collector = get_audit_collector()
    if collector is None or not _is_tracked_model(sender):
        return

    fields_diff = {}
    for field in sender._meta.concrete_fields:
        if field.name in SENSITIVE_FIELDS or field.name in AUTO_TIMESTAMP_FIELDS:
            continue
        if field.primary_key:
            continue
        old_val = _serialize_field_value(instance, field)
        if old_val is not None and old_val != '':
            fields_diff[field.name] = {'old': old_val, 'new': None}

    collector.events.append({
        'model': _model_label(sender),
        'object_id': str(instance.pk) if instance.pk is not None else '',
        'object_repr': _safe_object_repr(instance),
        'operation': 'delete',
        'fields': fields_diff,
    })


def _on_m2m_changed(sender, instance, action, reverse, model, pk_set, **kwargs):
    if reverse or action not in ('post_add', 'post_remove', 'post_clear'):
        return
    collector = get_audit_collector()
    if collector is None or not _is_tracked_model(instance.__class__):
        return

    field_name = None
    for m2m_field in instance._meta.many_to_many:
        if m2m_field.remote_field.through == sender:
            field_name = m2m_field.name
            break
    if not field_name:
        return

    try:
        current_values = [
            f"{str(obj)[:80]} (#{obj.pk})"
            for obj in getattr(instance, field_name).all()[:50]
        ]
    except Exception:
        current_values = sorted(str(pk) for pk in (pk_set or []))

    model_name = _model_label(instance.__class__)
    object_id = str(instance.pk) if instance.pk is not None else ''

    # Merge into existing event for the same object in this request when available
    for evt in reversed(collector.events):
        if evt['model'] == model_name and evt['object_id'] == object_id:
            evt['fields'][field_name] = {'old': None, 'new': current_values}
            return

    collector.events.append({
        'model': model_name,
        'object_id': object_id,
        'object_repr': _safe_object_repr(instance),
        'operation': 'update',
        'fields': {field_name: {'old': None, 'new': current_values}},
    })


def build_standard_changes_json(events, request_payload=None):
    """Build standard audit-diff/v1 JSON payload for UserActivityLog.changes."""
    if not events and not request_payload:
        return {}

    result = {'schema': 'audit-diff/v1'}
    if events:
        primary = events[0]
        result.update({
            'model': primary['model'],
            'object_id': primary['object_id'],
            'object_repr': primary['object_repr'],
            'operation': primary['operation'],
            'fields': primary['fields'],
        })
        if len(events) > 1:
            result['related'] = events[1:25]
    if request_payload:
        result['request_payload'] = request_payload
    return result


_signals_connected = False


def connect_audit_signals():
    global _signals_connected
    if _signals_connected:
        return
    pre_save.connect(_on_pre_save, dispatch_uid='account_audit_pre_save')
    post_save.connect(_on_post_save, dispatch_uid='account_audit_post_save')
    post_delete.connect(_on_post_delete, dispatch_uid='account_audit_post_delete')
    m2m_changed.connect(_on_m2m_changed, dispatch_uid='account_audit_m2m_changed')
    _signals_connected = True
