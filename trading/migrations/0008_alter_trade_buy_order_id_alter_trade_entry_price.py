# Generated by Django 4.2.7 on 2024-11-22 19:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trading', '0007_bscconfig_main_api_url'),
    ]

    operations = [
        migrations.AlterField(
            model_name='trade',
            name='buy_order_id',
            field=models.CharField(max_length=66, null=True),
        ),
        migrations.AlterField(
            model_name='trade',
            name='entry_price',
            field=models.DecimalField(decimal_places=18, help_text='In currency of wallet spend currency', max_digits=30),
        ),
    ]
