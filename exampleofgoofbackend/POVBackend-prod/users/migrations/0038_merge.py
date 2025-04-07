from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_enable_pgtrgm_extension'),
        ('users', '0036_alter_supportrequest_issue_type'),
        ('users', '0037_enable_trigram'),
    ]

    operations = [] 