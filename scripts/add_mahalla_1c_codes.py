import json

from area.models import Mahalla


def add_mahalla_1c_codes():
    with open('UzKad-Geonames(9452).json', 'r') as file:
        data = json.load(file)

        mahalla_updates = []
        for item in data:
            try:
                mahalla = Mahalla.objects.get(code=item['UZKAD_KODI'])
                mahalla.code_1c = item['1C_KOD']
                mahalla_updates.append(mahalla)
            except Mahalla.DoesNotExist:
                print(f"Warning: Mahalla with code {item['UZKAD_KODI']} not found.")

        Mahalla.objects.bulk_update(mahalla_updates, ['code_1c'])
        print("Done using bulk_update")
        print(f"Updated {len(mahalla_updates)} mahallas.")
