# Generated by Django 4.2.7 on 2025-05-01 21:51

from django.conf import settings
import django.contrib.gis.db.models.fields
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("geo", "0002_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserMapSettings",
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
                ("show_feature_info", models.BooleanField(default=False)),
                ("use_3d_buildings", models.BooleanField(default=True)),
                ("default_latitude", models.FloatField(default=40.7128)),
                ("default_longitude", models.FloatField(default=-74.006)),
                ("default_zoom", models.FloatField(default=15.0)),
                ("max_cache_size_mb", models.IntegerField(default=500)),
                ("theme", models.CharField(default="light", max_length=20)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Road",
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
                ("osm_id", models.BigIntegerField(unique=True)),
                ("name", models.CharField(blank=True, max_length=255, null=True)),
                ("road_type", models.CharField(max_length=50)),
                ("width", models.FloatField(blank=True, null=True)),
                ("lanes", models.IntegerField(blank=True, null=True)),
                (
                    "geometry",
                    django.contrib.gis.db.models.fields.LineStringField(srid=4326),
                ),
                ("last_updated", models.DateTimeField(auto_now=True)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["osm_id"], name="geo_road_osm_id_e42065_idx"),
                    models.Index(
                        fields=["road_type"], name="geo_road_road_ty_1413d1_idx"
                    ),
                    models.Index(fields=["geometry"], name="road_geom_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="Park",
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
                ("osm_id", models.BigIntegerField(unique=True)),
                ("name", models.CharField(blank=True, max_length=255, null=True)),
                ("park_type", models.CharField(max_length=50)),
                (
                    "geometry",
                    django.contrib.gis.db.models.fields.GeometryField(srid=4326),
                ),
                ("last_updated", models.DateTimeField(auto_now=True)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["osm_id"], name="geo_park_osm_id_daa9cf_idx"),
                    models.Index(
                        fields=["park_type"], name="geo_park_park_ty_1e0dc3_idx"
                    ),
                    models.Index(fields=["geometry"], name="park_geom_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="CachedRegion",
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
                ("name", models.CharField(max_length=255)),
                ("north", models.FloatField()),
                ("south", models.FloatField()),
                ("east", models.FloatField()),
                ("west", models.FloatField()),
                ("min_zoom", models.IntegerField()),
                ("max_zoom", models.IntegerField()),
                ("bounds", django.contrib.gis.db.models.fields.PolygonField(srid=4326)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("bundle_file", models.FileField(upload_to="region_bundles/")),
                ("size_kb", models.IntegerField()),
            ],
            options={
                "indexes": [models.Index(fields=["bounds"], name="region_bounds_idx")],
            },
        ),
        migrations.CreateModel(
            name="Building",
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
                ("osm_id", models.BigIntegerField(unique=True)),
                ("name", models.CharField(blank=True, max_length=255, null=True)),
                ("height", models.FloatField(blank=True, null=True)),
                ("levels", models.IntegerField(blank=True, null=True)),
                (
                    "building_type",
                    models.CharField(blank=True, max_length=50, null=True),
                ),
                (
                    "geometry",
                    django.contrib.gis.db.models.fields.GeometryField(srid=4326),
                ),
                ("last_updated", models.DateTimeField(auto_now=True)),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["osm_id"], name="geo_buildin_osm_id_f6898b_idx"
                    ),
                    models.Index(
                        fields=["building_type"], name="geo_buildin_buildin_08efe1_idx"
                    ),
                    models.Index(fields=["geometry"], name="building_geom_idx"),
                ],
            },
        ),
    ]
