# Generated by Django 4.2.7 on 2025-04-07 16:22

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("geo", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="userlocation",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="location_history",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
