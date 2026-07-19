from django.db import models

from account.models import CustomUser
from area.models import District
from baseapp.models import AutoTimeBaseModel
from damaged_object.models import DamagedTypes


class AppealStatus(models.TextChoices):
    new = 'new', 'New'
    in_process = 'in_process', 'In Process'
    sent = 'sent', 'Sent'
    approved = 'approved', 'Approved'
    rejected = 'rejected', 'Rejected'


class Appeal(AutoTimeBaseModel):
    sender = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='send_appeals')
    district = models.ForeignKey(
        District, on_delete=models.CASCADE, related_name='appeals')
    status = models.CharField(max_length=20, choices=AppealStatus.choices, default=AppealStatus.new)
    damaged_type = models.PositiveSmallIntegerField(choices=DamagedTypes.choices)
    director_comment = models.TextField(blank=True)
    unread = models.BooleanField(default=True)

    class Meta:
        db_table = "appeal"
        ordering = ("-created_at",)


    @property
    def obj_count(self):
        return self.damaged_objects.count()
