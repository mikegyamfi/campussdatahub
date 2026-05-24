from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('intel_app', '0003_mobilemoneyalert'),
    ]

    operations = [
        migrations.AddField(
            model_name='admininfo',
            name='mtn_api_enabled',
            field=models.BooleanField(
                default=False,
                help_text='Route MTN bundle orders through the Geosams Controller API. '
                          'When OFF, orders are saved as Pending for manual fulfilment.',
            ),
        ),
        migrations.AddField(
            model_name='admininfo',
            name='telecel_api_enabled',
            field=models.BooleanField(
                default=False,
                help_text='Route Telecel bundle orders through the Geosams Controller API.',
            ),
        ),
        migrations.AddField(
            model_name='admininfo',
            name='at_api_enabled',
            field=models.BooleanField(
                default=False,
                help_text='Route AirtelTigo (iShare) bundle orders through the Geosams Controller API.',
            ),
        ),
        migrations.AddField(
            model_name='isharebundletransaction',
            name='submitted_to_api',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='mtntransaction',
            name='submitted_to_api',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='vodafonetransaction',
            name='submitted_to_api',
            field=models.BooleanField(default=False),
        ),
    ]
