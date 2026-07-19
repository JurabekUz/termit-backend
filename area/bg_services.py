import requests
from pathlib import Path
from area.models import Region, District
BASE_DIR = Path(__file__).resolve().parent.parent


def get_stat_data(url):
    """API'dan ma'lumotlarni olish va kerakli formatda qaytarish"""
    response = requests.get(url)
    stat_data = response.json()
    last_year = identify_last_year(stat_data[0]['data'][0])
    return {item['Code']: item.get(last_year) for item in stat_data[0]['data']}


def update_population():
    data_dict = get_stat_data(
        url='https://api.siat.stat.uz/media/uploads/sdmx/sdmx_data_246.json'
    )
    regions_to_update = []
    districts_to_update = []

    for region in Region.objects.all():
        amount = data_dict.get(str(region.code))
        if amount:
            region.population = int(amount * 1000)
            regions_to_update.append(region)

    for district in District.objects.all():
        amount = data_dict.get(str(district.code))
        if amount:
            district.population = int(amount * 1000)
            districts_to_update.append(district)

    if regions_to_update:
        Region.objects.bulk_update(regions_to_update, ['population'])

    if districts_to_update:
        District.objects.bulk_update(districts_to_update, ['population'])

    republic_amount = data_dict.get("1700")
    if republic_amount:
        republic_amount = republic_amount*1000
        update_republic_stat('population', republic_amount)


def update_population_density():
    data_dict = get_stat_data(
        url='https://api.siat.stat.uz/media/uploads/sdmx/sdmx_data_236.json'
    )
    regions_to_update = []
    districts_to_update = []
    for region in Region.objects.all():
        amount = data_dict.get(str(region.code))
        if amount:
            region.population_density = amount
            regions_to_update.append(region)

    for district in District.objects.all():
        amount = data_dict.get(str(district.code))
        if amount:
            district.population_density = amount
            districts_to_update.append(district)

    if regions_to_update:
        Region.objects.bulk_update(regions_to_update, ['population_density'])

    if districts_to_update:
        District.objects.bulk_update(districts_to_update, ['population_density'])

    republic_amount = data_dict.get("1700")
    if republic_amount:
        republic_amount = republic_amount
        update_republic_stat('population_density', republic_amount)


def update_area():
    data_dict = get_stat_data(
        url='https://api.siat.stat.uz/media/uploads/sdmx/sdmx_data_2834.json'
    )
    regions_to_update = []
    districts_to_update = []

    for region in Region.objects.all():
        amount = data_dict.get(str(region.code))
        if amount:
            region.area = int(amount*1000)
            regions_to_update.append(region)

    for district in District.objects.all():
        amount = data_dict.get(str(district.code))
        if amount:
            district.area = int(amount*1000)
            districts_to_update.append(district)

    if regions_to_update:
        Region.objects.bulk_update(regions_to_update, ['area'])

    if districts_to_update:
        District.objects.bulk_update(districts_to_update, ['area'])

    republic_amount = data_dict.get("1700")
    if republic_amount:
        republic_amount = republic_amount
        update_republic_stat('area', republic_amount)


def update_republic_stat(key, value):
    import os
    import json

    file_path = f"{BASE_DIR}/area/data/republic_stat.json"

    if not os.path.exists(file_path) or os.stat(file_path).st_size == 0:
        # Fayl bo‘sh bo‘lsa, boshlang‘ich ma'lumot bilan to‘ldiramiz
        data = {
            'population': 0,
            'population_density': 0,
            'area': 0
        }  # Yoki kerakli boshlang‘ich struktura
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    else:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

    # Ma'lumotni yangilash
    data[key] = value

    # Yangilangan ma'lumotni saqlash
    with open(file_path, 'w', encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def identify_last_year(data):
    return max((key for key in data if key.isdigit()), key=int)
