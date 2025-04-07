# Generated by Django 4.2 on 2025-01-22 06:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0031_remove_creator_available_earnings_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='notify_comment_replies',
            field=models.BooleanField(default=True, help_text='Notify about replies to comments'),
        ),
        migrations.AddField(
            model_name='user',
            name='notify_recommended_visions',
            field=models.BooleanField(default=True, help_text='Notify about recommended visions'),
        ),
        migrations.AddField(
            model_name='user',
            name='notify_subscriptions',
            field=models.BooleanField(default=True, help_text='Notify about activity from subscribed channels'),
        ),
        migrations.AddField(
            model_name='user',
            name='notify_vision_activity',
            field=models.BooleanField(default=True, help_text='Notify about comments and other activity on visions'),
        ),
    ]
