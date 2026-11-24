import random
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from account.models import CustomUser, UserRoles
from appeal.models import Appeal, AppealStatus
from area.models import District, Mahalla, OpenArea, Region
from damaged_object.models import (
    AppealObjectStatus,
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


def _make_square_multipolygon(lon: float, lat: float, delta: float = 0.008) -> MultiPolygon:
    poly = Polygon.from_bbox((lon - delta, lat - delta, lon + delta, lat + delta))
    poly.srid = 4326
    mp = MultiPolygon(poly)
    mp.srid = 4326
    return mp


class Command(BaseCommand):
    help = 'Safely seeds realistic demo data across all regions for local dashboard testing (requires DEBUG=True and --confirm).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Required confirmation flag to prevent accidental seeding.',
        )
        parser.add_argument(
            '--force-append',
            action='store_true',
            help='Append demo data even if DamagedObject records already exist.',
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('Refusing to run seed_demo_data when DEBUG is False.')
        if not options['confirm']:
            raise CommandError('Pass --confirm to run seed_demo_data.')

        if DamagedObject.objects.exists() and not options['force_append']:
            self.stdout.write(
                self.style.WARNING(
                    f'DamagedObject already has {DamagedObject.objects.count()} rows. Skipping (pass --force-append to add more).'
                )
            )
            return

        rng = random.Random(20261124)
        now = timezone.now()
        today = now.date()

        with transaction.atomic():
            # 1. OpenAreaType entries
            area_type_names = [
                "Cho'l va dasht hududlari",
                "Qishloq xo'jaligi yerlari",
                "Yaylov va o'tloqlar",
                "O'rmon xo'jaligi yerlari",
                "Qabriston va qo'riqxona atroflari",
            ]
            open_area_types = []
            for name in area_type_names:
                obj, _ = OpenAreaType.objects.get_or_create(name=name, defaults={'is_active': True})
                open_area_types.append(obj)

            # 2. Populate zero OpenArea.hectare records realistically
            open_areas_to_update = []
            for oa in OpenArea.objects.select_related('district').all():
                if not oa.hectare or oa.hectare == Decimal('0.00'):
                    base_ha = rng.randint(1400, 16500)
                    oa.hectare = Decimal(f'{base_ha}.00')
                    open_areas_to_update.append(oa)
            if open_areas_to_update:
                OpenArea.objects.bulk_update(open_areas_to_update, ['hectare'])

            # 3. Users lookup for created_by / sender / performer
            rm_users = list(CustomUser.objects.filter(role=UserRoles.RM))
            le_user = CustomUser.objects.filter(role=UserRoles.LE).first()
            fallback_user = CustomUser.objects.first()

            def _pick_rm(region_id):
                for u in rm_users:
                    if u.region_id == region_id:
                        return u
                return rm_users[0] if rm_users else fallback_user

            # 4. Ensure demo mahallas exist across all 14 regions
            mahallas_pool = []
            mahalla_prefixes = [
                'Yangiobod', 'Dustlik', 'Navruz', 'Guliston', 'Tinchlik',
                'Barkamol', 'Buston', 'Shodlik', 'Mustaqillik', 'Bunyodkor',
                'Kamolot', 'Ziyokor', 'Umid', 'Al-Xorazmiy', 'Chorsu',
            ]
            existing_codes = set(Mahalla.objects.values_list('code', flat=True))

            for region in Region.objects.all().order_by('code'):
                districts = list(District.objects.filter(region=region).order_by('code')[:3])
                # Always ensure Yunusobod (where Bog'iston lives) is included if in Tashkent city
                if region.code == 1726:
                    yunusobod = District.objects.filter(code=1726266).first()
                    if yunusobod and yunusobod not in districts:
                        districts[0] = yunusobod

                for d_idx, district in enumerate(districts):
                    existing_d_mahallas = list(Mahalla.objects.filter(district=district))
                    mahallas_pool.extend(existing_d_mahallas)
                    needed = max(0, 3 - len(existing_d_mahallas))
                    base_lon = district.center_lan or region.center_lan or 69.24
                    base_lat = district.center_lat or region.center_lat or 41.31

                    for m_idx in range(needed):
                        seq = len(existing_d_mahallas) + m_idx + 1
                        code = district.code * 1000 + seq
                        while code in existing_codes:
                            code += 1
                        existing_codes.add(code)

                        offset_lon = (m_idx - 1) * 0.018 + (d_idx * 0.003)
                        offset_lat = ((m_idx % 2) - 0.5) * 0.015
                        m_lon = base_lon + offset_lon
                        m_lat = base_lat + offset_lat

                        # Mix smaller mahallas (can become Red >10%) and larger mahallas (Yellow / Green)
                        if (d_idx + m_idx) % 4 == 0:
                            hh, soc, hist, adm = rng.randint(28, 55), rng.randint(1, 3), rng.randint(0, 2), rng.randint(1, 2)
                        else:
                            hh, soc, hist, adm = rng.randint(140, 420), rng.randint(4, 15), rng.randint(0, 5), rng.randint(1, 6)

                        name_base = mahalla_prefixes[(region.id + d_idx * 3 + m_idx) % len(mahalla_prefixes)]
                        m = Mahalla.objects.create(
                            name=f'{name_base} MFY',
                            code=code,
                            parent_code=district.code,
                            district=district,
                            coordinates=_make_square_multipolygon(m_lon, m_lat, delta=0.007),
                            center_lat=m_lat,
                            center_lan=m_lon,
                            phone_number='+998712001010',
                            address=f'{region.name}, {district.name}, {name_base} ko‘chasi',
                            households=hh,
                            social_objects=soc,
                            historical_sites=hist,
                            adm_buildings=adm,
                        )
                        mahallas_pool.append(m)

            # 5. Create Appeals (26 total across 2025-2026)
            appeals_pool = []
            appeal_statuses = [
                AppealStatus.new,
                AppealStatus.in_process,
                AppealStatus.sent,
                AppealStatus.approved,
                AppealStatus.approved,
                AppealStatus.rejected,
            ]
            all_districts = [m.district for m in mahallas_pool]
            for idx in range(26):
                dist = all_districts[idx % len(all_districts)]
                st = appeal_statuses[idx % len(appeal_statuses)]
                dmg_type = DamagedTypes.mahalla if idx % 4 != 0 else DamagedTypes.open_area
                days_ago = rng.randint(2, 320)
                dt = now - timedelta(days=days_ago, hours=rng.randint(0, 12))
                apl = Appeal.objects.create(
                    sender=le_user or fallback_user,
                    district=dist,
                    status=st,
                    damaged_type=dmg_type,
                    director_comment='Hududiy komissiya tomonidan ko‘rib chiqildi.' if st in (AppealStatus.approved, AppealStatus.rejected) else '',
                    unread=st in (AppealStatus.new, AppealStatus.sent),
                )
                Appeal.objects.filter(pk=apl.pk).update(created_at=dt)
                appeals_pool.append(apl)

            # 6. Create MahallaInfo (~165) and OpenAreaInfo (~45) across 2025 & 2026
            statuses_weighted = [
                DamagedStatus.new,
                DamagedStatus.approved,
                DamagedStatus.approved,
                DamagedStatus.in_process,
                DamagedStatus.in_process,
                DamagedStatus.completed,
                DamagedStatus.completed,
                DamagedStatus.cleaned,
                DamagedStatus.rejected,
            ]
            building_prop_types = [
                PropertyType.INDIVIDUAL_HOUSE,
                PropertyType.INDIVIDUAL_HOUSE,
                PropertyType.APARTMENT,
                PropertyType.NON_RESIDENTIAL,
                PropertyType.MULTI_APARTMENT_BUILDING,
                PropertyType.SPECIAL_HOUSE,
            ]
            open_prop_types = [
                PropertyType.LAND,
                PropertyType.AGRICULTURAL_LAND,
                PropertyType.FOREST,
                PropertyType.WATER,
                PropertyType.PROTECTED_AREA,
                PropertyType.STATE_RESERVE,
                PropertyType.ROAD_LAND,
            ]
            obj_types_weighted = [
                ObjectTypes.households,
                ObjectTypes.households,
                ObjectTypes.households,
                ObjectTypes.social_objects,
                ObjectTypes.adm_buildings,
                ObjectTypes.historical_sites,
            ]

            created_damaged_objects = []
            plan_candidate_objects = []

            for i in range(165):
                # Keep ~18% of mahallas Green (0 damaged objects) by skipping every 5th mahalla
                usable_mahallas = [m for idx_m, m in enumerate(mahallas_pool) if idx_m % 5 != 4]
                mahalla = usable_mahallas[i % len(usable_mahallas)]
                dist = mahalla.district

                # Spread 35% in 2025, 65% in 2026 (with recent cluster in last 30 days)
                if i < 55:
                    month = rng.randint(1, 12)
                    day = rng.randint(1, 28)
                    created_dt = timezone.make_aware(datetime(2025, month, day, rng.randint(8, 18), rng.randint(0, 59)))
                elif i < 130:
                    month = rng.randint(1, 10)
                    day = rng.randint(1, 28)
                    created_dt = timezone.make_aware(datetime(2026, month, day, rng.randint(8, 18), rng.randint(0, 59)))
                else:
                    days_ago = rng.randint(0, 29)
                    created_dt = now - timedelta(days=days_ago, hours=rng.randint(0, 10))

                st = statuses_weighted[i % len(statuses_weighted)]
                # Make recent items slightly more likely to be new/approved
                if (now - created_dt).days < 14 and i % 3 == 0:
                    st = DamagedStatus.new

                obj_type = obj_types_weighted[i % len(obj_types_weighted)]
                prop_type = building_prop_types[i % len(building_prop_types)]
                lon = (mahalla.center_lan or dist.center_lan or 69.24) + rng.uniform(-0.004, 0.004)
                lat = (mahalla.center_lat or dist.center_lat or 41.31) + rng.uniform(-0.004, 0.004)

                linked_appeal = None
                apl_status = None
                if i % 6 == 0:
                    linked_appeal = appeals_pool[i % len(appeals_pool)]
                    apl_status = AppealObjectStatus.apl_approved if st != DamagedStatus.rejected else AppealObjectStatus.apl_rejected

                obj = MahallaInfo.objects.create(
                    district=dist,
                    created_by=_pick_rm(dist.region_id),
                    appeal=linked_appeal,
                    type=DamagedTypes.mahalla,
                    property_type=prop_type,
                    status=st,
                    apl_status=apl_status,
                    location=Point(lon, lat, srid=4326),
                    date=created_dt.date(),
                    director_comment='Tekshiruv dalolatnomasi asosida.' if st != DamagedStatus.new else '',
                    unread=st == DamagedStatus.new,
                    mahalla=mahalla,
                    object_type=obj_type,
                    cadastral_number=f'{str(dist.code)[:4]}:{i + 10:02d}:{rng.randint(10, 99)}:{rng.randint(100, 999)}',
                    owner_name=f'Fuqaro / Tashkilot #{i + 1}',
                    owner_phone=f'+99890{rng.randint(1000000, 9999999)}',
                    address=f'{dist.name}, {mahalla.name}, {i + 1}-uy',
                )
                DamagedObject.objects.filter(pk=obj.pk).update(created_at=created_dt)
                created_damaged_objects.append((obj, created_dt, st))
                if st in (DamagedStatus.in_process, DamagedStatus.completed, DamagedStatus.cleaned):
                    plan_candidate_objects.append((obj, created_dt, st))

            for j in range(45):
                dist = all_districts[(j * 3) % len(all_districts)]
                if j < 15:
                    created_dt = timezone.make_aware(datetime(2025, rng.randint(1, 12), rng.randint(1, 28), 10, 15))
                elif j < 35:
                    created_dt = timezone.make_aware(datetime(2026, rng.randint(1, 10), rng.randint(1, 28), 14, 30))
                else:
                    created_dt = now - timedelta(days=rng.randint(1, 25))

                st = statuses_weighted[(j + 1) % len(statuses_weighted)]
                lon = (dist.center_lan or 69.24) + rng.uniform(-0.02, 0.02)
                lat = (dist.center_lat or 41.31) + rng.uniform(-0.02, 0.02)
                hectares = Decimal(str(round(rng.uniform(2.5, 42.0), 2)))

                obj = OpenAreaInfo.objects.create(
                    district=dist,
                    created_by=_pick_rm(dist.region_id),
                    type=DamagedTypes.open_area,
                    property_type=open_prop_types[j % len(open_prop_types)],
                    status=st,
                    location=Point(lon, lat, srid=4326),
                    date=created_dt.date(),
                    unread=st == DamagedStatus.new,
                    area_type=open_area_types[j % len(open_area_types)],
                    owner_name=f'Xo‘jalik subyekti #{j + 1}',
                    owner_phone=f'+99893{rng.randint(1000000, 9999999)}',
                    address=f'{dist.name}, ochiq maydon uchastkasi #{j + 1}',
                    hectares=hectares,
                    coordinates=_make_square_multipolygon(lon, lat, delta=0.012),
                )
                DamagedObject.objects.filter(pk=obj.pk).update(created_at=created_dt)
                created_damaged_objects.append((obj, created_dt, st))
                if st in (DamagedStatus.in_process, DamagedStatus.completed, DamagedStatus.cleaned):
                    plan_candidate_objects.append((obj, created_dt, st))

            # 7. Create Plans, PlanItems, PlanRegionStatuses and DamagedObjectFlows
            plan_specs = [
                ('2025-yil Bahorgi Termitlarga Qarshi Chora-Tadbirlar Rejasi', date(2025, 3, 1), date(2025, 6, 30), PlanStatus.completed),
                ('2025-yil Kuzgi Dezinfeksiya va Himoya Rejasi', date(2025, 9, 1), date(2025, 11, 30), PlanStatus.completed),
                ('2026-yil 1-yarim yillik Kompleks Tozalash Rejasi', date(2026, 2, 1), date(2026, 7, 31), PlanStatus.completed),
                ('2026-yil 3-chorak Shoshilinch O‘choqlarni Bartaraf Etish Rejasi', date(2026, 8, 1), today - timedelta(days=24), PlanStatus.in_process),
                ('2026-yil 4-chorak Hududiy Profilaktika Rejasi', date(2026, 10, 1), today + timedelta(days=36), PlanStatus.in_process),
                ('2027-yil Qishki Monitoring va Tayyorgarlik Rejasi', today, today + timedelta(days=60), PlanStatus.new),
            ]
            plans = []
            for p_name, f_date, t_date, p_status in plan_specs:
                p = Plan.objects.create(
                    name=p_name,
                    from_date=f_date,
                    to_date=t_date,
                    status=p_status,
                    unread=p_status == PlanStatus.new,
                )
                p_dt = timezone.make_aware(datetime.combine(f_date, datetime.min.time()))
                Plan.objects.filter(pk=p.pk).update(created_at=p_dt)
                plans.append(p)

            # Map plan_candidate_objects into plans[0..4]
            active_and_done_plans = plans[:5]
            obj_to_plan_item = {}
            plan_region_map = {p.id: set() for p in plans}

            for idx, (obj, created_dt, st) in enumerate(plan_candidate_objects):
                if st in (DamagedStatus.completed, DamagedStatus.cleaned):
                    target_plan = active_and_done_plans[idx % 4]  # first 4 plans include completed items
                    is_performed = True
                else:
                    target_plan = plans[3] if idx % 3 == 0 else plans[4]  # active/overdue plans
                    is_performed = False

                done_dt = min(now, created_dt + timedelta(days=rng.randint(5, 35)))
                pi = PlanItem.objects.create(
                    plan=target_plan,
                    item=obj,
                    is_performed=is_performed,
                    performer=_pick_rm(obj.district.region_id),
                    date=done_dt.date() if is_performed else None,
                    description='Kimyoviy va biologik ishlov berish tadbirlari bajarildi.' if is_performed else '',
                )
                obj_to_plan_item[obj.id] = (pi, done_dt)
                plan_region_map[target_plan.id].add(obj.district.region_id)

            # Create PlanRegionStatus rows
            for p in plans:
                reg_ids = plan_region_map[p.id] or set(Region.objects.values_list('id', flat=True)[:5])
                for r_id in reg_ids:
                    PlanRegionStatus.objects.get_or_create(
                        plan=p,
                        region_id=r_id,
                        defaults={
                            'status': p.status,
                            'read_time': now - timedelta(days=rng.randint(1, 20)) if p.status != PlanStatus.new else None,
                        },
                    )

            # Create DamagedObjectFlow history for approved/in_process/completed/cleaned
            for obj, created_dt, st in created_damaged_objects:
                if st not in (
                    DamagedStatus.approved,
                    DamagedStatus.in_process,
                    DamagedStatus.completed,
                    DamagedStatus.cleaned,
                ):
                    continue
                pi_info = obj_to_plan_item.get(obj.id)
                pi = pi_info[0] if pi_info else None
                done_dt = pi_info[1] if pi_info else min(now, created_dt + timedelta(days=12))

                steps = [(DamagedStatus.approved, min(now, created_dt + timedelta(days=2)))]
                if st in (DamagedStatus.in_process, DamagedStatus.completed, DamagedStatus.cleaned):
                    steps.append((DamagedStatus.in_process, min(now, created_dt + timedelta(days=5))))
                if st in (DamagedStatus.completed, DamagedStatus.cleaned):
                    steps.append((st, done_dt))

                for step_status, step_dt in steps:
                    flow = DamagedObjectFlow.objects.create(
                        damaged_object=obj,
                        plan_item=pi if step_status in (DamagedStatus.in_process, DamagedStatus.completed, DamagedStatus.cleaned) else None,
                        status=step_status,
                    )
                    DamagedObjectFlow.objects.filter(pk=flow.pk).update(created_at=step_dt)

            # Guarantee ~12 Red (>10%) hotspot mahallas for realistic risk distribution
            small_mahallas = sorted(mahallas_pool, key=lambda item: item.objects_count)[:12]
            for h_idx, hm in enumerate(small_mahallas):
                target_count = max(4, int(hm.objects_count * 0.14) + 1)
                current_cnt = hm.damaged_objects.filter(
                    status__in=[DamagedStatus.approved, DamagedStatus.in_process, DamagedStatus.completed]
                ).count()
                for k in range(max(0, target_count - current_cnt)):
                    h_dt = now - timedelta(days=rng.randint(1, 28))
                    h_st = [DamagedStatus.approved, DamagedStatus.in_process, DamagedStatus.completed][(h_idx + k) % 3]
                    h_obj = MahallaInfo.objects.create(
                        district=hm.district,
                        created_by=_pick_rm(hm.district.region_id),
                        type=DamagedTypes.mahalla,
                        property_type=PropertyType.INDIVIDUAL_HOUSE,
                        status=h_st,
                        location=Point(
                            (hm.center_lan or 69.24) + rng.uniform(-0.002, 0.002),
                            (hm.center_lat or 41.31) + rng.uniform(-0.002, 0.002),
                            srid=4326,
                        ),
                        date=h_dt.date(),
                        mahalla=hm,
                        object_type=ObjectTypes.households,
                        cadastral_number=f'{str(hm.district.code)[:4]}:99:{h_idx:02d}:{k + 100}',
                        owner_name=f'Ochoq subyekti #{h_idx}-{k}',
                        owner_phone='+998901234567',
                        address=f'{hm.district.name}, {hm.name}, {k + 1}-uy',
                    )
                    DamagedObject.objects.filter(pk=h_obj.pk).update(created_at=h_dt)
                    created_damaged_objects.append((h_obj, h_dt, h_st))

            # 8. Recompute Mahalla damaged_percent & status (Green / Yellow / Red)
            for m in Mahalla.objects.all():
                m.update_status_and_percentage()

        self.stdout.write(
            self.style.SUCCESS(
                f'Demo data seeded: Mahallas={Mahalla.objects.count()}, '
                f'DamagedObjects={DamagedObject.objects.count()} '
                f'(MahallaInfo={MahallaInfo.objects.count()}, OpenAreaInfo={OpenAreaInfo.objects.count()}), '
                f'Flows={DamagedObjectFlow.objects.count()}, Appeals={Appeal.objects.count()}, '
                f'Plans={Plan.objects.count()}, PlanItems={PlanItem.objects.count()}'
            )
        )
