from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("crafttally", "0010_production_processes"),
    ]

    operations = [
        migrations.RenameField(
            model_name="activity",
            old_name="cost",
            new_name="transaction",
        ),
    ]
