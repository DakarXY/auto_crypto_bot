from asgiref.sync import async_to_sync

from django.core.management.base import BaseCommand

from trading.models.config import AutoTradingConfig
from trading.services.notification import NotificationService


class Command(BaseCommand):
    help = 'Stop trading bot'

    def handle(self, *args, **options):
        config = async_to_sync(AutoTradingConfig.get_config)()
        notification = NotificationService()

        if config.trading_enabled:
            config.trading_enabled = False
            config.save()

        self.stdout.write(self.style.SUCCESS('Trading bot stopped'))
        notification.notify_all_users("🔴 Trading bot stopped")