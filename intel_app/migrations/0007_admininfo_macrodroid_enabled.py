from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('intel_app', '0006_seed_system_tasks'),
    ]

    operations = [
        migrations.AddField(
            model_name='admininfo',
            name='macrodroid_enabled',
            field=models.BooleanField(
                default=True,
                help_text=(
                    "When ON, top-up requests redirect customers to the MoMo Transaction ID "
                    "claim page (self-service). When OFF, customers see the legacy 'pay and "
                    "wait for admin to credit' page; admin credits manually from the Requests list."
                ),
            ),
        ),
    ]
