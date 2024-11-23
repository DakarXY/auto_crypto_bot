from django.db import models


class Currency(models.Model):
    STATUS_CHOICES = [
        ('NEW', 'New'),
        ('ANALYZING', 'Analyzing'),
        ('BUYING', 'Buying'),
        ('BOUGHT', 'Bought'),
        ('SELLING', 'Selling'),
        ('SOLD', 'Sold'),
        ('REJECTED', 'Rejected'),
        ('ERROR', 'Error'),
        ('MANUAL', 'Manual')
    ]

    symbol = models.CharField(max_length=50)
    address = models.CharField(max_length=42, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='NEW')
    price_first_seen = models.DecimalField(max_digits=30, decimal_places=18, null=True, default=0)
    price_peak = models.DecimalField(max_digits=30, decimal_places=18, null=True, default=0)
    current_price = models.DecimalField(max_digits=30, decimal_places=18, null=True, default=0)
    pool_address = models.CharField(max_length=42, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    error_message = models.TextField(null=True, blank=True)
    analyze_data = models.JSONField(null=True)

    def __str__(self):
        return f"{self.symbol} ({self.status})"

    class Meta:
        verbose_name_plural = "Currencies"