# Generated by Django 4.2.7 on 2025-04-28 08:41

import django.contrib.postgres.fields
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("pins", "0002_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PinAnalytics",
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
                ("total_views", models.IntegerField(default=0)),
                ("unique_viewers", models.IntegerField(default=0)),
                ("collection_rate", models.FloatField(default=0)),
                (
                    "peak_hour",
                    models.IntegerField(
                        default=0, help_text="Hour of day with most views (0-23)"
                    ),
                ),
                ("last_updated", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name_plural": "Pin analytics",
            },
        ),
        migrations.AddField(
            model_name="pin",
            name="genre",
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name="pin",
            name="mood",
            field=models.CharField(
                blank=True,
                choices=[
                    ("happy", "Happy"),
                    ("chill", "Chill"),
                    ("energetic", "Energetic"),
                    ("sad", "Sad"),
                    ("romantic", "Romantic"),
                    ("focus", "Focus"),
                    ("party", "Party"),
                    ("workout", "Workout"),
                ],
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="pin",
            name="tags",
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(max_length=50),
                blank=True,
                null=True,
                size=None,
            ),
        ),
        migrations.AddIndex(
            model_name="pin",
            index=models.Index(
                fields=["created_at"], name="pins_pin_created_48a338_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="pin",
            index=models.Index(fields=["service"], name="pins_pin_service_6e3a9b_idx"),
        ),
        migrations.AddIndex(
            model_name="pin",
            index=models.Index(fields=["rarity"], name="pins_pin_rarity_079f9c_idx"),
        ),
        migrations.AddIndex(
            model_name="pin",
            index=models.Index(fields=["genre"], name="pins_pin_genre_737c09_idx"),
        ),
        migrations.AddIndex(
            model_name="pin",
            index=models.Index(fields=["mood"], name="pins_pin_mood_c2180d_idx"),
        ),
        migrations.AddIndex(
            model_name="pin",
            index=models.Index(
                fields=["is_private"], name="pins_pin_is_priv_d0aab4_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="pininteraction",
            index=models.Index(
                fields=["interaction_type"], name="pins_pinint_interac_6d77bb_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="pininteraction",
            index=models.Index(
                fields=["created_at"], name="pins_pinint_created_ce1285_idx"
            ),
        ),
        migrations.AddField(
            model_name="pinanalytics",
            name="pin",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="analytics",
                to="pins.pin",
            ),
        ),
    ]
