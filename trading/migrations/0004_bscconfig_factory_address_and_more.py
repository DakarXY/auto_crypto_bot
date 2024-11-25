# Generated by Django 4.2.7 on 2024-11-22 17:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trading', '0003_bscconfig_token_analyze_url_id_currency_analyze_data'),
    ]

    operations = [
        migrations.AddField(
            model_name='bscconfig',
            name='factory_address',
            field=models.CharField(default='', max_length=128),
        ),
        migrations.AddField(
            model_name='wallet',
            name='currency_to_spend_address',
            field=models.CharField(default='', max_length=256),
        ),
        migrations.AlterField(
            model_name='bscconfig',
            name='known_tokens',
            field=models.CharField(help_text="Example: 'USDT,\\<addr\\> WBNB,\\<addr\\>'", max_length=800),
        ),
        migrations.AlterField(
            model_name='currency',
            name='status',
            field=models.CharField(choices=[('NEW', 'New'), ('ANALYZING', 'Analyzing'), ('BUYING', 'Buying'), ('BOUGHT', 'Bought'), ('SELLING', 'Selling'), ('SOLD', 'Sold'), ('REJECTED', 'Rejected'), ('ERROR', 'Error'), ('MANUAL', 'Manual')], default='NEW', max_length=20),
        ),
        migrations.AlterField(
            model_name='wallet',
            name='address',
            field=models.CharField(max_length=256),
        ),
        migrations.AlterField(
            model_name='wallet',
            name='private_key',
            field=models.CharField(max_length=256),
        ),
    ]
