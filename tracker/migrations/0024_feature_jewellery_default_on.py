from django.db import migrations, models


def enable_jewellery(apps, schema_editor):
    apps.get_model('tracker', 'HouseholdConfig').objects.update(feature_jewellery=True)


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0023_householdconfig_feature_expenses'),
    ]

    operations = [
        migrations.AlterField(
            model_name='householdconfig',
            name='feature_jewellery',
            field=models.BooleanField(default=True, help_text='Jewellery vault'),
        ),
        # The old default (off) hid the jewellery page with a 404 for every household.
        migrations.RunPython(enable_jewellery, migrations.RunPython.noop),
    ]
