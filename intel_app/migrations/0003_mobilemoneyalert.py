from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('intel_app', '0002_agentvodabundleprice_superagentvodabundleprice_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='MobileMoneyAlert',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('raw_sms_body', models.TextField()),
                ('sender_address', models.CharField(max_length=50)),
                ('received_at_phone', models.CharField(blank=True, max_length=100)),
                ('transaction_id', models.CharField(blank=True, max_length=100, null=True, unique=True)),
                ('amount', models.DecimalField(decimal_places=2, default=0.00, max_digits=10)),
                ('status', models.CharField(
                    choices=[
                        ('Unclaimed', 'Unclaimed'),
                        ('Claimed', 'Claimed'),
                        ('Ignored', 'Ignored'),
                        ('Expired', 'Expired'),
                    ],
                    default='Unclaimed',
                    max_length=20,
                )),
                ('claimed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('claimed_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),
    ]
