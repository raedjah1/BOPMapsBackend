# Generated by Django 4.2 on 2025-01-18 04:51

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('videos', '0024_visionrequest_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='vision',
            name='vision_request',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='requested_vision', to='videos.visionrequest'),
        ),
    ]
