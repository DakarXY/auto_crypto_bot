# Generated by Django 4.2.7 on 2024-11-21 17:19

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('trading', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Wallet',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('address', models.CharField(max_length=42)),
                ('currency_symbol', models.CharField(max_length=64)),
                ('private_key', models.CharField(max_length=64)),
            ],
        ),
        migrations.RemoveField(
            model_name='autotradingconfig',
            name='listing_check_interval',
        ),
        migrations.AddField(
            model_name='autotradingconfig',
            name='max_transactions_count',
            field=models.IntegerField(default=100, help_text='Max transactions count for token to buy it'),
        ),
        migrations.AddField(
            model_name='autotradingconfig',
            name='min_transactions_count',
            field=models.IntegerField(default=1, help_text='Min transactions count for token to buy it'),
        ),
        migrations.AddField(
            model_name='autotradingconfig',
            name='provider',
            field=models.CharField(choices=[('BSC', 'BSC'), ('Binance', 'Binance')], default='BSC', max_length=10),
        ),
        migrations.CreateModel(
            name='BSCConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rpc_nodes', models.CharField(help_text="Delimiter is ' ' (space)", max_length=600)),
                ('router_address', models.CharField(max_length=128)),
                ('known_tokens', models.CharField(help_text="Example: 'USDT,<addr> WBNB,<addr>'", max_length=800)),
                ('wallet', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='trading.wallet')),
            ],
        ),
        migrations.AddField(
            model_name='trade',
            name='wallet',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='trading.wallet'),
        ),
    ]
