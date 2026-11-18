from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0007_alter_customuser_regions'),
    ]

    operations = [
        migrations.CreateModel(
            name='SuperAccessChallenge',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('jti', models.CharField(max_length=64, unique=True)),
                ('ip_address', models.GenericIPAddressField()),
                ('totp_step', models.BigIntegerField(unique=True)),
                ('expires_at', models.DateTimeField()),
                ('used_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'account_super_access_challenge',
            },
        ),
        migrations.CreateModel(
            name='SuperAccessRateLimit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ip_address', models.GenericIPAddressField(unique=True)),
                ('failed_attempts', models.PositiveIntegerField(default=0)),
                ('locked_until', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'account_super_access_rate_limit',
            },
        ),
    ]
