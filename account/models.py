import random
import string
import uuid

from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator

from django.db import models
from django.utils import timezone
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


class SuperAccessRateLimit(models.Model):
    ip_address = models.GenericIPAddressField(unique=True)
    failed_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'account_super_access_rate_limit'


class SuperAccessChallenge(models.Model):
    jti = models.CharField(max_length=64, unique=True)
    ip_address = models.GenericIPAddressField()
    totp_step = models.BigIntegerField(unique=True, null=True, blank=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'account_super_access_challenge'


class LoginMethod(models.TextChoices):
    ONE_ID = 'oneid', _('OneID')
    SUPER_ACCESS = 'super_access', _('Super Access')


class ActivityAction(models.TextChoices):
    LOGIN = 'login', _('Login')
    LOGOUT = 'logout', _('Logout')
    PAGE_VIEW = 'page_view', _('Page view')
    CREATE = 'create', _('Create')
    UPDATE = 'update', _('Update')
    DELETE = 'delete', _('Delete')
    APPROVE = 'approve', _('Approve')
    REJECT = 'reject', _('Reject')
    ACTION = 'action', _('Action')


class UserSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='sessions')
    login_method = models.CharField(max_length=20, choices=LoginMethod.choices, default=LoginMethod.ONE_ID)
    login_at = models.DateTimeField(default=timezone.now, db_index=True)
    logout_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_seen_at = models.DateTimeField(default=timezone.now, db_index=True)
    logout_reason = models.CharField(max_length=30, blank=True, default='')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True, default='')
    last_page = models.CharField(max_length=500, blank=True, default='')
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = 'account_user_session'
        ordering = ['-login_at']
        indexes = [
            models.Index(fields=['user', '-login_at']),
            models.Index(fields=['is_active', '-last_seen_at']),
        ]
        verbose_name = _("User session")
        verbose_name_plural = _("User sessions")

    def __str__(self):
        return f"{self.user_id} ({self.login_method}) @ {self.login_at}"


class UserActivityLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='activity_logs')
    session = models.ForeignKey(
        UserSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='activities'
    )
    action = models.CharField(max_length=40, choices=ActivityAction.choices, db_index=True)
    method = models.CharField(max_length=10, blank=True, default='')
    endpoint = models.CharField(max_length=500, blank=True, default='')
    from_page = models.CharField(max_length=500, blank=True, default='')
    to_page = models.CharField(max_length=500, blank=True, default='')
    page_title = models.CharField(max_length=255, blank=True, default='')
    resource_type = models.CharField(max_length=64, blank=True, default='', db_index=True)
    resource_id = models.CharField(max_length=64, blank=True, default='')
    object_repr = models.CharField(max_length=255, blank=True, default='')
    description = models.CharField(max_length=500, blank=True, default='')
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True, default='')
    changes = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = 'account_activity_log'
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['action', '-created_at']),
            models.Index(fields=['session', '-created_at']),
        ]
        verbose_name = _("User activity log")
        verbose_name_plural = _("User activity logs")

    def __str__(self):
        return f"{self.user_id} {self.action} {self.to_page or self.endpoint}"
