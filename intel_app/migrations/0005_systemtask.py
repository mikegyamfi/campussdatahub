from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('intel_app', '0004_geosams_controller_kill_switches'),
    ]

    operations = [
        migrations.CreateModel(
            name='SystemTask',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=100, unique=True)),
                ('description', models.CharField(blank=True, max_length=255)),
                ('interval_seconds', models.PositiveIntegerField(default=60)),
                ('last_run_at', models.DateTimeField(blank=True, null=True)),
                ('last_run_status', models.CharField(blank=True, max_length=50)),
                ('last_run_detail', models.CharField(blank=True, max_length=500)),
                ('enabled', models.BooleanField(default=True)),
            ],
        ),
    ]
