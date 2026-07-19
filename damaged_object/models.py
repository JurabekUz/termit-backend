from django.db import models
from django.contrib.gis.db.models import PointField, MultiPolygonField

from account.models import CustomUser
from area.models import District, Mahalla
from baseapp.models import AutoTimeBaseModel
from info.models import OpenAreaType, Media


class PropertyType(models.IntegerChoices):
    INDIVIDUAL_HOUSE = 1, "Yakka tartibdagi uy-joy"
    APARTMENT = 2, "Ko‘p qavatli uydagi xonadon"
    NON_RESIDENTIAL = 3, "Noturar bino yoki inshoot"
    LAND = 4, "Yer uchastkasi"
    MULTI_APARTMENT_BUILDING = 6, "Ko‘p kvartirali uy"
    ROAD_LAND = 13, "Avtomobil yo‘llari uchun ajratilgan yer uchastkasi"
    AGRICULTURAL_LAND = 14, "Qishloq xo‘jaligiga mo‘ljallangan yerlari"
    FOREST = 15, "O‘rmon xo‘jaligi yerlari"
    WATER = 16, "Suv xo‘jaligi yerlari"
    PROTECTED_AREA = 17, "Muhofaza etiladigan tabiiy hududlar"
    STATE_RESERVE = 18, "Davlat zaxira yerlari"
    SPECIAL_HOUSE = 19, "Maxsus uy"


class DamagedTypes(models.IntegerChoices):
    mahalla = 1, 'Mahalla'
    open_area = 2, 'Open areas'


class ObjectTypes(models.IntegerChoices):
    households = 1, 'Households'
    social_objects = 2, 'Social objects'
    historical_sites = 3, 'Historical sites'
    adm_buildings = 4, 'Administrative buildings'


class DamagedStatus(models.TextChoices):
    new = 'new', 'New'
    approved = 'approved', 'Approved'
    rejected = 'rejected', 'Rejected'
    in_process = 'in_process', 'In Process'
    completed = 'completed', 'Completed'
    cleaned = 'cleaned', 'Cleaned'


class AppealObjectStatus(models.TextChoices):
    apl_new = 'apl_new', 'Appeal New'
    apl_approved = 'apl_approved', 'Appeal Approved'
    apl_rejected = 'apl_rejected', 'Appeal Rejected'


class DamagedObject(models.Model):
    district = models.ForeignKey(District, on_delete=models.CASCADE, related_name="damaged_objects")
    created_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="damaged_objects")
    appeal = models.ForeignKey(
        "appeal.Appeal", on_delete=models.CASCADE,
        null=True, blank=True, related_name="damaged_objects")
    type = models.PositiveSmallIntegerField(choices=DamagedTypes.choices)
    property_type = models.PositiveSmallIntegerField(choices=PropertyType.choices, null=True, blank=True)
    status = models.CharField(max_length=20, choices=DamagedStatus.choices, null=True, default=DamagedStatus.new)
    apl_status = models.CharField(max_length=20, choices=AppealObjectStatus.choices, null=True, blank=True)
    location = PointField(null=True, blank=True)
    date = models.DateField(null=True, blank=True)
    videos = models.ManyToManyField(Media, related_name="videos_damaged_object", blank=True)
    images = models.ManyToManyField(Media, related_name="damaged_objects", blank=True)
    apl_images = models.ManyToManyField(Media, related_name="apl_damaged_objects", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    director_comment = models.TextField(blank=True)
    unread = models.BooleanField(default=True)

    class Meta:
        db_table = "damaged_object"
        ordering = ("-created_at",)

    def update_status(self, status, plan_item_id=None):
        # update status
        self.status = status
        self.save(update_fields=['status'])

        # create object flow
        if status in [DamagedStatus.approved, DamagedStatus.in_process, DamagedStatus.completed, DamagedStatus.cleaned]:
            DamagedObjectFlow.objects.create(damaged_object=self, plan_item_id=plan_item_id, status=status)

    def create_flow(self, status):
        return DamagedObjectFlow.objects.create(damaged_object=self, status=status)



class MahallaInfo(DamagedObject):
    mahalla = models.ForeignKey(Mahalla, on_delete=models.CASCADE, related_name="damaged_objects")
    object_type = models.PositiveSmallIntegerField(choices=ObjectTypes.choices)
    cadastral_number = models.CharField(max_length=50, blank=True, null=True)
    owner_name = models.CharField(max_length=255, blank=True)
    owner_phone = models.CharField(max_length=15, blank=True)
    address = models.TextField(blank=True)

    class Meta:
        db_table = "mahalla_info"


class OpenAreaInfo(DamagedObject):
    area_type = models.ForeignKey(
        OpenAreaType, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='damaged_objects')
    owner_name = models.CharField(max_length=255, blank=True)
    owner_phone = models.CharField(max_length=15, blank=True)
    address = models.TextField(blank=True)
    hectares = models.DecimalField(max_digits=8, decimal_places=2, help_text="Area amount (hectares)")
    coordinates = MultiPolygonField(null=True, blank=True)

    class Meta:
        db_table = "open_area_info"


class DamagedObjectFlow(models.Model):
    damaged_object = models.ForeignKey(DamagedObject, on_delete=models.CASCADE, related_name='flows')
    plan_item = models.ForeignKey(
        "plan.PlanItem", on_delete=models.SET_NULL, null=True, blank=True, related_name='flows')
    status = models.CharField(max_length=20, choices=DamagedStatus.choices, default=DamagedStatus.approved)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'damaged_object_flow'
        verbose_name = 'Damaged Object Status Flow'
        verbose_name_plural = 'Damaged Object Status Flows'
