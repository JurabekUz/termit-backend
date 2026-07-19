import random
import string

from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator

from django.db import models
from django.utils.translation import gettext_lazy as _


pinfl_regex = RegexValidator(
    regex=r'^\d{14}$',
    message=_("PINFL must consist of 14 digits")
)


class UserRoles(models.TextChoices):
    ADMIN = 'admin', _('Admin')
    CD = 'CD', _('Center Director')
    CM = 'CM', _('Center Manager')
    RM = 'RM', _('Regional Manager')
    ME = 'ME', _('Ministry employee')
    LE = 'LE', _('Legal entity')


class CustomUser(AbstractUser):
    first_name = None
    last_name = None
    pinfl = models.CharField(
        _("PINFL"),
        max_length=14,
        unique=True,
        blank=True,
        null=True,
        help_text=_(
            _("Identification number only 14 digits must be entered")
        ),
        validators=[pinfl_regex],
        error_messages={
            "unique": _("A user with such an identification number already exists."),
        }
    )
    full_name = models.CharField(max_length=250, blank=True, verbose_name=_('F.I.SH'))
    role = models.CharField(max_length=5, choices=UserRoles.choices, default=UserRoles.LE, verbose_name=_('Role'))
    ministry = models.ForeignKey(
        'info.Ministry', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name=_('Ministry'), related_name='users'
    )
    region = models.ForeignKey(
        'area.Region', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name=_('Region'), related_name='users'
    )
    regions = models.ManyToManyField('area.Region', blank=True,
                                     related_name='multi_users', verbose_name=_('Regions'))

    REQUIRED_FIELDS = ["email", "pinfl", "full_name", 'role']

    class Meta:
        db_table = 'account'
        verbose_name = _("User")
        verbose_name_plural = _("Users")


    def __str__(self):
        return self.username


def generate_username(length=8):
    random_username = ''.join(random.choices(string.ascii_lowercase, k=length))

    # If the username is already taken, create a new username.
    while CustomUser.objects.filter(username=random_username).exists():
        random_username = ''.join(random.choices(string.ascii_lowercase, k=length))

    return random_username


def random_password(length=8):
    characters = string.ascii_letters + string.digits + string.punctuation
    password = ''.join(random.choices(characters, k=length))
    return password
