import mimetypes

from django.contrib.gis.geos import Point, Polygon, MultiPolygon
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from config.utils import CommonException


def validate_video_size(video):
    max_size = 51 * 1024 * 1024  # 51 MB
    if video.size > max_size:
        raise ValidationError(_("The video size should not exceed 50MB."))
    return video


def validate_video_format(video):
    valid_mime_types = ["video/mp4", "video/avi", "video/mov", "video/mkv"]
    mime_type = mimetypes.guess_type(video.name)[0]

    if mime_type not in valid_mime_types:
        raise ValidationError(_("The video format should be MP4, AVI, MOV or MKV."))

    return video


def location_validator(value):
    try:
        return Point(value[0], value[1])  # (longitude, latitude)
    except (ValueError, TypeError):
        raise CommonException(f'Invalid values: {value}. Expected [longitude, latitude] as floats.')


def coordinates_validator(value):
    """coordinates ni List formatidan MultiPolygon shaklga o‘tkazish"""
    try:
        polygons = [Polygon(polygon) for polygon in value]  # Har bir polygonni yaratish
        return MultiPolygon(*polygons)  # MultiPolygon yaratish
    except Exception:
        raise CommonException(_("Invalid coordinates format. Must be a list of polygons."))
