# Generated by Django 4.2.7 on 2025-04-07 16:22

import bopmaps.validators
import django.contrib.auth.models
import django.contrib.gis.db.models.fields
import django.core.validators
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="User",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                (
                    "last_login",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="last login"
                    ),
                ),
                (
                    "is_superuser",
                    models.BooleanField(
                        default=False,
                        help_text="Designates that this user has all permissions without explicitly assigning them.",
                        verbose_name="superuser status",
                    ),
                ),
                (
                    "first_name",
                    models.CharField(
                        blank=True, max_length=150, verbose_name="first name"
                    ),
                ),
                (
                    "last_name",
                    models.CharField(
                        blank=True, max_length=150, verbose_name="last name"
                    ),
                ),
                (
                    "is_staff",
                    models.BooleanField(
                        default=False,
                        help_text="Designates whether the user can log into this admin site.",
                        verbose_name="staff status",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="Designates whether this user should be treated as active. Unselect this instead of deleting accounts.",
                        verbose_name="active",
                    ),
                ),
                (
                    "date_joined",
                    models.DateTimeField(
                        default=django.utils.timezone.now, verbose_name="date joined"
                    ),
                ),
                (
                    "username",
                    models.CharField(
                        error_messages={
                            "unique": "A user with that username already exists."
                        },
                        max_length=150,
                        unique=True,
                        validators=[
                            django.core.validators.RegexValidator(
                                message="Enter a valid username. This value may contain only letters, numbers, and @/./+/-/_ characters.",
                                regex="^[\\w.@+-]+$",
                            )
                        ],
                    ),
                ),
                (
                    "email",
                    models.EmailField(
                        error_messages={
                            "unique": "A user with that email already exists."
                        },
                        max_length=254,
                        unique=True,
                    ),
                ),
                (
                    "profile_pic",
                    models.ImageField(
                        blank=True,
                        null=True,
                        upload_to="profile_pics/",
                        validators=[
                            bopmaps.validators.ImageDimensionsValidator(
                                max_height=2000,
                                max_width=2000,
                                min_height=100,
                                min_width=100,
                            )
                        ],
                    ),
                ),
                ("bio", models.TextField(blank=True, null=True)),
                (
                    "location",
                    django.contrib.gis.db.models.fields.PointField(
                        blank=True, geography=True, null=True, srid=4326
                    ),
                ),
                ("last_active", models.DateTimeField(auto_now=True)),
                ("last_location_update", models.DateTimeField(blank=True, null=True)),
                ("date_of_birth", models.DateField(blank=True, null=True)),
                ("spotify_connected", models.BooleanField(default=False)),
                ("apple_music_connected", models.BooleanField(default=False)),
                ("soundcloud_connected", models.BooleanField(default=False)),
                ("notification_enabled", models.BooleanField(default=True)),
                ("location_tracking_enabled", models.BooleanField(default=True)),
                ("email_notifications_enabled", models.BooleanField(default=True)),
                ("fcm_token", models.CharField(blank=True, max_length=512, null=True)),
                ("device_os", models.CharField(blank=True, max_length=100, null=True)),
                ("app_version", models.CharField(blank=True, max_length=20, null=True)),
                ("is_banned", models.BooleanField(default=False)),
                ("ban_reason", models.TextField(blank=True, null=True)),
                ("banned_until", models.DateTimeField(blank=True, null=True)),
                ("pins_created", models.PositiveIntegerField(default=0)),
                ("pins_collected", models.PositiveIntegerField(default=0)),
                (
                    "groups",
                    models.ManyToManyField(
                        blank=True,
                        help_text="The groups this user belongs to. A user will get all permissions granted to each of their groups.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.group",
                        verbose_name="groups",
                    ),
                ),
                (
                    "user_permissions",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Specific permissions for this user.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.permission",
                        verbose_name="user permissions",
                    ),
                ),
            ],
            options={
                "verbose_name": "User",
                "verbose_name_plural": "Users",
                "indexes": [
                    models.Index(
                        fields=["username"], name="users_user_usernam_65d164_idx"
                    ),
                    models.Index(fields=["email"], name="users_user_email_6f2530_idx"),
                    models.Index(
                        fields=["spotify_connected"],
                        name="users_user_spotify_bf5f7f_idx",
                    ),
                    models.Index(
                        fields=["apple_music_connected"],
                        name="users_user_apple_m_1303c0_idx",
                    ),
                    models.Index(
                        fields=["soundcloud_connected"],
                        name="users_user_soundcl_82f335_idx",
                    ),
                    models.Index(
                        fields=["is_banned"], name="users_user_is_bann_4050e8_idx"
                    ),
                ],
            },
            managers=[
                ("objects", django.contrib.auth.models.UserManager()),
            ],
        ),
    ]
