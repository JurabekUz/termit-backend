import json
import logging
import os
from datetime import date
from pathlib import Path

import requests

from area.models import Region, District

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent.parent

SIAT_ENDPOINTS = {
    'population': 'https://api.siat.stat.uz/media/uploads/sdmx/sdmx_data_246.json',
    'density': 'https://api.siat.stat.uz/media/uploads/sdmx/sdmx_data_236.json',
    'area': 'https://api.siat.stat.uz/media/uploads/sdmx/sdmx_data_2834.json',
}

# Official SOATO fallback figures (population in thousands, density per km2, area in thousand km2)
# Used only when api.siat.stat.uz is unreachable from the container.
FALLBACK_REGION_STATS = {
    '1700': {'population': 37543.2, 'density': 83.6, 'area': 448.98},
    '1703': {'population': 3458.5, 'density': 804.3, 'area': 4.30},
    '1706': {'population': 2076.8, 'density': 51.5, 'area': 40.32},
    '1708': {'population': 1537.4, 'density': 72.5, 'area': 21.21},
    '1710': {'population': 3635.2, 'density': 127.2, 'area': 28.57},
    '1712': {'population': 1094.6, 'density': 9.9, 'area': 110.99},
    '1714': {'population': 3130.8, 'density': 420.8, 'area': 7.44},
    '1718': {'population': 4293.0, 'density': 256.0, 'area': 16.77},
    '1722': {'population': 2946.0, 'density': 146.6, 'area': 20.10},
    '1724': {'population': 930.8, 'density': 217.5, 'area': 4.28},
    '1726': {'population': 3112.8, 'density': 7155.9, 'area': 0.44},
    '1727': {'population': 3106.5, 'density': 203.6, 'area': 15.26},
    '1730': {'population': 4148.2, 'density': 613.6, 'area': 6.76},
    '1733': {'population': 2031.7, 'density': 335.8, 'area': 6.05},
    '1735': {'population': 2040.9, 'density': 12.2, 'area': 166.59},
}


def identify_last_year(data: dict) -> str:
    year_keys = [key for key in data.keys() if str(key).isdigit() and len(str(key)) == 4]
    if not year_keys:
        return ''
    return max(year_keys, key=int)


def get_stat_data(url: str, timeout: int = 15) -> dict:
    """Fetch SIAT SDMX dataset and return {SOATO_code: latest_numeric_value}."""
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        stat_data = response.json()
        if not isinstance(stat_data, list) or not stat_data or 'data' not in stat_data[0]:
            return {}
        rows = stat_data[0]['data']
        if not rows:
            return {}
        result = {}
        for item in rows:
            code = str(item.get('Code', '')).strip()
            if not code:
                continue
            last_year = identify_last_year(item)
            if not last_year:
                continue
            raw_val = item.get(last_year)
            if raw_val is not None:
                try:
                    result[code] = float(raw_val)
                except (TypeError, ValueError):
                    continue
        return result
    except Exception as exc:
        logger.warning("SIAT API request failed (%s): %s", url, exc)
        return {}


def _apply_district_fallbacks():
    """Ensure every District has non-zero population, area, and density derived from its Region when missing."""
    districts_to_update = []
    regions = Region.objects.prefetch_related('district_set').all()
    for region in regions:
        districts = list(region.district_set.all())
        if not districts:
            continue
        missing = [d for d in districts if d.population == 0 or d.area == 0]
        if not missing:
            continue
        existing_pop = sum(d.population for d in districts if d.population > 0)
        existing_area = sum(d.area for d in districts if d.area > 0)
        rem_pop = max(region.population - existing_pop, 0)
        rem_area = max(region.area - existing_area, 0)
        per_pop = max(int(rem_pop / len(missing)) if rem_pop else int(region.population / len(districts)), 1000)
        per_area = max(int(rem_area / len(missing)) if rem_area else int(region.area / len(districts)), 1)
        for d in missing:
            if d.population == 0:
                d.population = per_pop
            if d.area == 0:
                d.area = per_area
            if d.population_density == 0:
                d.population_density = round(d.population / max(d.area, 1), 1)
            districts_to_update.append(d)
    if districts_to_update:
        District.objects.bulk_update(districts_to_update, ['population', 'area', 'population_density'])
    return len(districts_to_update)


def update_republic_stat(key, value):
    file_path = f"{BASE_DIR}/area/data/republic_stat.json"
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    if not os.path.exists(file_path) or os.stat(file_path).st_size == 0:
        data = {'population': 0, 'population_density': 0, 'area': 0}
    else:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

    data[key] = value
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def update_population():
    data_dict = get_stat_data(SIAT_ENDPOINTS['population'])
    used_fallback = False
    if not data_dict:
        used_fallback = True
        data_dict = {k: v['population'] for k, v in FALLBACK_REGION_STATS.items()}

    regions_to_update = []
    districts_to_update = []

    for region in Region.objects.all():
        amount = data_dict.get(str(region.code))
        if amount:
            region.population = int(round(amount * 1000))
            regions_to_update.append(region)

    for district in District.objects.all():
        amount = data_dict.get(str(district.code))
        if amount:
            district.population = int(round(amount * 1000))
            districts_to_update.append(district)

    if regions_to_update:
        Region.objects.bulk_update(regions_to_update, ['population'])
    if districts_to_update:
        District.objects.bulk_update(districts_to_update, ['population'])

    republic_amount = data_dict.get('1700')
    if republic_amount:
        update_republic_stat('population', int(round(republic_amount * 1000)))
    return not used_fallback


def update_population_density():
    data_dict = get_stat_data(SIAT_ENDPOINTS['density'])
    used_fallback = False
    if not data_dict:
        used_fallback = True
        data_dict = {k: v['density'] for k, v in FALLBACK_REGION_STATS.items()}

    regions_to_update = []
    districts_to_update = []

    for region in Region.objects.all():
        amount = data_dict.get(str(region.code))
        if amount:
            region.population_density = round(float(amount), 1)
            regions_to_update.append(region)

    for district in District.objects.all():
        amount = data_dict.get(str(district.code))
        if amount:
            district.population_density = round(float(amount), 1)
            districts_to_update.append(district)

    if regions_to_update:
        Region.objects.bulk_update(regions_to_update, ['population_density'])
    if districts_to_update:
        District.objects.bulk_update(districts_to_update, ['population_density'])

    republic_amount = data_dict.get('1700')
    if republic_amount:
        update_republic_stat('population_density', round(float(republic_amount), 1))
    return not used_fallback


def update_area():
    data_dict = get_stat_data(SIAT_ENDPOINTS['area'])
    used_fallback = False
    if not data_dict:
        used_fallback = True
        data_dict = {k: v['area'] for k, v in FALLBACK_REGION_STATS.items()}

    regions_to_update = []
    districts_to_update = []

    for region in Region.objects.all():
        amount = data_dict.get(str(region.code))
        if amount:
            region.area = max(int(round(amount * 1000)), 1)
            regions_to_update.append(region)

    for district in District.objects.all():
        amount = data_dict.get(str(district.code))
        if amount:
            district.area = max(int(round(amount * 1000)), 1)
            districts_to_update.append(district)

    if regions_to_update:
        Region.objects.bulk_update(regions_to_update, ['area'])
    if districts_to_update:
        District.objects.bulk_update(districts_to_update, ['area'])

    republic_amount = data_dict.get('1700')
    if republic_amount:
        # Store republic area in hectares to match region.area * 100 / district.area * 100 in area_statistics()
        update_republic_stat('area', int(round(republic_amount * 1000 * 100)))
        update_republic_stat('area_km2', round(float(republic_amount) * 1000, 2))
    return not used_fallback


def sync_all_demographics() -> dict:
    pop_live = update_population()
    den_live = update_population_density()
    area_live = update_area()
    filled_districts = _apply_district_fallbacks()

    live = pop_live and den_live and area_live
    update_republic_stat('last_synced', date.today().isoformat())
    update_republic_stat('source', 'SIAT (api.siat.stat.uz)' if live else 'SIAT fallback')

    return {
        'live': live,
        'regions_with_population': Region.objects.filter(population__gt=0).count(),
        'districts_with_population': District.objects.filter(population__gt=0).count(),
        'fallback_filled_districts': filled_districts,
    }
