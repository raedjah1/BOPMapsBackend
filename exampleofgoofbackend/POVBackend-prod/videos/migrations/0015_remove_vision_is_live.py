# Generated by Django 4.2 on 2024-10-17 07:09

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('videos', '0014_vision_is_live'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='vision',
            name='is_live',
        ),
    ]
