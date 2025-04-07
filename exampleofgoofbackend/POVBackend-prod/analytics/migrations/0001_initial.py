from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('users', '0023_user_birth_date_user_country_user_gender'),
    ]

    operations = [
        # First create base tables
        migrations.CreateModel(
            name='SubscriptionSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(db_index=True)),
                ('total_subscribers', models.IntegerField(default=0)),
                ('new_subscribers', models.IntegerField(default=0)),
                ('churned_subscribers', models.IntegerField(default=0)),
                ('subscription_revenue', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('creator', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='users.creator')),
            ],
            options={
                'unique_together': {('creator', 'date')},
            },
        ),
        migrations.CreateModel(
            name='ViewSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(db_index=True)),
                ('total_views', models.IntegerField(default=0)),
                ('subscriber_views', models.IntegerField(default=0)),
                ('non_subscriber_views', models.IntegerField(default=0)),
                ('highlight_views', models.IntegerField(default=0)),
                ('non_highlight_views', models.IntegerField(default=0)),
                ('engagement_rate', models.FloatField(default=0)),
                ('avg_session_duration', models.FloatField(default=0)),
                ('creator', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='users.creator')),
            ],
            options={
                'unique_together': {('creator', 'date')},
            },
        ),
        migrations.CreateModel(
            name='RevenueSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(db_index=True)),
                ('subscription_revenue', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('tip_revenue', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('total_revenue', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('tip_percentage', models.FloatField(default=0)),
                ('creator', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='users.creator')),
            ],
            options={
                'unique_together': {('creator', 'date')},
            },
        ),
        migrations.CreateModel(
            name='EngagementSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(db_index=True)),
                ('total_likes', models.IntegerField(default=0)),
                ('total_comments', models.IntegerField(default=0)),
                ('unique_engagers', models.IntegerField(default=0)),
                ('avg_likes_per_vision', models.FloatField(default=0)),
                ('avg_comments_per_vision', models.FloatField(default=0)),
                ('creator', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='users.creator')),
            ],
            options={
                'unique_together': {('creator', 'date')},
            },
        ),
        migrations.CreateModel(
            name='DemographicSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(db_index=True)),
                ('age_breakdown', models.JSONField(default=dict)),
                ('gender_breakdown', models.JSONField(default=dict)),
                ('country_breakdown', models.JSONField(default=dict)),
                ('creator', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='users.creator')),
            ],
            options={
                'unique_together': {('creator', 'date')},
            },
        ),
        migrations.CreateModel(
            name='TipSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(db_index=True)),
                ('total_tips', models.IntegerField(default=0)),
                ('total_tip_amount', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('unique_tippers', models.IntegerField(default=0)),
                ('creator', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='users.creator')),
            ],
            options={
                'unique_together': {('creator', 'date')},
            },
        ),
    ] 