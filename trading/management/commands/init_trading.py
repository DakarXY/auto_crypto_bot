from django.conf import settings
from django.core.management.base import BaseCommand

from trading.models.config import AutoTradingConfig
from trading.services.binance_client import BinanceClient
from trading.services.notification import NotificationService
from trading.services.pancakeswap import PancakeSwapMonitor


class Command(BaseCommand):
    help = 'Initialize trading configuration and requirements'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Reset existing configuration'
        )

    def handle(self, *args, **options):
        try:
            # Check trading config
            if options['reset']:
                AutoTradingConfig.objects.all().delete()
                self.stdout.write('Existing configuration reset')

            self.stdout.write('Trading configuration initialized')

            # Check Binance connection
            binance = BinanceClient(settings.BINANCE_API_KEY, settings.BINANCE_API_SECRET)
            balance = binance.get_usdt_balance()
            self.stdout.write(f'Binance connection OK, USDT balance: {balance}')

            # Check BSC connection
            monitor = PancakeSwapMonitor()
            block = monitor.w3.eth.block_number
            self.stdout.write(f'BSC connection OK, current block: {block}')

            # Check Telegram bot
            notification = NotificationService()
            notification.notify_all_users("✅ Trading bot initialized")
            self.stdout.write('Telegram bot connection OK')

            self.stdout.write(self.style.SUCCESS('All systems initialized successfully'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error during initialization: {str(e)}'))
            raise
