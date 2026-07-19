from django.db.models import Sum, Count, Exists, OuterRef

from area.models import Region, District, Mahalla, OpenArea, MahallaStatus
from damaged_object.models import OpenAreaInfo, DamagedStatus, DamagedObject, MahallaInfo

object_types_data = {
    1: "households",
    2: "social_objects",
    3: "historical_sites",
    4: "adm_buildings",
}


def number_statistics(mahalla_code=None, district_code=None, region_code=None):
    filtered_counts = Mahalla.objects.all()

    if mahalla_code:
        filtered_counts = filtered_counts.filter(code=mahalla_code)
        exists = Mahalla.objects.filter(id=mahalla_code).exclude(status=MahallaStatus.green).exists()
        count = 1 if exists else 0

        data = {
            'region': (count, 1),
            'district': (count, 1),
            'mahalla': (count, 1),
            'open_area': (0, 0)
        }
    elif district_code:
        filtered_counts = filtered_counts.filter(parent_code=district_code)
        mahalla_count = Mahalla.objects.filter(parent_code=district_code).count()
        open_area_obj = OpenArea.objects.get(district__code=district_code)

        queryset = Mahalla.objects.filter(parent_code=district_code).exclude(status=MahallaStatus.green)
        count = 1 if queryset.exists() else 0
        m_count = queryset.count()
        d_open_area = OpenAreaInfo.objects.filter(district__code=district_code).filter(
            status__in=[DamagedStatus.approved, DamagedStatus.in_process, DamagedStatus.completed]
        ).aggregate(total=Sum('hectares'))['total'] or 0

        data = {
            'region': (count, 1),
            'district': (count, 1),
            'mahalla': (m_count, mahalla_count),
            'open_area': (d_open_area, open_area_obj.hectare)
        }
    elif region_code:
        filtered_counts = filtered_counts.filter(district__parent_code=region_code)
        district_count = District.objects.filter(parent_code=region_code).count()
        mahalla_count = Mahalla.objects.filter(district__parent_code=region_code).count()
        sum_hectare = OpenArea.objects.filter(district__parent_code=region_code).aggregate(
            sum_hectare=Sum('hectare')
        )['sum_hectare'] or 0

        queryset = Mahalla.objects.filter(district__parent_code=region_code).exclude(status=MahallaStatus.green)
        r_count = 1 if queryset.exists() else 0
        d_count = queryset.values('district').distinct().count()
        m_count = queryset.count()
        d_open_area = OpenAreaInfo.objects.filter(district__parent_code=region_code).filter(
            status__in=[DamagedStatus.approved, DamagedStatus.in_process, DamagedStatus.completed]
        ).aggregate(total=Sum('hectares'))['total'] or 0

        data = {
            'region': (r_count, 1),
            'district': (d_count, district_count),
            'mahalla': (m_count, mahalla_count),
            'open_area': (d_open_area, sum_hectare)
        }
    else:
        total_region = Region.objects.count()
        total_district = District.objects.count()
        total_mahalla = Mahalla.objects.count()
        total_open_area = OpenArea.objects.aggregate(total=Sum('hectare'))['total'] or 0

        r_count = Mahalla.objects.exclude(status=MahallaStatus.green).values('district__region').distinct().count()
        d_count = Mahalla.objects.exclude(status=MahallaStatus.green).values('district').distinct().count()
        m_count = Mahalla.objects.exclude(status=MahallaStatus.green).count()
        d_open_area = OpenAreaInfo.objects.filter(
            status__in=[DamagedStatus.approved, DamagedStatus.in_process, DamagedStatus.completed]
        ).aggregate(total=Sum('hectares'))['total'] or 0
        data = {
            'region': (r_count, total_region),
            'district': (d_count, total_district),
            'mahalla': (m_count, total_mahalla),
            'open_area': (d_open_area, total_open_area)
        }
    building_counts = filtered_counts.aggregate(
        households=Sum('households'),
        social_objects=Sum('social_objects'),
        historical_sites=Sum('historical_sites'),
        adm_buildings=Sum('adm_buildings')
    )
    # adding building counts
    households_damaged_count = (
        MahallaInfo.objects
        .filter(mahalla__in=filtered_counts)
        .values('object_type')
        .annotate(count=Count('id'))
    )

    households_damaged_count_data = {
        object_types_data[row['object_type']]: row['count']
        for row in households_damaged_count
    }
    building_counts_data = {
        "households": (
            households_damaged_count_data.get('households', 0),
            building_counts['households']
        ),
        "social_objects": (
            households_damaged_count_data.get('social_objects', 0),
            building_counts['social_objects']
        ),
        "historical_sites": (
            households_damaged_count_data.get('historical_sites', 0),
            building_counts['historical_sites']
        ),
        "adm_buildings": (
            households_damaged_count_data.get('adm_buildings', 0),
            building_counts['adm_buildings']
        )
    }
    data['building_counts'] = building_counts_data

    return data


def area_statistics(district_code=None, region_code=None):
    data = {}
    if district_code:
        district = District.objects.get(code=district_code)
        data['population'] = district.population
        data['population_density'] = district.population_density
        data['area'] = district.area * 100

        counts = district.mahalla_set.aggregate(
            households=Sum('households'),
            social_objects=Sum('social_objects'),
            historical_sites=Sum('historical_sites'),
            adm_buildings=Sum('adm_buildings')
        )
        open_area = OpenArea.objects.get(district__code=district_code).hectare
    elif region_code:
        region = Region.objects.get(code=region_code)
        data['population'] = region.population
        data['population_density'] = region.population_density
        data['area'] = region.area * 100
        counts = Mahalla.objects.filter(district__parent_code=region_code).aggregate(
            households=Sum('households'),
            social_objects=Sum('social_objects'),
            historical_sites=Sum('historical_sites'),
            adm_buildings=Sum('adm_buildings')
        )
        open_area = OpenArea.objects.filter(
            district__parent_code=region_code).aggregate(hectare=Sum('hectare')).get('hectare')

    else:
        import json
        from pathlib import Path
        BASE_DIR = Path(__file__).resolve().parent.parent
        file_path = "area/data/republic_stat.json"
        file_path = f"{BASE_DIR}/{file_path}"
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except:
            data = {}

        counts = Mahalla.objects.aggregate(
            households=Sum('households'),
            social_objects=Sum('social_objects'),
            historical_sites=Sum('historical_sites'),
            adm_buildings=Sum('adm_buildings')
        )
        open_area = OpenArea.objects.aggregate(hectare=Sum('hectare')).get('hectare')

    data['open_area'] = open_area
    data['building_counts'] = counts
    return data


def convert_to_km2(total, dm_area):
    return round(total/100, 2), round(dm_area/100, 2)


def area_damaged_status(region_code=None):
    print(region_code)
    if region_code:
        queryset = District.objects.filter(parent_code=region_code).annotate(
            is_damaged=Exists(
                DamagedObject.objects.filter(
                    district=OuterRef('pk'),
                    status__in=[
                        DamagedStatus.approved,
                        DamagedStatus.in_process,
                        DamagedStatus.completed,
                    ]
                )
            )
        )
    else:
        queryset = Region.objects.annotate(
            is_damaged=Exists(
                DamagedObject.objects.filter(
                    district__region=OuterRef('pk'),
                    status__in=[
                        DamagedStatus.approved,
                        DamagedStatus.in_process,
                        DamagedStatus.completed,
                    ]
                )
            )
        )
    return queryset.values('code', 'id', 'is_damaged')
