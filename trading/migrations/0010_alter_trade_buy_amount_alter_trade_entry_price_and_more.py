# Generated by Django 4.2.7 on 2024-11-23 11:15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trading', '0009_alter_trade_buy_amount_alter_trade_entry_price_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='trade',
            name='buy_amount',
            field=models.DecimalField(decimal_places=18, max_digits=50, null=True),
        ),
        migrations.AlterField(
            model_name='trade',
            name='entry_price',
            field=models.DecimalField(decimal_places=18, help_text='In currency of wallet spend currency', max_digits=50, null=True),
        ),
        migrations.AlterField(
            model_name='trade',
            name='quantity',
            field=models.DecimalField(decimal_places=18, max_digits=50, null=True),
        ),
    ]
