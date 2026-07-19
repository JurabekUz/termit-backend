from django.core.management.base import BaseCommand
from area.models import District, OpenArea


class Command(BaseCommand):
    help = "Create OpenArea objects for all districts that don't have one."

    def handle(self, *args, **kwargs):
        districts = District.objects.all()
        created_count = 0

        for district in districts:
            open_area, created = OpenArea.objects.get_or_create(district=district, defaults={'hectare': 0})
            if created:
                created_count += 1

        self.stdout.write(self.style.SUCCESS(f"Successfully created {created_count} OpenArea objects."))
