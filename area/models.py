from django.db import models
from django.utils import timezone
from django.contrib.gis.db import models as geomodels

from .managers import RegionManager, DistrictManager, MahallaManager


class Region(models.Model):
    name = models.CharField(max_length=255)
    code = models.IntegerField(unique=True)
    coordinates = geomodels.MultiPolygonField()
    center_lat = models.FloatField(null=True)
    center_lan = models.FloatField(null=True)
    population = models.PositiveIntegerField(default=0)
    area = models.PositiveIntegerField(default=0)
    population_density = models.FloatField(default=0)

    objects = RegionManager()

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'region'
        base_manager_name = 'objects'


class District(models.Model):
    name = models.CharField(max_length=255)
    parent_code = models.IntegerField()
    code = models.IntegerField(unique=True)
    coordinates = geomodels.MultiPolygonField()
    center_lat = models.FloatField(null=True)
    center_lan = models.FloatField(null=True)
    region = models.ForeignKey(Region, on_delete=models.PROTECT)
    population = models.PositiveIntegerField(default=0)
    area = models.PositiveIntegerField(default=0)
    population_density = models.FloatField(default=0)

    objects = DistrictManager()

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'district'
        base_manager_name = 'objects'


class MahallaStatus(models.IntegerChoices):
    green = 0, 'Green'
    yellow = 1, 'Yellow'
    red = 2, 'Red'


class Mahalla(models.Model):
    name = models.CharField(max_length=255)
    code = models.IntegerField(unique=True)
    parent_code = models.IntegerField()
    district = models.ForeignKey(District, on_delete=models.PROTECT)
    coordinates = geomodels.MultiPolygonField()
    center_lat = models.FloatField(null=True)
    center_lan = models.FloatField(null=True)
    code_1c = models.CharField(max_length=20, blank=True)
    # info
    info = models.JSONField(null=True)
    phone_number = models.CharField(max_length=15, blank=True)
    address = models.CharField(max_length=500, blank=True)
    # objects counts
    households = models.PositiveIntegerField(default=0)
    social_objects = models.PositiveIntegerField(default=0)
    historical_sites = models.PositiveIntegerField(default=0)
    adm_buildings = models.PositiveIntegerField(default=0)
    # extra
    info_last_updated = models.DateTimeField(auto_now=True)
    damaged_percent = models.DecimalField(default=0, max_digits=5, decimal_places=2)
    status = models.IntegerField(choices=MahallaStatus.choices, default=MahallaStatus.green)
    updated_at = models.DateTimeField(auto_now=True)

    objects = MahallaManager()

    def __str__(self):
        return self.name


    class Meta:
        db_table = 'mahalla'
        base_manager_name = 'objects'


    @property
    def objects_count(self):
        objects_list = (
            self.households,
            self.social_objects,
            self.historical_sites,
            self.adm_buildings
        )
        return sum(objects_list)


    def update_status_and_percentage(self):
        from decimal import Decimal, ROUND_HALF_UP
        """
        Updates the damaged percentage and status based on damaged objects.
        - 0     -> Green
        - 10%       -> Yellow
        - >10 - 100%    -> Red
        """

        damaged_objects_count = self.damaged_objects.filter(
            status__in=['approved', 'in_process', 'completed']
        ).count()

        if self.objects_count == 0:
            percentage = Decimal('0.00')  # Avoid division by zero
        else:
            percentage = (Decimal(damaged_objects_count) / Decimal(self.objects_count)) * Decimal('100')
            percentage = percentage.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # Save percentage
        self.damaged_percent = percentage

        # Update status based on percentage
        if damaged_objects_count == 0:
            self.status = MahallaStatus.green
        elif percentage <= Decimal('10.00'):
            self.status = MahallaStatus.yellow
        else:
            self.status = MahallaStatus.red
        self.save()

    @property
    def percentage_display(self):
        if self.damaged_percent == self.damaged_percent.to_integral():
            return int(self.damaged_percent)
        return self.damaged_percent


class OpenArea(models.Model):
    district = models.OneToOneField(District, on_delete=models.CASCADE, related_name='open_areas')
    hectare = models.DecimalField(default=0, max_digits=8, decimal_places=2)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'open_area'
        ordering = ('-district',)
