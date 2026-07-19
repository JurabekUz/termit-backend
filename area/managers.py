from django.db import models


class RegionManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().defer("coordinates")


class DistrictManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().defer("coordinates")


class MahallaManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().defer("coordinates")

