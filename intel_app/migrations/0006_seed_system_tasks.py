from django.db import migrations


SEED = [
    ("poll_geosams", "Poll the Geosams Controller API for pending bundle transactions.", 90),
    ("cleanup_momo", "Purge old Ignored/Expired MoMo alerts.", 24 * 60 * 60),
]


def seed_tasks(apps, schema_editor):
    SystemTask = apps.get_model('intel_app', 'SystemTask')
    for key, desc, interval in SEED:
        SystemTask.objects.update_or_create(
            key=key,
            defaults={'description': desc, 'interval_seconds': interval},
        )


def unseed_tasks(apps, schema_editor):
    SystemTask = apps.get_model('intel_app', 'SystemTask')
    SystemTask.objects.filter(key__in=[k for k, _, _ in SEED]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('intel_app', '0005_systemtask'),
    ]

    operations = [
        migrations.RunPython(seed_tasks, unseed_tasks),
    ]
