# Generated by Django 4.2 on 2025-02-24 07:26

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('videos', '0032_vision_average_rating_vision_latent_factors_and_more'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='vision',
            name='videos_visi_average_7be8ac_idx',
        ),
        migrations.RemoveIndex(
            model_name='vision',
            name='vision_ranking_idx',
        ),
        migrations.RenameIndex(
            model_name='vision',
            new_name='vision_ranking_idx',
            old_name='vision_active_idx',
        ),
        migrations.RemoveField(
            model_name='vision',
            name='average_rating',
        ),
        migrations.RemoveField(
            model_name='vision',
            name='latent_factors',
        ),
        migrations.RemoveField(
            model_name='vision',
            name='rating_count',
        ),
    ]
