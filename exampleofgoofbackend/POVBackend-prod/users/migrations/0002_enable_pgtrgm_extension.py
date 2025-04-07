from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),  # Update this according to your current migrations
    ]

    operations = [
        TrigramExtension(),
    ] 