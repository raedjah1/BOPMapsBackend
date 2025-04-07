# Generated by Django 4.2 on 2025-03-01 05:51

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0035_user_revenuecat_uuid'),
        ('payments', '0011_usersubscription_credits_per_month_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProcessedRevenueCatEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_id', models.CharField(db_index=True, max_length=255, unique=True)),
                ('event_type', models.CharField(max_length=50)),
                ('product_id', models.CharField(blank=True, max_length=255, null=True)),
                ('processed_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='users.user')),
            ],
            options={
                'ordering': ['-processed_at'],
            },
        ),
        migrations.AddIndex(
            model_name='processedrevenuecatevent',
            index=models.Index(fields=['event_id'], name='payments_pr_event_i_4d09ec_idx'),
        ),
    ]
