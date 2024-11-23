from django.db import models

from .wallet import Wallet


class BSCConfig(models.Model):
    wallet = models.ForeignKey(Wallet, null=True, on_delete=models.CASCADE)
    rpc_nodes = models.CharField(max_length=600, help_text="Delimiter is ' ' (space)")
    router_address = models.CharField(max_length=128)
    known_tokens = models.CharField(max_length=800, help_text="Example: 'USDT,\<addr\> WBNB,\<addr\>'")
    token_analyze_url_id =  models.CharField(max_length=20, default="56")
    factory_address = models.CharField(max_length=128, default="")
    main_api_url = models.CharField(max_length=128, default="")


    def __str__(self):
        return f"{self.wallet}"

    @classmethod
    async def get_config(cls):
        """Get or create configuration instance"""
        config, created = await cls.objects.select_related("wallet").aget_or_create(pk=1)
        return config
