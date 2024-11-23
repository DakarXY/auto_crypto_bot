from django.db import models

from .currency import Currency
from ..models.wallet import Wallet

class Trade(models.Model):
    STATUS_CHOICES = [
        ('BOUGHT', 'Bought'),
        ('SOLD', 'Sold'),
    ]

    SELL_REASON_CHOICES = [
        ('DROP_FROM_PEAK', 'Dropped from peak (20%)'),
        ('BELOW_ENTRY', 'Below entry price'),
        ('PROFIT_TARGET', '3x profit target'),
        ('MANUAL', 'Manual sell'),
    ]

    currency = models.ForeignKey(Currency, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=50, decimal_places=18, null=True)
    entry_price = models.DecimalField(max_digits=50, decimal_places=18, help_text="In currency of wallet spend currency", null=True)
    exit_price = models.DecimalField(max_digits=50, decimal_places=18, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    buy_amount = models.DecimalField(max_digits=50, decimal_places=18, null=True)
    sell_amount = models.DecimalField(max_digits=50, decimal_places=18, null=True)
    profit_loss = models.DecimalField(max_digits=50, decimal_places=18, null=True)
    profit_loss_percentage = models.DecimalField(max_digits=8, decimal_places=2, null=True)
    buy_order_id = models.CharField(max_length=66, null=True)
    sell_order_id = models.CharField(max_length=66, null=True)
    buy_timestamp = models.DateTimeField()
    sell_timestamp = models.DateTimeField(null=True)
    sell_reason = models.CharField(max_length=20, choices=SELL_REASON_CHOICES, null=True)
    wallet = models.ForeignKey(Wallet, null=True, on_delete=models.CASCADE)