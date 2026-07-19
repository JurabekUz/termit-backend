from django.db.models import Q, F, Sum, Count, ExpressionWrapper, FloatField, Case, When, Value
from django.utils.translation import gettext_lazy as _

from area.models import Region, District, Mahalla, MahallaStatus, OpenArea
from baseapp.integrations import get_cadastre_info
from config.utils import CommonException
from damaged_object.models import DamagedStatus as ds
from damaged_object.serializers import ObjectStatSerializer, OpenAreaStatSerializer


def mahalla_status_statistics(region_code):
    labels = []
    green = []
    yellow = []
    red = []
    queryset = Region.objects.annotate(
        total=Count('district__mahalla', distinct=True),
        green=Count('district__mahalla', filter=Q(district__mahalla__status=MahallaStatus.green)),
        yellow=Count('district__mahalla', filter=Q(district__mahalla__status=MahallaStatus.yellow)),
        red=Count('district__mahalla', filter=Q(district__mahalla__status=MahallaStatus.red))
    )

    if region_code:
        queryset = District.objects.filter(parent_code=region_code).annotate(
            total=Count('mahalla', distinct=True),
            green=Count('mahalla', filter=Q(mahalla__status=MahallaStatus.green)),
            yellow=Count('mahalla', filter=Q(mahalla__status=MahallaStatus.yellow)),
            red=Count('mahalla', filter=Q(mahalla__status=MahallaStatus.red))
        )

    for item in queryset:
        labels.append(item.name)
        total = item.total or 1

        green.append(round(item.green * 100 / total, 2))
        yellow.append(round(item.yellow * 100 / total, 2))
        red.append(round(item.red * 100 / total, 2))

    return {
        'labels': labels,
        'green': green,
        'yellow': yellow,
        'red': red
    }


def get_object_stats_queryset(group_by_field, name_field, filters=None):
    filters = filters or {}
    return (
        Mahalla.objects.filter(**filters)
        .values(group_by_field)
        .annotate(
            total_houses=Sum('households'),
            total_objects=Sum('social_objects'),
            total_sites=Sum('historical_sites'),
            total_buildings=Sum('adm_buildings'),
            total_damaged_object=Count('damaged_objects',
                                filter=Q(damaged_objects__status__in=[ds.approved, ds.in_process, ds.completed]),
                                distinct=True),
        )
        .annotate(
            total=F('total_houses') + F('total_objects') + F('total_sites') + F('total_buildings'),
        )
        .annotate(
            label=F(name_field),
            percentage=Case(
                When(total=0, then=Value(0.0)),
                default=ExpressionWrapper(
                    100.0 * F('total_damaged_object') / F('total'),
                    output_field=FloatField()
                ),
                output_field=FloatField()
            )
        )
        .order_by('-percentage')
    )


def object_statistics(region_code, district_code):
    if district_code:
        queryset = get_object_stats_queryset(
            group_by_field='name',
            name_field='name',
            filters={'parent_code': district_code}
        )
    elif region_code:
        queryset = get_object_stats_queryset(
            group_by_field='district__name',
            name_field='district__name',
            filters={'district__parent_code': region_code}
        )
    else:
        queryset = get_object_stats_queryset(
            group_by_field='district__region__name',
            name_field='district__region__name',
        )

    serializer = ObjectStatSerializer(queryset, many=True)
    return serializer.data


def get_object_stats_queryset_by_types(group_by_field, name_field, type_label, filters=None):
    filters = filters or {}
    object_type = {
        'households': 1,
        'social_objects': 2,
        'historical_sites': 3,
        'adm_buildings': 4,
    }
    return (
        Mahalla.objects.filter(**filters)
        .values(group_by_field)
        .annotate(
            total=Sum(type_label, distinct=True),
            total_damaged_object=Count('damaged_objects', distinct=True,
                                       filter=Q(damaged_objects__object_type=object_type[type_label],
                                                damaged_objects__status__in=[ds.approved, ds.in_process, ds.completed])
                                       ),
        ).annotate(
            label=F(name_field),
            percentage=Case(
                When(total=0, then=Value(0.0)),
                default=ExpressionWrapper(
                    100.0 * F('total_damaged_object') / F('total'),
                    output_field=FloatField()
                ),
                output_field=FloatField()
            )
        ).order_by('-percentage')
    )


def object_statistics_by_types(region_code, district_code, type_label):
    if district_code:
        queryset = get_object_stats_queryset_by_types(
            group_by_field='name',
            name_field='name',
            type_label=type_label,
            filters={'parent_code': district_code}
        )
    elif region_code:
        queryset = get_object_stats_queryset_by_types(
            group_by_field='district__name',
            name_field='district__name',
            type_label=type_label,
            filters={'district__parent_code': region_code}
        )
    else:
        queryset = get_object_stats_queryset_by_types(
            group_by_field='district__region__name',
            name_field='district__region__name',
            type_label=type_label
        )

    serializer = ObjectStatSerializer(queryset, many=True)
    return serializer.data


def open_area_statistics(region_code):
    if region_code:
        queryset = District.objects.filter(parent_code=region_code).annotate(
            total=Sum(
                'open_areas__hectare', default=0, distinct=True),
            total_damaged_object=Sum(
                'damaged_objects__openareainfo__hectares',
                filter=Q(
                    damaged_objects__openareainfo__status__in=
                    [ds.approved, ds.in_process, ds.completed
                     ]),
                default=0, distinct=True)
        ).annotate(
            percentage=Case(
            When(total=0, then=Value(0.0)),
                default=ExpressionWrapper(
                    100.0 * F('total_damaged_object') / F('total'),
                    output_field=FloatField()
                ),
                output_field=FloatField()
            )
        ).order_by('-percentage')
    else:
        queryset = Region.objects.annotate(
            total=Sum(
                'district__open_areas__hectare', default=0, distinct=True),
            total_damaged_object=Sum(
                'district__damaged_objects__openareainfo__hectares',
                filter=Q(
                    district__damaged_objects__openareainfo__status__in=
                    [ds.approved, ds.in_process, ds.completed
                     ]),
                default=0, distinct=True)
        ).annotate(
            percentage=Case(
            When(total=0, then=Value(0.0)),
                default=ExpressionWrapper(
                    100.0 * F('total_damaged_object') / F('total'),
                    output_field=FloatField()
                ),
                output_field=FloatField()
            )
        ).order_by('-percentage')

    serializer = OpenAreaStatSerializer(queryset, many=True)
    return serializer.data


def get_cadastral_object(number, user):
    data = {}
    object_info = get_cadastre_info(number)
    if object_info['code'] == 1:
        region_code = object_info['region_id']
        region_id = get_object_id_by_code(Region, region_code)
        if user.region_id is not None and region_id != user.region_id:
            raise CommonException(
                _("You do not have permission to enter this cadastral"
                  " digital object because it belongs to another region."))
        try:
            district_code = object_info['district_id']
            mahalla_1c_code = object_info['neighborhood_id']
            data['cadastral_number'] = object_info['cad_number']
            data['region_id'] = region_id
            data['district_id'] = get_object_id_by_code(District, district_code)
            data['mahalla_id'] = get_mahalla_id_by_c1_code(mahalla_1c_code)
            data['address'] = object_info['address']
            data['names'] = [subject['name'] for subject in object_info['subjects']]
            data['vid'] = object_info['vid']
            data['tip'] = object_info['tip']
        except Exception as e:
            raise CommonException(_("Sorry, an unexpected error occurred while processing the data."))
        return data
    else:
        raise CommonException(object_info.get('message', _("Sorry, there was an error retrieving data.")))


def get_mahalla_code_by_c1_code(c1_code):
    try:
        return Mahalla.objects.get(code_1c=c1_code).code
    except Mahalla.DoesNotExist:
        return None


def get_mahalla_id_by_c1_code(c1_code):
    try:
        return Mahalla.objects.only("id").get(code_1c=c1_code).id
    except Mahalla.DoesNotExist:
        return None


def get_object_id_by_code(model, code):
    try:
        return model.objects.only("id").get(code=code).id
    except model.DoesNotExist:
        return None
