from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand

from trading.models.config import AutoTradingConfig
from trading.services.notification import NotificationService
from trading.tasks.trading import monitor_new_listings


class Command(BaseCommand):
    help = 'Start trading bot'

    def handle(self, *args, **options):
        config = async_to_sync(AutoTradingConfig.get_config)()
        notification = NotificationService()

        if not config.trading_enabled:
            config.trading_enabled = True
            config.save()

        self.stdout.write(self.style.SUCCESS('Trading bot started'))
        notification.notify_all_users("🟢 Trading bot started")

        # Start monitoring
        monitor_new_listings.send()