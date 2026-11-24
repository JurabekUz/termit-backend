import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Coalesce, TruncDay, TruncMonth, TruncYear
from django.utils import timezone

from account.models import UserRoles
from appeal.models import Appeal, AppealStatus
from area.models import District, Mahalla, MahallaStatus, OpenArea, Region
from damaged_object.models import (
    DamagedObject,
    DamagedObjectFlow,
    DamagedStatus,
    DamagedTypes,
    MahallaInfo,
    ObjectTypes,
    OpenAreaInfo,
    PropertyType,
)
from info.models import OpenAreaType
from plan.models import Plan, PlanItem, PlanRegionStatus, PlanStatus

BASE_DIR = Path(__file__).resolve().parent.parent

CONFIRMED_STATUSES = [
    DamagedStatus.approved,
    DamagedStatus.in_process,
    DamagedStatus.completed,
    DamagedStatus.cleaned,
]
ACTIVE_STATUSES = [DamagedStatus.approved, DamagedStatus.in_process]
CLEANED_STATUSES = [DamagedStatus.completed, DamagedStatus.cleaned]

OBJECT_TYPE_KEYS = {
    ObjectTypes.households: 'households',
    ObjectTypes.social_objects: 'social_objects',
    ObjectTypes.historical_sites: 'historical_sites',
    ObjectTypes.adm_buildings: 'adm_buildings',
}

PROPERTY_TYPE_KEYS = {
    PropertyType.INDIVIDUAL_HOUSE: 'INDIVIDUAL_HOUSE',
    PropertyType.APARTMENT: 'APARTMENT',
    PropertyType.NON_RESIDENTIAL: 'NON_RESIDENTIAL',
    PropertyType.LAND: 'LAND',
    PropertyType.MULTI_APARTMENT_BUILDING: 'MULTI_APARTMENT_BUILDING',
    PropertyType.ROAD_LAND: 'ROAD_LAND',
    PropertyType.AGRICULTURAL_LAND: 'AGRICULTURAL_LAND',
    PropertyType.FOREST: 'FOREST',
    PropertyType.WATER: 'WATER',
    PropertyType.PROTECTED_AREA: 'PROTECTED_AREA',
    PropertyType.STATE_RESERVE: 'STATE_RESERVE',
    PropertyType.SPECIAL_HOUSE: 'SPECIAL_HOUSE',
}


def _parse_int(val):
    if val is None:
        return None
    s = str(val).strip()
    return int(s) if s.isdigit() else None


def _parse_date(val):
    if not val:
        return None
    s = str(val).strip()
    for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d.%m.%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _pct_change(curr: float, prev: float) -> float:
    if prev == 0:
        return 100.0 if curr > 0 else 0.0
    return round(((curr - prev) / prev) * 100.0, 1)


def _read_republic_meta() -> dict:
    file_path = BASE_DIR / 'area' / 'data' / 'republic_stat.json'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def resolve_scope(request) -> dict:
    region_code = _parse_int(request.query_params.get('region'))
    district_code = _parse_int(request.query_params.get('district'))
    mahalla_param = _parse_int(request.query_params.get('mahalla'))
    date_from = _parse_date(request.query_params.get('from') or request.query_params.get('date_from'))
    date_to = _parse_date(request.query_params.get('to') or request.query_params.get('date_to'))

    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from

    user = getattr(request, 'user', None)
    if user and getattr(user, 'is_authenticated', False) and user.role == UserRoles.RM:
        allowed_codes = set()
        if user.region_id:
            allowed_codes.add(user.region.code)
        allowed_codes.update(user.regions.values_list('code', flat=True))
        if allowed_codes:
            if region_code not in allowed_codes:
                region_code = user.region.code if user.region_id else sorted(allowed_codes)[0]
                # Clear district/mahalla if forced region differs
                if district_code and not District.objects.filter(code=district_code, parent_code=region_code).exists():
                    district_code = None
                    mahalla_param = None

    mahalla_obj = None
    if mahalla_param:
        mahalla_obj = Mahalla.objects.select_related('district', 'district__region').filter(
            Q(id=mahalla_param) | Q(code=mahalla_param)
        ).first()
        if mahalla_obj:
            district_code = mahalla_obj.district.code
            region_code = mahalla_obj.district.region.code

    district_obj = None
    if district_code:
        district_obj = District.objects.select_related('region').filter(code=district_code).first()
        if district_obj:
            region_code = district_obj.region.code

    region_obj = None
    if region_code:
        region_obj = Region.objects.filter(code=region_code).first()

    if mahalla_obj:
        scope_level = 'mahalla'
        scope_name = mahalla_obj.name
    elif district_obj:
        scope_level = 'district'
        scope_name = district_obj.name
    elif region_obj:
        scope_level = 'region'
        scope_name = region_obj.name
    else:
        scope_level = 'republic'
        scope_name = "O'zbekiston Respublikasi"

    return {
        'region_code': region_code,
        'district_code': district_code,
        'mahalla_id': mahalla_obj.id if mahalla_obj else None,
        'mahalla_code': mahalla_obj.code if mahalla_obj else None,
        'date_from': date_from,
        'date_to': date_to,
        'scope_level': scope_level,
        'scope_name': scope_name,
        'region_obj': region_obj,
        'district_obj': district_obj,
        'mahalla_obj': mahalla_obj,
    }


def _filter_damaged_objects(qs, scope: dict, apply_dates: bool = True):
    if scope['mahalla_id']:
        qs = qs.filter(mahallainfo__mahalla_id=scope['mahalla_id'])
    elif scope['district_code']:
        qs = qs.filter(district__code=scope['district_code'])
    elif scope['region_code']:
        qs = qs.filter(district__parent_code=scope['region_code'])

    if apply_dates:
        if scope['date_from']:
            qs = qs.filter(created_at__date__gte=scope['date_from'])
        if scope['date_to']:
            qs = qs.filter(created_at__date__lte=scope['date_to'])
    return qs


def _filter_mahallas(qs, scope: dict):
    if scope['mahalla_id']:
        return qs.filter(id=scope['mahalla_id'])
    if scope['district_code']:
        return qs.filter(district__code=scope['district_code'])
    if scope['region_code']:
        return qs.filter(district__parent_code=scope['region_code'])
    return qs


def _filter_appeals(qs, scope: dict, apply_dates: bool = True):
    if scope['district_code']:
        qs = qs.filter(district__code=scope['district_code'])
    elif scope['region_code']:
        qs = qs.filter(district__parent_code=scope['region_code'])

    if apply_dates:
        if scope['date_from']:
            qs = qs.filter(created_at__date__gte=scope['date_from'])
        if scope['date_to']:
            qs = qs.filter(created_at__date__lte=scope['date_to'])
    return qs


def _filter_flows(qs, scope: dict, apply_dates: bool = True):
    if scope['mahalla_id']:
        qs = qs.filter(damaged_object__mahallainfo__mahalla_id=scope['mahalla_id'])
    elif scope['district_code']:
        qs = qs.filter(damaged_object__district__code=scope['district_code'])
    elif scope['region_code']:
        qs = qs.filter(damaged_object__district__parent_code=scope['region_code'])

    if apply_dates:
        if scope['date_from']:
            qs = qs.filter(created_at__date__gte=scope['date_from'])
        if scope['date_to']:
            qs = qs.filter(created_at__date__lte=scope['date_to'])
    return qs


def _filter_plan_items(qs, scope: dict):
    if scope['mahalla_id']:
        return qs.filter(item__mahallainfo__mahalla_id=scope['mahalla_id'])
    if scope['district_code']:
        return qs.filter(item__district__code=scope['district_code'])
    if scope['region_code']:
        return qs.filter(item__district__parent_code=scope['region_code'])
    return qs


def _month_buckets(ref_date: date, n: int = 12):
    buckets = []
    y, m = ref_date.year, ref_date.month
    for _ in range(n):
        buckets.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    buckets.reverse()
    return buckets


def _sparkline_monthly(qs, date_field='created_at', ref_date: date = None) -> list:
    ref_date = ref_date or timezone.now().date()
    buckets = _month_buckets(ref_date, 12)
    start_year, start_month = buckets[0]
    start_dt = date(start_year, start_month, 1)
    rows = (
        qs.filter(**{f'{date_field}__date__gte': start_dt, f'{date_field}__date__lte': ref_date})
        .annotate(month=TruncMonth(date_field))
        .values('month')
        .annotate(c=Count('id'))
    )
    counts_map = {}
    for r in rows:
        if r['month']:
            counts_map[(r['month'].year, r['month'].month)] = r['c']
    return [counts_map.get(b, 0) for b in buckets]


def _scope_population(scope: dict) -> int:
    if scope['district_obj']:
        return scope['district_obj'].population or 0
    if scope['region_obj']:
        return scope['region_obj'].population or 0
    meta = _read_republic_meta()
    pop = meta.get('population')
    if pop:
        return int(pop)
    return Region.objects.aggregate(total=Coalesce(Sum('population'), 0))['total']


def _comparison_windows(scope: dict):
    today = timezone.now().date()
    d_from = scope['date_from']
    d_to = scope['date_to']
    if d_from and d_to:
        span = max((d_to - d_from).days + 1, 1)
        prev_to = d_from - timedelta(days=1)
        prev_from = prev_to - timedelta(days=span - 1)
        return (d_from, d_to), (prev_from, prev_to)
    curr_to = d_to or today
    curr_from = curr_to - timedelta(days=29)
    prev_to = curr_from - timedelta(days=1)
    prev_from = prev_to - timedelta(days=29)
    return (curr_from, curr_to), (prev_from, prev_to)


def get_dashboard_overview(scope: dict) -> dict:
    today = timezone.now().date()
    (curr_from, curr_to), (prev_from, prev_to) = _comparison_windows(scope)

    dmg_qs = _filter_damaged_objects(DamagedObject.objects.all(), scope, apply_dates=True)
    dmg_unbounded_qs = _filter_damaged_objects(DamagedObject.objects.all(), scope, apply_dates=False)

    dmg_counts = dmg_qs.aggregate(
        total=Count('id'),
        new_count=Count('id', filter=Q(status=DamagedStatus.new)),
        approved_count=Count('id', filter=Q(status=DamagedStatus.approved)),
        in_process_count=Count('id', filter=Q(status=DamagedStatus.in_process)),
        cleaned_count=Count('id', filter=Q(status__in=CLEANED_STATUSES)),
        rejected_count=Count('id', filter=Q(status=DamagedStatus.rejected)),
        confirmed_count=Count('id', filter=Q(status__in=CONFIRMED_STATUSES)),
    )

    curr_period_dmg = dmg_unbounded_qs.filter(created_at__date__gte=curr_from, created_at__date__lte=curr_to).count()
    prev_period_dmg = dmg_unbounded_qs.filter(created_at__date__gte=prev_from, created_at__date__lte=prev_to).count()

    flow_qs = _filter_flows(DamagedObjectFlow.objects.filter(status__in=CLEANED_STATUSES), scope, apply_dates=False)
    curr_period_cleaned = flow_qs.filter(created_at__date__gte=curr_from, created_at__date__lte=curr_to).values('damaged_object_id').distinct().count()
    prev_period_cleaned = flow_qs.filter(created_at__date__gte=prev_from, created_at__date__lte=prev_to).values('damaged_object_id').distinct().count()

    confirmed_cnt = dmg_counts['confirmed_count']
    cleaned_cnt = dmg_counts['cleaned_count']
    active_cnt = dmg_counts['approved_count'] + dmg_counts['in_process_count']
    completion_rate = round((cleaned_cnt / confirmed_cnt) * 100, 1) if confirmed_cnt > 0 else 0.0

    # Open areas (hectares)
    oa_total_qs = OpenArea.objects.all()
    if scope['district_code']:
        oa_total_qs = oa_total_qs.filter(district__code=scope['district_code'])
    elif scope['region_code']:
        oa_total_qs = oa_total_qs.filter(district__parent_code=scope['region_code'])
    total_open_ha = float(oa_total_qs.aggregate(s=Coalesce(Sum('hectare'), Decimal('0.00')))['s'] or 0.0)

    oa_info_qs = OpenAreaInfo.objects.all()
    if scope['district_code']:
        oa_info_qs = oa_info_qs.filter(district__code=scope['district_code'])
    elif scope['region_code']:
        oa_info_qs = oa_info_qs.filter(district__parent_code=scope['region_code'])
    if scope['date_from']:
        oa_info_qs = oa_info_qs.filter(created_at__date__gte=scope['date_from'])
    if scope['date_to']:
        oa_info_qs = oa_info_qs.filter(created_at__date__lte=scope['date_to'])

    oa_agg = oa_info_qs.aggregate(
        damaged_ha=Coalesce(Sum('hectares', filter=Q(status__in=CONFIRMED_STATUSES)), Decimal('0.00')),
        cleaned_ha=Coalesce(Sum('hectares', filter=Q(status__in=CLEANED_STATUSES)), Decimal('0.00')),
    )
    damaged_ha = round(float(oa_agg['damaged_ha'] or 0.0), 2)
    cleaned_ha = round(float(oa_agg['cleaned_ha'] or 0.0), 2)
    damaged_ha_pct = round((damaged_ha / total_open_ha) * 100, 2) if total_open_ha > 0 else 0.0

    oa_unbounded = OpenAreaInfo.objects.all()
    if scope['district_code']:
        oa_unbounded = oa_unbounded.filter(district__code=scope['district_code'])
    elif scope['region_code']:
        oa_unbounded = oa_unbounded.filter(district__parent_code=scope['region_code'])
    curr_oa_ha = float(oa_unbounded.filter(created_at__date__gte=curr_from, created_at__date__lte=curr_to).aggregate(s=Coalesce(Sum('hectares'), Decimal('0.00')))['s'] or 0.0)
    prev_oa_ha = float(oa_unbounded.filter(created_at__date__gte=prev_from, created_at__date__lte=prev_to).aggregate(s=Coalesce(Sum('hectares'), Decimal('0.00')))['s'] or 0.0)

    # Plan execution
    plan_items_qs = _filter_plan_items(PlanItem.objects.exclude(plan__status=PlanStatus.draft), scope)
    if scope['date_from']:
        plan_items_qs = plan_items_qs.filter(plan__to_date__gte=scope['date_from'])
    if scope['date_to']:
        plan_items_qs = plan_items_qs.filter(plan__from_date__lte=scope['date_to'])
    plan_item_agg = plan_items_qs.aggregate(
        total=Count('id'),
        performed=Count('id', filter=Q(is_performed=True)),
    )
    plan_total_items = plan_item_agg['total']
    plan_performed = plan_item_agg['performed']
    plan_completion_pct = round((plan_performed / plan_total_items) * 100, 1) if plan_total_items > 0 else 0.0

    plans_scope_qs = Plan.objects.exclude(status=PlanStatus.draft)
    if scope['mahalla_id']:
        plans_scope_qs = plans_scope_qs.filter(items__item__mahallainfo__mahalla_id=scope['mahalla_id']).distinct()
    elif scope['district_code']:
        plans_scope_qs = plans_scope_qs.filter(items__item__district__code=scope['district_code']).distinct()
    elif scope['region_code']:
        plans_scope_qs = plans_scope_qs.filter(
            Q(region_statuses__region__code=scope['region_code']) | Q(items__item__district__parent_code=scope['region_code'])
        ).distinct()

    active_plans_cnt = plans_scope_qs.filter(status__in=[PlanStatus.approved, PlanStatus.in_process]).count()
    overdue_plans_cnt = plans_scope_qs.filter(
        status__in=[PlanStatus.approved, PlanStatus.in_process],
        to_date__lt=today,
    ).count()

    # Appeals
    appeal_qs = _filter_appeals(Appeal.objects.all(), scope, apply_dates=True)
    appeal_unbounded = _filter_appeals(Appeal.objects.all(), scope, apply_dates=False)
    apl_agg = appeal_qs.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status__in=[AppealStatus.new, AppealStatus.in_process, AppealStatus.sent])),
        approved=Count('id', filter=Q(status=AppealStatus.approved)),
        rejected=Count('id', filter=Q(status=AppealStatus.rejected)),
    )
    apl_total = apl_agg['total']
    apl_rate = round((apl_agg['approved'] / apl_total) * 100, 1) if apl_total > 0 else 0.0

    # Mahalla risk counts
    mahalla_qs = _filter_mahallas(Mahalla.objects.all(), scope)
    m_agg = mahalla_qs.aggregate(
        total=Count('id'),
        green=Count('id', filter=Q(status=MahallaStatus.green)),
        yellow=Count('id', filter=Q(status=MahallaStatus.yellow)),
        red=Count('id', filter=Q(status=MahallaStatus.red)),
        households=Coalesce(Sum('households'), 0),
        social_objects=Coalesce(Sum('social_objects'), 0),
        historical_sites=Coalesce(Sum('historical_sites'), 0),
        adm_buildings=Coalesce(Sum('adm_buildings'), 0),
    )
    m_total = m_agg['total']

    # Building categories breakdown
    mi_qs = MahallaInfo.objects.all()
    if scope['mahalla_id']:
        mi_qs = mi_qs.filter(mahalla_id=scope['mahalla_id'])
    elif scope['district_code']:
        mi_qs = mi_qs.filter(district__code=scope['district_code'])
    elif scope['region_code']:
        mi_qs = mi_qs.filter(district__parent_code=scope['region_code'])
    if scope['date_from']:
        mi_qs = mi_qs.filter(created_at__date__gte=scope['date_from'])
    if scope['date_to']:
        mi_qs = mi_qs.filter(created_at__date__lte=scope['date_to'])

    mi_by_type = {
        row['object_type']: row
        for row in mi_qs.values('object_type').annotate(
            damaged=Count('id', filter=Q(status__in=CONFIRMED_STATUSES)),
            cleaned=Count('id', filter=Q(status__in=CLEANED_STATUSES)),
        )
    }

    building_categories = {}
    for ot_id, ot_key in OBJECT_TYPE_KEYS.items():
        total_stock = int(m_agg.get(ot_key) or 0)
        stats_row = mi_by_type.get(ot_id, {'damaged': 0, 'cleaned': 0})
        damaged_cnt = stats_row['damaged']
        cleaned_cat_cnt = stats_row['cleaned']
        pct = round((damaged_cnt / total_stock) * 100, 2) if total_stock > 0 else 0.0
        building_categories[ot_key] = {
            'damaged': damaged_cnt,
            'cleaned': cleaned_cat_cnt,
            'total': total_stock,
            'pct': pct,
        }

    # Normalized benchmarks
    population = _scope_population(scope)
    per_10k_pop = round((confirmed_cnt / population) * 10000, 2) if population > 0 else 0.0
    total_hh = int(m_agg['households'] or 0)
    per_1k_hh = round((building_categories['households']['damaged'] / total_hh) * 1000, 2) if total_hh > 0 else 0.0

    # Highest risk sub-area in current scope
    highest_risk_area = None
    if not scope['district_code'] and not scope['region_code']:
        top_reg = (
            Region.objects.annotate(
                dmg=Count('district__damaged_objects', filter=Q(district__damaged_objects__status__in=CONFIRMED_STATUSES))
            )
            .order_by('-dmg')
            .first()
        )
        if top_reg:
            reg_per_10k = round((top_reg.dmg / top_reg.population) * 10000, 2) if top_reg.population else 0.0
            highest_risk_area = {'name': top_reg.name, 'code': top_reg.code, 'count': top_reg.dmg, 'per_10k': reg_per_10k}
    elif scope['region_code'] and not scope['district_code']:
        top_dist = (
            District.objects.filter(parent_code=scope['region_code'])
            .annotate(dmg=Count('damaged_objects', filter=Q(damaged_objects__status__in=CONFIRMED_STATUSES)))
            .order_by('-dmg')
            .first()
        )
        if top_dist:
            d_per_10k = round((top_dist.dmg / top_dist.population) * 10000, 2) if top_dist.population else 0.0
            highest_risk_area = {'name': top_dist.name, 'code': top_dist.code, 'count': top_dist.dmg, 'per_10k': d_per_10k}
    elif scope['district_code']:
        top_m = (
            Mahalla.objects.filter(district__code=scope['district_code'])
            .annotate(dmg=Count('damaged_objects', filter=Q(damaged_objects__status__in=CONFIRMED_STATUSES)))
            .order_by('-dmg')
            .first()
        )
        if top_m:
            highest_risk_area = {'name': top_m.name, 'code': top_m.code, 'count': top_m.dmg, 'per_10k': float(top_m.damaged_percent)}

    # Peak month in unbounded scope
    peak_row = (
        dmg_unbounded_qs.annotate(m=TruncMonth('created_at'))
        .values('m')
        .annotate(c=Count('id'))
        .order_by('-c')
        .first()
    )
    peak_month = {
        'label': peak_row['m'].strftime('%Y-%m') if peak_row and peak_row['m'] else None,
        'count': peak_row['c'] if peak_row else 0,
    }

    last_updated_obj = DamagedObject.objects.order_by('-updated_at').values_list('updated_at', flat=True).first()
    last_updated = (last_updated_obj.date() if last_updated_obj else today).isoformat()

    return {
        'meta': {
            'last_updated': last_updated,
            'scope_level': scope['scope_level'],
            'scope_name': scope['scope_name'],
            'date_from': scope['date_from'].isoformat() if scope['date_from'] else None,
            'date_to': scope['date_to'].isoformat() if scope['date_to'] else None,
        },
        'narrative': {
            'total_mahallas': m_total,
            'red_mahallas': m_agg['red'],
            'yellow_mahallas': m_agg['yellow'],
            'green_mahallas': m_agg['green'],
            'active_damaged': active_cnt,
            'cleaned_count': cleaned_cnt,
            'cleaned_rate': completion_rate,
            'period_new_count': curr_period_dmg,
            'top_risk_area_name': highest_risk_area['name'] if highest_risk_area else None,
        },
        'kpis': {
            'damaged_total': {
                'total': dmg_counts['total'],
                'confirmed': confirmed_cnt,
                'active': active_cnt,
                'new_count': dmg_counts['new_count'],
                'in_process_count': dmg_counts['in_process_count'],
                'trend_pct': _pct_change(curr_period_dmg, prev_period_dmg),
                'prev_period_count': prev_period_dmg,
                'sparkline': _sparkline_monthly(dmg_unbounded_qs, 'created_at', curr_to),
            },
            'cleaned_objects': {
                'cleaned_count': cleaned_cnt,
                'total_confirmed': confirmed_cnt,
                'completion_rate_pct': completion_rate,
                'trend_pct': _pct_change(curr_period_cleaned, prev_period_cleaned),
                'sparkline': _sparkline_monthly(flow_qs, 'created_at', curr_to),
            },
            'open_areas': {
                'damaged_ha': damaged_ha,
                'cleaned_ha': cleaned_ha,
                'total_ha': round(total_open_ha, 2),
                'damaged_pct': damaged_ha_pct,
                'trend_pct': _pct_change(curr_oa_ha, prev_oa_ha),
                'sparkline': _sparkline_monthly(oa_unbounded, 'created_at', curr_to),
            },
            'plan_execution': {
                'performed_items': plan_performed,
                'total_items': plan_total_items,
                'completion_pct': plan_completion_pct,
                'active_plans': active_plans_cnt,
                'overdue_plans': overdue_plans_cnt,
            },
            'appeals': {
                'total': apl_total,
                'pending': apl_agg['pending'],
                'approved': apl_agg['approved'],
                'rejected': apl_agg['rejected'],
                'approval_rate_pct': apl_rate,
                'sparkline': _sparkline_monthly(appeal_unbounded, 'created_at', curr_to),
            },
            'mahalla_risk': {
                'total': m_total,
                'red': m_agg['red'],
                'yellow': m_agg['yellow'],
                'green': m_agg['green'],
                'red_pct': round((m_agg['red'] / m_total) * 100, 1) if m_total else 0.0,
                'yellow_pct': round((m_agg['yellow'] / m_total) * 100, 1) if m_total else 0.0,
                'green_pct': round((m_agg['green'] / m_total) * 100, 1) if m_total else 0.0,
            },
        },
        'building_categories': building_categories,
        'normalized': {
            'population': population,
            'per_10k_population': per_10k_pop,
            'per_1k_households': per_1k_hh,
            'highest_risk_area': highest_risk_area,
            'peak_month': peak_month,
        },
    }


def get_dynamics_stats(scope: dict, period: str = 'monthly') -> dict:
    today = timezone.now().date()
    dmg_qs = _filter_damaged_objects(DamagedObject.objects.all(), scope, apply_dates=True)
    flow_qs = _filter_flows(
        DamagedObjectFlow.objects.filter(status__in=CLEANED_STATUSES),
        scope,
        apply_dates=True,
    )

    if period == 'daily':
        if not scope['date_from'] and not scope['date_to']:
            start_d = today - timedelta(days=29)
            end_d = today
            dmg_period_qs = dmg_qs.filter(created_at__date__gte=start_d, created_at__date__lte=end_d)
            flow_period_qs = flow_qs.filter(created_at__date__gte=start_d, created_at__date__lte=end_d)
        else:
            start_d = scope['date_from'] or (today - timedelta(days=29))
            end_d = scope['date_to'] or today
            dmg_period_qs = dmg_qs
            flow_period_qs = flow_qs

        dmg_rows = (
            dmg_period_qs.annotate(bucket=TruncDay('created_at'))
            .values('bucket')
            .annotate(
                total=Count('id'),
                mahalla=Count('id', filter=Q(type=DamagedTypes.mahalla)),
                open_area=Count('id', filter=Q(type=DamagedTypes.open_area)),
            )
        )
        flow_rows = (
            flow_period_qs.annotate(bucket=TruncDay('created_at'))
            .values('bucket')
            .annotate(cleaned=Count('damaged_object_id', distinct=True))
        )

        dmg_map = {r['bucket'].date(): r for r in dmg_rows if r['bucket']}
        flow_map = {r['bucket'].date(): r['cleaned'] for r in flow_rows if r['bucket']}

        labels, det_total, det_mahalla, det_oa, cleaned_arr = [], [], [], [], []
        cur = start_d
        while cur <= end_d:
            labels.append(cur.strftime('%d.%m'))
            d_row = dmg_map.get(cur, {})
            det_total.append(d_row.get('total', 0))
            det_mahalla.append(d_row.get('mahalla', 0))
            det_oa.append(d_row.get('open_area', 0))
            cleaned_arr.append(flow_map.get(cur, 0))
            cur += timedelta(days=1)

    elif period == 'yearly':
        dmg_rows = (
            dmg_qs.annotate(bucket=TruncYear('created_at'))
            .values('bucket')
            .annotate(
                total=Count('id'),
                mahalla=Count('id', filter=Q(type=DamagedTypes.mahalla)),
                open_area=Count('id', filter=Q(type=DamagedTypes.open_area)),
            )
            .order_by('bucket')
        )
        flow_rows = (
            flow_qs.annotate(bucket=TruncYear('created_at'))
            .values('bucket')
            .annotate(cleaned=Count('damaged_object_id', distinct=True))
        )
        flow_map = {r['bucket'].year: r['cleaned'] for r in flow_rows if r['bucket']}
        years = sorted({r['bucket'].year for r in dmg_rows if r['bucket']} | set(flow_map.keys()))
        dmg_map = {r['bucket'].year: r for r in dmg_rows if r['bucket']}

        labels, det_total, det_mahalla, det_oa, cleaned_arr = [], [], [], [], []
        for y in years:
            labels.append(str(y))
            d_row = dmg_map.get(y, {})
            det_total.append(d_row.get('total', 0))
            det_mahalla.append(d_row.get('mahalla', 0))
            det_oa.append(d_row.get('open_area', 0))
            cleaned_arr.append(flow_map.get(y, 0))

    else:  # monthly (default: last 12 months or filtered range)
        if not scope['date_from'] and not scope['date_to']:
            buckets = _month_buckets(today, 12)
            start_d = date(buckets[0][0], buckets[0][1], 1)
            dmg_period_qs = dmg_qs.filter(created_at__date__gte=start_d)
            flow_period_qs = flow_qs.filter(created_at__date__gte=start_d)
        else:
            dmg_period_qs = dmg_qs
            flow_period_qs = flow_qs
            start_d = scope['date_from'] or date(today.year, 1, 1)
            end_d = scope['date_to'] or today
            buckets = []
            y, m = start_d.year, start_d.month
            while (y, m) <= (end_d.year, end_d.month):
                buckets.append((y, m))
                m += 1
                if m > 12:
                    m = 1
                    y += 1

        dmg_rows = (
            dmg_period_qs.annotate(bucket=TruncMonth('created_at'))
            .values('bucket')
            .annotate(
                total=Count('id'),
                mahalla=Count('id', filter=Q(type=DamagedTypes.mahalla)),
                open_area=Count('id', filter=Q(type=DamagedTypes.open_area)),
            )
        )
        flow_rows = (
            flow_period_qs.annotate(bucket=TruncMonth('created_at'))
            .values('bucket')
            .annotate(cleaned=Count('damaged_object_id', distinct=True))
        )
        dmg_map = {(r['bucket'].year, r['bucket'].month): r for r in dmg_rows if r['bucket']}
        flow_map = {(r['bucket'].year, r['bucket'].month): r['cleaned'] for r in flow_rows if r['bucket']}

        labels, det_total, det_mahalla, det_oa, cleaned_arr = [], [], [], [], []
        for y, m in buckets:
            labels.append(f'{m:02d}.{y}')
            d_row = dmg_map.get((y, m), {})
            det_total.append(d_row.get('total', 0))
            det_mahalla.append(d_row.get('mahalla', 0))
            det_oa.append(d_row.get('open_area', 0))
            cleaned_arr.append(flow_map.get((y, m), 0))

    # Year-over-Year comparison (current year vs previous year, unbounded by date filter)
    curr_year = scope['date_to'].year if scope['date_to'] else today.year
    prev_year = curr_year - 1
    yoy_qs = _filter_damaged_objects(DamagedObject.objects.all(), scope, apply_dates=False).filter(
        created_at__year__in=[curr_year, prev_year]
    )
    yoy_rows = (
        yoy_qs.annotate(m=TruncMonth('created_at'))
        .values('m')
        .annotate(c=Count('id'))
    )
    yoy_map = {(r['m'].year, r['m'].month): r['c'] for r in yoy_rows if r['m']}

    return {
        'period': period,
        'labels': labels,
        'series': {
            'detected_total': det_total,
            'detected_mahalla': det_mahalla,
            'detected_open_area': det_oa,
            'cleaned_total': cleaned_arr,
        },
        'yoy_comparison': {
            'months': [f'{m:02d}' for m in range(1, 13)],
            'current_year': curr_year,
            'prev_year': prev_year,
            'current_series': [yoy_map.get((curr_year, m), 0) for m in range(1, 13)],
            'prev_series': [yoy_map.get((prev_year, m), 0) for m in range(1, 13)],
        },
    }


def get_composition_stats(scope: dict) -> dict:
    dmg_qs = _filter_damaged_objects(DamagedObject.objects.all(), scope, apply_dates=True)
    total_dmg = dmg_qs.count()

    # 1. Object types + open areas
    mi_qs = MahallaInfo.objects.filter(id__in=dmg_qs.values('id'))
    mi_counts = {
        r['object_type']: r['c']
        for r in mi_qs.values('object_type').annotate(c=Count('id'))
    }
    oa_count = dmg_qs.filter(type=DamagedTypes.open_area).count()

    by_object_type = []
    for ot_id, ot_key in OBJECT_TYPE_KEYS.items():
        cnt = mi_counts.get(ot_id, 0)
        by_object_type.append({
            'key': ot_key,
            'count': cnt,
            'pct': round((cnt / total_dmg) * 100, 1) if total_dmg else 0.0,
        })
    by_object_type.append({
        'key': 'open_area',
        'count': oa_count,
        'pct': round((oa_count / total_dmg) * 100, 1) if total_dmg else 0.0,
    })

    # 2. Property types
    prop_rows = (
        dmg_qs.exclude(property_type__isnull=True)
        .values('property_type')
        .annotate(c=Count('id'))
        .order_by('-c')
    )
    by_property_type = [
        {
            'code': r['property_type'],
            'key': PROPERTY_TYPE_KEYS.get(r['property_type'], 'LAND'),
            'count': r['c'],
            'pct': round((r['c'] / total_dmg) * 100, 1) if total_dmg else 0.0,
        }
        for r in prop_rows
    ]

    # 3. Open area types
    oa_info_qs = OpenAreaInfo.objects.filter(id__in=dmg_qs.values('id'))
    oa_type_rows = (
        oa_info_qs.values('area_type__id', 'area_type__name')
        .annotate(c=Count('id'), hectares=Coalesce(Sum('hectares'), Decimal('0.00')))
        .order_by('-hectares')
    )
    by_open_area_type = [
        {
            'id': r['area_type__id'],
            'name': r['area_type__name'] or 'Noma’lum',
            'count': r['c'],
            'hectares': round(float(r['hectares'] or 0.0), 2),
        }
        for r in oa_type_rows
    ]

    # 4. Status funnel
    status_counts = {
        r['status']: r['c']
        for r in dmg_qs.values('status').annotate(c=Count('id'))
    }
    ordered_statuses = [
        DamagedStatus.new,
        DamagedStatus.approved,
        DamagedStatus.in_process,
        DamagedStatus.completed,
        DamagedStatus.cleaned,
        DamagedStatus.rejected,
    ]
    status_funnel = [
        {
            'status': st,
            'count': status_counts.get(st, 0),
            'pct': round((status_counts.get(st, 0) / total_dmg) * 100, 1) if total_dmg else 0.0,
        }
        for st in ordered_statuses
    ]

    return {
        'total': total_dmg,
        'by_object_type': by_object_type,
        'by_property_type': by_property_type,
        'by_open_area_type': by_open_area_type,
        'status_funnel': status_funnel,
    }


def _risk_level(red_cnt: int, per_10k: float, avg_per_10k: float) -> str:
    if red_cnt > 0 or (avg_per_10k > 0 and per_10k >= avg_per_10k * 1.4):
        return 'high'
    if per_10k > 0:
        return 'medium'
    return 'low'


def get_regional_ranking(scope: dict) -> dict:
    dmg_date_q = Q()
    if scope['date_from']:
        dmg_date_q &= Q(created_at__date__gte=scope['date_from'])
    if scope['date_to']:
        dmg_date_q &= Q(created_at__date__lte=scope['date_to'])

    rows = []
    if not scope['region_code']:
        level = 'region'
        m_stats = {
            r['district__region_id']: r
            for r in Mahalla.objects.values('district__region_id').annotate(
                total_objects=Coalesce(Sum('households'), 0)
                + Coalesce(Sum('social_objects'), 0)
                + Coalesce(Sum('historical_sites'), 0)
                + Coalesce(Sum('adm_buildings'), 0),
                red_mahallas=Count('id', filter=Q(status=MahallaStatus.red)),
                yellow_mahallas=Count('id', filter=Q(status=MahallaStatus.yellow)),
                green_mahallas=Count('id', filter=Q(status=MahallaStatus.green)),
            )
        }
        d_stats = {
            r['district__region_id']: r
            for r in DamagedObject.objects.filter(dmg_date_q).values('district__region_id').annotate(
                damaged_count=Count('id', filter=Q(status__in=CONFIRMED_STATUSES)),
                cleaned_count=Count('id', filter=Q(status__in=CLEANED_STATUSES)),
            )
        }
        oa_stats = {
            r['district__region_id']: r['ha']
            for r in OpenAreaInfo.objects.filter(dmg_date_q & Q(status__in=CONFIRMED_STATUSES))
            .values('district__region_id')
            .annotate(ha=Coalesce(Sum('hectares'), Decimal('0.00')))
        }

        for item in Region.objects.all():
            ms = m_stats.get(item.id, {})
            ds_row = d_stats.get(item.id, {})
            damaged_cnt = ds_row.get('damaged_count', 0)
            cleaned_cnt = ds_row.get('cleaned_count', 0)
            pop = item.population or 0
            per_10k = round((damaged_cnt / pop) * 10000, 2) if pop > 0 else 0.0
            cleaned_pct = round((cleaned_cnt / damaged_cnt) * 100, 1) if damaged_cnt > 0 else 0.0
            rows.append({
                'id': item.id,
                'code': item.code,
                'name': item.name,
                'population': pop,
                'total_objects': int(ms.get('total_objects') or 0),
                'damaged_count': damaged_cnt,
                'cleaned_count': cleaned_cnt,
                'cleaned_pct': cleaned_pct,
                'open_area_damaged_ha': round(float(oa_stats.get(item.id) or 0.0), 2),
                'per_10k_pop': per_10k,
                'red_mahallas': ms.get('red_mahallas', 0),
                'yellow_mahallas': ms.get('yellow_mahallas', 0),
                'green_mahallas': ms.get('green_mahallas', 0),
            })

    elif not scope['district_code']:
        level = 'district'
        m_stats = {
            r['district_id']: r
            for r in Mahalla.objects.filter(district__parent_code=scope['region_code'])
            .values('district_id')
            .annotate(
                total_objects=Coalesce(Sum('households'), 0)
                + Coalesce(Sum('social_objects'), 0)
                + Coalesce(Sum('historical_sites'), 0)
                + Coalesce(Sum('adm_buildings'), 0),
                red_mahallas=Count('id', filter=Q(status=MahallaStatus.red)),
                yellow_mahallas=Count('id', filter=Q(status=MahallaStatus.yellow)),
                green_mahallas=Count('id', filter=Q(status=MahallaStatus.green)),
            )
        }
        d_stats = {
            r['district_id']: r
            for r in DamagedObject.objects.filter(dmg_date_q & Q(district__parent_code=scope['region_code']))
            .values('district_id')
            .annotate(
                damaged_count=Count('id', filter=Q(status__in=CONFIRMED_STATUSES)),
                cleaned_count=Count('id', filter=Q(status__in=CLEANED_STATUSES)),
            )
        }
        oa_stats = {
            r['district_id']: r['ha']
            for r in OpenAreaInfo.objects.filter(
                dmg_date_q & Q(district__parent_code=scope['region_code']) & Q(status__in=CONFIRMED_STATUSES)
            )
            .values('district_id')
            .annotate(ha=Coalesce(Sum('hectares'), Decimal('0.00')))
        }

        for item in District.objects.filter(parent_code=scope['region_code']):
            ms = m_stats.get(item.id, {})
            ds_row = d_stats.get(item.id, {})
            damaged_cnt = ds_row.get('damaged_count', 0)
            cleaned_cnt = ds_row.get('cleaned_count', 0)
            pop = item.population or 0
            per_10k = round((damaged_cnt / pop) * 10000, 2) if pop > 0 else 0.0
            cleaned_pct = round((cleaned_cnt / damaged_cnt) * 100, 1) if damaged_cnt > 0 else 0.0
            rows.append({
                'id': item.id,
                'code': item.code,
                'name': item.name,
                'population': pop,
                'total_objects': int(ms.get('total_objects') or 0),
                'damaged_count': damaged_cnt,
                'cleaned_count': cleaned_cnt,
                'cleaned_pct': cleaned_pct,
                'open_area_damaged_ha': round(float(oa_stats.get(item.id) or 0.0), 2),
                'per_10k_pop': per_10k,
                'red_mahallas': ms.get('red_mahallas', 0),
                'yellow_mahallas': ms.get('yellow_mahallas', 0),
                'green_mahallas': ms.get('green_mahallas', 0),
            })

    else:
        level = 'mahalla'
        m_date_q = Q()
        if scope['date_from']:
            m_date_q &= Q(damaged_objects__created_at__date__gte=scope['date_from'])
        if scope['date_to']:
            m_date_q &= Q(damaged_objects__created_at__date__lte=scope['date_to'])

        qs = Mahalla.objects.filter(district__code=scope['district_code']).annotate(
            damaged_count=Count(
                'damaged_objects',
                filter=Q(damaged_objects__status__in=CONFIRMED_STATUSES) & m_date_q,
                distinct=True,
            ),
            cleaned_count=Count(
                'damaged_objects',
                filter=Q(damaged_objects__status__in=CLEANED_STATUSES) & m_date_q,
                distinct=True,
            ),
        )
        for item in qs:
            cleaned_pct = round((item.cleaned_count / item.damaged_count) * 100, 1) if item.damaged_count > 0 else 0.0
            rows.append({
                'id': item.id,
                'code': item.code,
                'name': item.name,
                'population': 0,
                'total_objects': item.objects_count,
                'damaged_count': item.damaged_count,
                'cleaned_count': item.cleaned_count,
                'cleaned_pct': cleaned_pct,
                'open_area_damaged_ha': 0.0,
                'per_10k_pop': float(item.damaged_percent),
                'red_mahallas': 1 if item.status == MahallaStatus.red else 0,
                'yellow_mahallas': 1 if item.status == MahallaStatus.yellow else 0,
                'green_mahallas': 1 if item.status == MahallaStatus.green else 0,
            })

    avg_per_10k = (sum(r['per_10k_pop'] for r in rows) / len(rows)) if rows else 0.0
    for r in rows:
        r['risk_level'] = _risk_level(r['red_mahallas'], r['per_10k_pop'], avg_per_10k)
        r['multiplier'] = round(r['per_10k_pop'] / avg_per_10k, 1) if avg_per_10k > 0 else 1.0

    rows.sort(key=lambda r: (r['damaged_count'], r['per_10k_pop']), reverse=True)

    # TOP-10 risky mahallas in scope
    top_m_qs = _filter_mahallas(
        Mahalla.objects.select_related('district', 'district__region').all(),
        scope,
    ).annotate(
        damaged_count=Count(
            'damaged_objects',
            filter=Q(damaged_objects__status__in=CONFIRMED_STATUSES),
            distinct=True,
        )
    ).filter(damaged_count__gt=0).order_by('-status', '-damaged_percent', '-damaged_count')[:10]

    top_mahallas = [
        {
            'id': m.id,
            'code': m.code,
            'name': m.name,
            'district_name': m.district.name,
            'district_code': m.district.code,
            'region_name': m.district.region.name,
            'region_code': m.district.region.code,
            'objects_count': m.objects_count,
            'damaged_count': m.damaged_count,
            'damaged_percent': float(m.damaged_percent),
            'status': m.status,
        }
        for m in top_m_qs
    ]

    return {
        'level': level,
        'avg_per_10k': round(avg_per_10k, 2),
        'items': rows,
        'top_mahallas': top_mahallas,
    }


def get_plan_execution_stats(scope: dict) -> dict:
    today = timezone.now().date()
    item_filter = Q()
    if scope['mahalla_id']:
        item_filter = Q(items__item__mahallainfo__mahalla_id=scope['mahalla_id'])
    elif scope['district_code']:
        item_filter = Q(items__item__district__code=scope['district_code'])
    elif scope['region_code']:
        item_filter = Q(items__item__district__parent_code=scope['region_code'])

    plans_qs = Plan.objects.exclude(status=PlanStatus.draft)
    if scope['mahalla_id']:
        plans_qs = plans_qs.filter(items__item__mahallainfo__mahalla_id=scope['mahalla_id']).distinct()
    elif scope['district_code']:
        plans_qs = plans_qs.filter(items__item__district__code=scope['district_code']).distinct()
    elif scope['region_code']:
        plans_qs = plans_qs.filter(
            Q(region_statuses__region__code=scope['region_code']) | Q(items__item__district__parent_code=scope['region_code'])
        ).distinct()

    if scope['date_from']:
        plans_qs = plans_qs.filter(to_date__gte=scope['date_from'])
    if scope['date_to']:
        plans_qs = plans_qs.filter(from_date__lte=scope['date_to'])

    plans_qs = plans_qs.annotate(
        total_items=Count('items', filter=item_filter, distinct=True),
        performed_items=Count('items', filter=item_filter & Q(items__is_performed=True), distinct=True),
    ).order_by('-from_date')

    plans_list = []
    for p in plans_qs:
        comp_pct = round((p.performed_items / p.total_items) * 100, 1) if p.total_items > 0 else (100.0 if p.status == PlanStatus.completed else 0.0)
        is_overdue = p.status in (PlanStatus.approved, PlanStatus.in_process) and p.to_date < today
        days_left = (p.to_date - today).days
        plans_list.append({
            'id': p.id,
            'name': p.name,
            'from_date': p.from_date.isoformat(),
            'to_date': p.to_date.isoformat(),
            'status': p.status,
            'total_items': p.total_items,
            'performed_items': p.performed_items,
            'completion_pct': comp_pct,
            'is_overdue': is_overdue,
            'days_left': days_left,
        })

    # Regional breakdown of plan execution
    reg_qs = Region.objects.all()
    if scope['region_code']:
        reg_qs = reg_qs.filter(code=scope['region_code'])

    pi_date_q = Q()
    if scope['date_from']:
        pi_date_q &= Q(district__damaged_objects__plan_items__plan__to_date__gte=scope['date_from'])
    if scope['date_to']:
        pi_date_q &= Q(district__damaged_objects__plan_items__plan__from_date__lte=scope['date_to'])

    reg_rows = reg_qs.annotate(
        total_items=Count(
            'district__damaged_objects__plan_items',
            filter=~Q(district__damaged_objects__plan_items__plan__status=PlanStatus.draft) & pi_date_q,
            distinct=True,
        ),
        performed_items=Count(
            'district__damaged_objects__plan_items',
            filter=Q(district__damaged_objects__plan_items__is_performed=True)
            & ~Q(district__damaged_objects__plan_items__plan__status=PlanStatus.draft)
            & pi_date_q,
            distinct=True,
        ),
    ).order_by('-total_items')

    by_region = [
        {
            'region_code': r.code,
            'region_name': r.name,
            'total_items': r.total_items,
            'performed_items': r.performed_items,
            'completion_pct': round((r.performed_items / r.total_items) * 100, 1) if r.total_items > 0 else 0.0,
        }
        for r in reg_rows
        if r.total_items > 0
    ]

    return {
        'plans': plans_list,
        'by_region': by_region,
    }


def get_operational_feed(scope: dict) -> dict:
    today = timezone.now().date()
    dmg_qs = _filter_damaged_objects(DamagedObject.objects.all(), scope, apply_dates=False)
    appeal_qs = _filter_appeals(Appeal.objects.all(), scope, apply_dates=False)
    mahalla_qs = _filter_mahallas(Mahalla.objects.all(), scope)

    overdue_plans = Plan.objects.filter(
        status__in=[PlanStatus.approved, PlanStatus.in_process],
        to_date__lt=today,
    )
    if scope['region_code']:
        overdue_plans = overdue_plans.filter(
            Q(region_statuses__region__code=scope['region_code']) | Q(items__item__district__parent_code=scope['region_code'])
        ).distinct()
    overdue_cnt = overdue_plans.count()

    pending_new_cnt = dmg_qs.filter(status=DamagedStatus.new).count()
    pending_appeals_cnt = appeal_qs.filter(status__in=[AppealStatus.new, AppealStatus.sent]).count()
    red_mahallas_cnt = mahalla_qs.filter(status=MahallaStatus.red).count()

    alerts = []
    if overdue_cnt > 0:
        alerts.append({
            'id': 'overdue_plans',
            'severity': 'critical',
            'code': 'overdue_plans',
            'count': overdue_cnt,
            'target_route': '/plans',
        })
    if red_mahallas_cnt > 0:
        alerts.append({
            'id': 'red_mahallas',
            'severity': 'critical',
            'code': 'red_mahallas',
            'count': red_mahallas_cnt,
            'target_route': '/mahalla',
        })
    if pending_new_cnt > 0:
        alerts.append({
            'id': 'pending_new_objects',
            'severity': 'warning',
            'code': 'pending_new_objects',
            'count': pending_new_cnt,
            'target_route': '/damaged-objects',
        })
    if pending_appeals_cnt > 0:
        alerts.append({
            'id': 'pending_appeals',
            'severity': 'warning',
            'code': 'pending_appeals',
            'count': pending_appeals_cnt,
            'target_route': '/appeals',
        })

    # Recent activity stream (latest 15 events combining DamagedObject + DamagedObjectFlow + Appeal)
    events = []
    recent_objs = (
        dmg_qs.select_related('district', 'district__region', 'mahallainfo__mahalla')
        .order_by('-created_at')[:10]
    )
    for obj in recent_objs:
        m_name = None
        if hasattr(obj, 'mahallainfo') and obj.mahallainfo.mahalla_id:
            m_name = obj.mahallainfo.mahalla.name
        events.append({
            'id': f'obj-{obj.id}',
            'event_type': 'object_created',
            'object_type': 'mahalla' if obj.type == DamagedTypes.mahalla else 'open_area',
            'status': obj.status,
            'district_name': obj.district.name,
            'district_code': obj.district.code,
            'region_code': obj.district.region.code,
            'mahalla_name': m_name,
            'object_id': obj.id,
            'timestamp': obj.created_at.isoformat(),
        })

    recent_flows = (
        _filter_flows(DamagedObjectFlow.objects.all(), scope, apply_dates=False)
        .select_related(
            'damaged_object',
            'damaged_object__district',
            'damaged_object__district__region',
            'damaged_object__mahallainfo__mahalla',
        )
        .order_by('-created_at')[:8]
    )
    for fl in recent_flows:
        obj = fl.damaged_object
        m_name = None
        if hasattr(obj, 'mahallainfo') and obj.mahallainfo.mahalla_id:
            m_name = obj.mahallainfo.mahalla.name
        events.append({
            'id': f'flow-{fl.id}',
            'event_type': 'status_changed',
            'object_type': 'mahalla' if obj.type == DamagedTypes.mahalla else 'open_area',
            'status': fl.status,
            'district_name': obj.district.name,
            'district_code': obj.district.code,
            'region_code': obj.district.region.code,
            'mahalla_name': m_name,
            'object_id': obj.id,
            'timestamp': fl.created_at.isoformat(),
        })

    recent_appeals = appeal_qs.select_related('district', 'district__region').order_by('-created_at')[:5]
    for apl in recent_appeals:
        events.append({
            'id': f'apl-{apl.id}',
            'event_type': 'appeal_submitted',
            'object_type': 'mahalla' if apl.damaged_type == DamagedTypes.mahalla else 'open_area',
            'status': apl.status,
            'district_name': apl.district.name,
            'district_code': apl.district.code,
            'region_code': apl.district.region.code,
            'mahalla_name': None,
            'object_id': apl.id,
            'timestamp': apl.created_at.isoformat(),
        })

    events.sort(key=lambda e: e['timestamp'], reverse=True)
    events = events[:15]

    rep_meta = _read_republic_meta()
    last_dmg_dt = DamagedObject.objects.order_by('-updated_at').values_list('updated_at', flat=True).first()

    data_sources = [
        {
            'key': 'postgis_cadastre',
            'status': 'online',
            'last_updated': (last_dmg_dt.date() if last_dmg_dt else today).isoformat(),
        },
        {
            'key': 'siat_demographics',
            'status': 'online' if rep_meta.get('population') else 'warning',
            'last_updated': rep_meta.get('last_synced') or today.isoformat(),
        },
        {
            'key': 'iip_cadastre',
            'status': 'online',
            'last_updated': today.isoformat(),
        },
        {
            'key': 'oneid_auth',
            'status': 'online',
            'last_updated': today.isoformat(),
        },
    ]

    total_oa_ha = float(OpenArea.objects.aggregate(s=Coalesce(Sum('hectare'), Decimal('0.00')))['s'] or 0.0)
    system_passport = {
        'regions_count': Region.objects.count(),
        'districts_count': District.objects.count(),
        'mahallas_count': Mahalla.objects.count(),
        'open_areas_ha': round(total_oa_ha, 1),
    }

    return {
        'alerts': alerts,
        'recent_activity': events,
        'data_sources': data_sources,
        'system_passport': system_passport,
    }


def get_map_points(scope: dict) -> list:
    qs = _filter_damaged_objects(
        DamagedObject.objects.filter(location__isnull=False)
        .select_related('district', 'mahallainfo', 'mahallainfo__mahalla', 'openareainfo', 'openareainfo__area_type'),
        scope,
        apply_dates=True,
    ).order_by('-created_at')[:500]

    points = []
    for obj in qs:
        if not obj.location:
            continue
        address = ''
        object_type = None
        mahalla_id = None
        mahalla_name = None
        hectares = None
        if hasattr(obj, 'mahallainfo'):
            address = obj.mahallainfo.address
            object_type = obj.mahallainfo.object_type
            mahalla_id = obj.mahallainfo.mahalla_id
            mahalla_name = obj.mahallainfo.mahalla.name if obj.mahallainfo.mahalla_id else None
        elif hasattr(obj, 'openareainfo'):
            address = obj.openareainfo.address
            hectares = float(obj.openareainfo.hectares)

        points.append({
            'id': obj.id,
            'lat': obj.location.y,
            'lng': obj.location.x,
            'type': obj.type,
            'object_type': object_type,
            'status': obj.status,
            'property_type': obj.property_type,
            'address': address,
            'district_code': obj.district.code,
            'district_name': obj.district.name,
            'mahalla_id': mahalla_id,
            'mahalla_name': mahalla_name,
            'hectares': hectares,
            'date': obj.date.isoformat() if obj.date else obj.created_at.date().isoformat(),
        })
    return points


def get_map_inspector(scope: dict, target_type: str, target_id: int) -> dict:
    if target_type == 'object' and target_id:
        obj = (
            DamagedObject.objects.select_related(
                'district', 'district__region', 'mahallainfo__mahalla', 'openareainfo__area_type'
            )
            .filter(id=target_id)
            .first()
        )
        if not obj:
            return {'target_type': 'object', 'found': False}
        if scope['region_code'] and obj.district.parent_code != scope['region_code']:
            return {'target_type': 'object', 'found': False}

        flows = [
            {
                'status': f.status,
                'created_at': f.created_at.isoformat(),
                'plan_name': f.plan_item.plan.name if f.plan_item_id and f.plan_item.plan_id else None,
            }
            for f in obj.flows.select_related('plan_item__plan').order_by('created_at')
        ]
        info = {
            'target_type': 'object',
            'found': True,
            'id': obj.id,
            'type': obj.type,
            'status': obj.status,
            'property_type': PROPERTY_TYPE_KEYS.get(obj.property_type) if obj.property_type else None,
            'district_name': obj.district.name,
            'region_name': obj.district.region.name,
            'date': obj.date.isoformat() if obj.date else obj.created_at.date().isoformat(),
            'lat': obj.location.y if obj.location else None,
            'lng': obj.location.x if obj.location else None,
            'flows': flows,
        }
        if hasattr(obj, 'mahallainfo'):
            mi = obj.mahallainfo
            info.update({
                'name': mi.mahalla.name if mi.mahalla_id else obj.district.name,
                'mahalla_id': mi.mahalla_id,
                'object_type': OBJECT_TYPE_KEYS.get(mi.object_type),
                'cadastral_number': mi.cadastral_number,
                'owner_name': mi.owner_name,
                'owner_phone': mi.owner_phone,
                'address': mi.address,
            })
        elif hasattr(obj, 'openareainfo'):
            oi = obj.openareainfo
            info.update({
                'name': oi.area_type.name if oi.area_type_id else obj.district.name,
                'hectares': float(oi.hectares),
                'owner_name': oi.owner_name,
                'owner_phone': oi.owner_phone,
                'address': oi.address,
            })
        return info

    if target_type == 'mahalla' and target_id:
        m = Mahalla.objects.select_related('district', 'district__region').filter(
            Q(id=target_id) | Q(code=target_id)
        ).first()
        if not m:
            return {'target_type': 'mahalla', 'found': False}
        if scope['region_code'] and m.district.parent_code != scope['region_code']:
            return {'target_type': 'mahalla', 'found': False}

        dmg_agg = m.damaged_objects.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(status__in=ACTIVE_STATUSES)),
            cleaned=Count('id', filter=Q(status__in=CLEANED_STATUSES)),
            new_count=Count('id', filter=Q(status=DamagedStatus.new)),
        )
        recent = [
            {
                'id': item.id,
                'object_type': OBJECT_TYPE_KEYS.get(item.object_type),
                'status': item.status,
                'cadastral_number': item.cadastral_number,
                'address': item.address,
                'date': item.date.isoformat() if item.date else item.created_at.date().isoformat(),
            }
            for item in m.damaged_objects.order_by('-created_at')[:5]
        ]
        return {
            'target_type': 'mahalla',
            'found': True,
            'id': m.id,
            'code': m.code,
            'name': m.name,
            'district_name': m.district.name,
            'region_name': m.district.region.name,
            'status': m.status,
            'damaged_percent': float(m.damaged_percent),
            'objects_count': m.objects_count,
            'building_counts': {
                'households': m.households,
                'social_objects': m.social_objects,
                'historical_sites': m.historical_sites,
                'adm_buildings': m.adm_buildings,
            },
            'damaged_summary': dmg_agg,
            'address': m.address,
            'phone_number': m.phone_number,
            'recent_objects': recent,
        }

    # District / Region / Republic inspector
    inspect_scope = dict(scope)
    if target_type == 'district' and target_id:
        d_obj = District.objects.select_related('region').filter(Q(code=target_id) | Q(id=target_id)).first()
        if d_obj and (not scope['region_code'] or d_obj.parent_code == scope['region_code']):
            inspect_scope['district_code'] = d_obj.code
            inspect_scope['district_obj'] = d_obj
            inspect_scope['region_code'] = d_obj.region.code
            inspect_scope['region_obj'] = d_obj.region
            inspect_scope['mahalla_id'] = None
            inspect_scope['scope_level'] = 'district'
            inspect_scope['scope_name'] = d_obj.name
    elif target_type == 'region' and target_id and not scope['region_code']:
        r_obj = Region.objects.filter(Q(code=target_id) | Q(id=target_id)).first()
        if r_obj:
            inspect_scope['region_code'] = r_obj.code
            inspect_scope['region_obj'] = r_obj
            inspect_scope['district_code'] = None
            inspect_scope['district_obj'] = None
            inspect_scope['mahalla_id'] = None
            inspect_scope['scope_level'] = 'region'
            inspect_scope['scope_name'] = r_obj.name

    overview = get_dashboard_overview(inspect_scope)
    return {
        'target_type': inspect_scope['scope_level'],
        'found': True,
        'name': inspect_scope['scope_name'],
        'population': overview['normalized']['population'],
        'per_10k_population': overview['normalized']['per_10k_population'],
        'damaged_total': overview['kpis']['damaged_total']['total'],
        'active_damaged': overview['kpis']['damaged_total']['active'],
        'cleaned_count': overview['kpis']['cleaned_objects']['cleaned_count'],
        'completion_rate_pct': overview['kpis']['cleaned_objects']['completion_rate_pct'],
        'mahalla_risk': overview['kpis']['mahalla_risk'],
        'building_categories': overview['building_categories'],
    }
