# Generated by Django 4.2 on 2024-11-20 05:22

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('videos', '0015_remove_vision_is_live'),
    ]

    operations = [
        migrations.AddField(
            model_name='vision',
            name='rtmp_link',
            field=models.URLField(blank=True, max_length=500, null=True),
        ),
        migrations.AddField(
            model_name='vision',
            name='stream_key',
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
    ]
