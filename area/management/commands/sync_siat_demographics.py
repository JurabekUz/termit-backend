from django.core.management.base import BaseCommand

from area.bg_services import sync_all_demographics


class Command(BaseCommand):
    help = 'Sync Uzbekistan Region & District population, density, and area from SIAT (stat.uz) with offline fallback.'

    def handle(self, *args, **options):
        self.stdout.write('Syncing SIAT demographics for Regions and Districts...')
        summary = sync_all_demographics()
        source = 'live SIAT API' if summary['live'] else 'official SOATO fallback'
        self.stdout.write(
            self.style.SUCCESS(
                f"Done ({source}): regions={summary['regions_with_population']}, "
                f"districts={summary['districts_with_population']}, "
                f"fallback_filled_districts={summary['fallback_filled_districts']}"
            )
        )
