from django.db import IntegrityError

from area.models import Region, District, Mahalla
from pathlib import Path
import json
from django.contrib.gis.geos import GEOSGeometry

BASE_DIR = Path(__file__).resolve().parent.parent


def load_region():
    count = 0
    existed_data = 0
    file_path = "Mintaqa_27_03_2024.geojson"
    file_path = f"{BASE_DIR}/{file_path}"
    try:

        with open(file_path, 'r', encoding='utf-8') as f:
            geojson_data = json.load(f)

            for feature in geojson_data['features']:
                properties = feature['properties']
                geometry = GEOSGeometry(json.dumps(feature['geometry']))

                obj = Region.objects.filter(name=properties['region_name']).first()
                coordinates = list(geometry[0][0])


                # Calculate the centroid

                # Get the centroid latitude and longitude
                count += 1

                if obj is not None:
                    existed_data += 1
                    continue

                if properties['objectid'] == 'null' or properties['objectid'] is None:
                    print(properties)
                    print("\n//////////\n")
                else:
                    center = geometry.centroid
                    Region.objects.create(
                        name=properties['region_name'],
                        coordinates=geometry,
                        code=properties['parent_code'],
                        center_lat=center.y,
                        center_lan=center.x
                    )
        print("Existed data", existed_data)
        return count
    except Exception as e:
        print("Error ", str(e))


def district_geojson():
    count = 0
    existed_data = 0
    file_path = "Tuman_16_05_2024.geojson"
    file_path = f"{BASE_DIR}/{file_path}"
    try:

        with open(file_path, 'r', encoding='utf-8') as f:
            geojson_data = json.load(f)

            for feature in geojson_data['features']:
                properties = feature['properties']
                geometry = GEOSGeometry(json.dumps(feature['geometry']))
                region = Region.objects.get(code=properties['parent_code'])
                obj = District.objects.filter(code=properties['code']).first()
                count += 1

                if obj is not None:
                    existed_data += 1
                    continue

                if properties['district'] == 'null' or properties['district'] is None:
                    print(properties)
                    print("\n//////////\n")
                else:
                    center = geometry.centroid
                    District.objects.create(
                        parent_code=properties['parent_code'],
                        name=properties['district'],
                        code=properties['code'],
                        coordinates=geometry,
                        region=region,
                        center_lat=center.y,
                        center_lan=center.x
                    )
        print("Existed data", existed_data)
        return count
    except Exception as e:
        print("Error ", str(e))


def load_mahalla():
    count = 0
    existed_data = 0
    # file_path = "Mahalla_21_05_2024.geojson"
    file_path = "mahalla.json"
    file_path = f"{BASE_DIR}/{file_path}"
    try:

        with open(file_path, 'r', encoding='utf-8') as f:
            geojson_data = json.load(f)

            for feature in geojson_data['features']:
                properties = feature['properties']
                geometry = GEOSGeometry(json.dumps(feature['geometry']))
                obj = Mahalla.objects.filter(code=properties['code']).first()
                count += 1
                district = District.objects.filter(code=properties['code']).first()
                if district is None:
                    print(properties['parent_code'])
                # else:
                    print("error ")
                    break
                if obj is not None:
                    existed_data += 1
                    continue

                if properties['mahalla_id'] == 'null' or properties['mahalla_id'] is None:
                    print(properties)
                    print("\n//////////\n")
                else:
                    try:
                        center = geometry.centroid
                        Mahalla.objects.create(
                            name=properties['mahalla_nomi'],
                            parent_code=properties['code'],
                            district=district,
                            code=properties['mahalla_id'],
                            coordinates=geometry,
                            center_lat=center.y,
                            center_lan=center.x
                        )
                    except IntegrityError:
                        print(f"Mahalla with code {properties['mahalla_id']} already exists. Skipping...")
                        print(properties)
                    except Exception as e:
                        print(f"Unexpected error occurred for Mahalla '{properties.get('mahalla_nomi')}' — {e}")
                        print(properties)
        print("Existed data", existed_data)
        return count
    except Exception as e:
        print("Error ", str(e))
        # {'objectid': 2301, 'region_name': 'Namangan viloyati', 'mahalla_nomi': 'Anorzor MFY', 'parent_code': 1714, 'district': 'Namangan shahar', 'code': 1714401, 'mahalla_id': None, 'shape_Length': 5213.57302520
        # 4035, 'shape_Area': 982087.8449339296}