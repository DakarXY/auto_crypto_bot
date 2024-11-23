from decimal import Decimal

from django.db import models


class AutoTradingConfig(models.Model):
    """
    Trading configuration singleton model
    """
    PROVIDER_CHOICES = [
        ('BSC', 'BSC'),
        ('Binance', 'Binance'),
    ]


    # Trading parameters
    max_active_trades = models.IntegerField(default=10, 
        help_text="Maximum number of active trades")
    trade_amount = models.DecimalField(
        max_digits=10, decimal_places=2,
        default=Decimal('30.00'),
        help_text="Amount in USDT per trade"
    )
    min_liquidity_usd = models.DecimalField(
        max_digits=10, decimal_places=2,
        default=Decimal('10000.00'),
        help_text="Minimum liquidity in USD"
    )

    # Price targets
    max_price_drop_percent = models.DecimalField(
        max_digits=5, decimal_places=2,
        default=Decimal('20.00'),
        help_text="Maximum price drop from peak (%)"
    )
    profit_target_multiplier = models.DecimalField(
        max_digits=5, decimal_places=2,
        default=Decimal('3.00'),
        help_text="Profit target multiplier (e.g., 3 = 300%)"
    )

    price_check_interval = models.IntegerField(
        default=10,
        help_text="Price monitoring interval (seconds)"
    )

    # Transaction settings
    slippage_percent = models.DecimalField(
        max_digits=5, decimal_places=2,
        default=Decimal('1.00'),
        help_text="Slippage tolerance (%)"
    )
    gas_limit = models.IntegerField(
        default=300000,
        help_text="Gas limit for transactions"
    )

    # General settings
    trading_enabled = models.BooleanField(
        default=True,
        help_text="Enable/disable automatic trading"
    )

    max_transactions_count = models.IntegerField(
        default=100,
        help_text="Max transactions count for token to buy it"
    )
    min_transactions_count = models.IntegerField(
        default=1,
        help_text="Min transactions count for token to buy it"
    )

    provider = models.CharField(max_length=10, choices=PROVIDER_CHOICES, default='BSC')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Trading Configuration"
        verbose_name_plural = "Trading Configuration"

    async def asave(self, *args, **kwargs):
        """Ensure only one instance exists"""
        self.pk = 1
        await super().asave(*args, **kwargs)

    def save(self, *args, **kwargs):
        """Ensure only one instance exists"""
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    async def get_config(cls):
        """Get or create configuration instance"""
        config, created = await cls.objects.aget_or_create(pk=1)
        return config

    def __str__(self):
        return "Trading Configuration"