import os

from django.db import models
from django.utils.translation import gettext_lazy as _

from baseapp.models import BaseModel
from info.utils import media_upload_path, delete_file_from_storage


class Ministry(BaseModel):

    class Meta:
        db_table = 'ministry'
        verbose_name = _("Ministry")
        verbose_name_plural = _("Ministries")


class OpenAreaType(BaseModel):

    class Meta:
        db_table = 'open_area_type'
        verbose_name = _("Open area type")
        verbose_name_plural = _("Open area types")


class Media(models.Model):
    file = models.FileField(upload_to=media_upload_path, verbose_name="Media")
    name = models.CharField(max_length=50, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "media"

    def save(self, *args, **kwargs):
        # Agar name bo'sh bo'lsa, fayl nomini avtomatik qo‘yish
        if not self.name and self.file:
            self.name = os.path.splitext(self.file.name)[0][:50]  # 50 belgidan oshmasligi uchun kesiladi

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        delete_file_from_storage(self.file.path)
        super().delete(*args, **kwargs)
