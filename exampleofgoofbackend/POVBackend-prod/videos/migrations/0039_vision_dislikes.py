# Generated by Django 4.2 on 2025-03-10 02:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('videos', '0038_alter_vision_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='vision',
            name='dislikes',
            field=models.IntegerField(db_index=True, default=0),
        ),
    ]
