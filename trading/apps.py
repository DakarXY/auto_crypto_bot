import logging

from django.apps import AppConfig

logger = logging.getLogger('trading')


class TradingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'trading'

    def ready(self):
        # Initialize trading configuration
        # from trading.models.config import AutoTradingConfig
        # if not AutoTradingConfig.objects.exists():
        #     AutoTradingConfig.objects.create()
        pass