# Generated by Django 4.2 on 2024-10-15 05:36

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0017_collabinvite_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='ActivityEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action_type', models.CharField(choices=[('post', 'Post'), ('like', 'Like'), ('comment', 'Comment'), ('subscribe', 'Subscribe'), ('event_create', 'Event Create')], max_length=20)),
                ('target_id', models.PositiveIntegerField()),
                ('target_type', models.CharField(choices=[('vision', 'Vision'), ('event', 'Event'), ('comment', 'Comment'), ('creator', 'Creator')], max_length=20)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='activities', to='users.user')),
            ],
        ),
        migrations.CreateModel(
            name='NotificationTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=50, unique=True)),
                ('template_en', models.TextField()),
                ('template_es', models.TextField()),
            ],
        ),
        migrations.CreateModel(
            name='UserActivity',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('seen', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='users.activityevent')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='users.user')),
            ],
        ),
        migrations.CreateModel(
            name='ActivityItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('image_url', models.URLField(blank=True, null=True)),
                ('creator', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='users.creator')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='users.user')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
