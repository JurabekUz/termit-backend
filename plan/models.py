from django.db import models
from django.utils import timezone

from baseapp.models import AutoTimeBaseModel
from damaged_object.models import DamagedObject, DamagedStatus
from account.models import CustomUser
from info.models import Media


class PlanStatus(models.TextChoices):
    draft = 'draft', 'Draft'
    new = 'new', 'New'
    approved = 'approved', 'Approved'
    rejected = 'rejected', 'Rejected'
    in_process = 'in_process', 'In Process'
    completed = 'completed', 'Completed'


class Plan(AutoTimeBaseModel):
    name = models.CharField(max_length=500)
    from_date = models.DateField()
    to_date = models.DateField()
    status = models.CharField(max_length=20, choices=PlanStatus.choices, default=PlanStatus.draft)
    director_comment = models.TextField(blank=True)
    unread = models.BooleanField(default=True)


    class Meta:
        ordering = ('-created_at',)
        db_table = 'plan'
        verbose_name = 'Plan'
        verbose_name_plural = 'Plans'

    def __str__(self):
        return self.name

    def percentage_of_cleaned(self, region_id=None):
        if self.status == PlanStatus.draft:
            return 0

        items = self.items
        if region_id is not None:
            items = items.filter(item__district__region=region_id)

        total = items.count()
        cleaned = items.filter(flows__status=DamagedStatus.completed).distinct().count()

        percentage = (cleaned / total) * 100 if total > 0 else 0
        return int(percentage) if percentage == int(percentage) else round(percentage, 2)

    def items_count(self, region_id=None):
        if region_id is not None:
            return self.items.filter(item__district__region=region_id).count()
        elif self.status == PlanStatus.draft:
            return self.draft_items.count()
        return self.items.count()

    def update_region_status(self, region_id):
        obj = self.region_statuses.get(region_id=region_id)
        # obj.is_read = True
        obj.status = PlanStatus.in_process
        obj.read_time = timezone.now()
        obj.save(update_fields=['status', 'read_time'])

    def get_regional_status(self, region_id):
        obj = self.region_statuses.get(region_id=region_id)
        return obj.status


class PlanItem(AutoTimeBaseModel):
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(DamagedObject, on_delete=models.CASCADE, related_name='plan_items')

    is_performed = models.BooleanField(default=False)
    performer = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='plan_items'
    )
    date = models.DateField(null=True, blank=True)
    document = models.ForeignKey(Media, on_delete=models.SET_NULL, null=True, blank=True, related_name='document_items')
    description = models.TextField(blank=True)
    images = models.ManyToManyField(Media, related_name="image_items", blank=True)

    class Meta:
        ordering = ('-created_at',)
        db_table = 'plan_item'
        verbose_name = 'Plan Item'
        verbose_name_plural = 'Plan Items'


class PlanRegionStatus(models.Model):
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name='region_statuses')
    region = models.ForeignKey('area.Region', on_delete=models.CASCADE, related_name='plan_statuses')
    # is_read = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=PlanStatus.choices, default=PlanStatus.approved)
    read_time = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'plan_region_status'
        unique_together = ('plan', 'region')
        ordering = ('-read_time',)
        verbose_name = 'Region Status'
        verbose_name_plural = 'Region Statuses'


class DraftItem(models.Model):
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name='draft_items')
    item = models.ForeignKey(DamagedObject, on_delete=models.CASCADE, related_name='draft_items')
