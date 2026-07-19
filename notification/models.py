from django.db import models

from account.models import CustomUser


class ModuleChoices(models.TextChoices):
    plan = 'plan', 'Plan'
    mahalla = 'mahalla', "Mahalla"
    open_area = 'open_area', 'Open area'
    appeal = 'appeal', 'Appeal'



class NotificationCounter(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='counters')
    module = models.CharField(max_length=20, choices=ModuleChoices.choices)
    status = models.CharField(max_length=20)
    number = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = ['user', 'module', 'status']
        db_table = 'notification_counter'

