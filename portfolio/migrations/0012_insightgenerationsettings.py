# Django migration: InsightGenerationSettings singleton

from django.db import migrations, models


def _seed_solo(apps, schema_editor):
    Model = apps.get_model('portfolio', 'InsightGenerationSettings')
    Model.objects.get_or_create(pk=1, defaults={'cooldown_days': 30})


class Migration(migrations.Migration):

    dependencies = [
        ('portfolio', '0011_usstockholding'),
    ]

    operations = [
        migrations.CreateModel(
            name='InsightGenerationSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                (
                    'cooldown_days',
                    models.PositiveSmallIntegerField(
                        default=30,
                        help_text='Minimum calendar days between runs per AccountGroup (ignored when DEBUG=True).',
                    ),
                ),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'AI insight cooldown',
                'verbose_name_plural': 'AI insight cooldown',
            },
        ),
        migrations.RunPython(_seed_solo, migrations.RunPython.noop),
    ]
