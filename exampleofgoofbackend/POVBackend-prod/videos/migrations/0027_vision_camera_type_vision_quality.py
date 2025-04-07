# Generated by Django 4.2 on 2025-02-06 07:21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('videos', '0026_vision_engagement_score_vision_feature_vector_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='vision',
            name='camera_type',
            field=models.CharField(choices=[('phone', 'Phone'), ('external', 'External'), ('none', 'None')], default='none', max_length=10),
        ),
        migrations.AddField(
            model_name='vision',
            name='quality',
            field=models.CharField(choices=[('1080p', '1080p'), ('4k', '4K'), ('8k', '8K'), ('auto', 'Auto')], default='auto', max_length=5),
        ),
    ]
