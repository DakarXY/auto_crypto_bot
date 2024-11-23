from django.db import models


class Wallet(models.Model):
    address = models.CharField(max_length=256)
    currency_symbol = models.CharField(max_length=64)
    private_key = models.CharField(max_length=256)
    currency_to_spend_address = models.CharField(max_length=256, default="")

    def __str__(self):
        return self.address