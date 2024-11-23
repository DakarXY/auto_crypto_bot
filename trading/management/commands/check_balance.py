from asgiref.sync import async_to_sync

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Sum

from trading.models.config import AutoTradingConfig
from trading.models.trade import Trade
from trading.services.binance_client import BinanceClient


class Command(BaseCommand):
    help = 'Check trading balances and limits'

    def handle(self, *args, **options):
        config = async_to_sync(AutoTradingConfig.get_config)()
        binance = BinanceClient(settings.BINANCE_API_KEY, settings.BINANCE_API_SECRET)

        # Get USDT balance
        balance = binance.get_usdt_balance()
        self.stdout.write(f'USDT Balance: ${balance:.2f}')

        # Get active trades
        active_trades = Trade.objects.filter(status='BOUGHT')
        active_count = active_trades.count()

        self.stdout.write(f'\nActive Trades: {active_count}/{config.max_active_trades}')

        total_invested = active_trades.aggregate(
            total=Sum('buy_amount')
        )['total'] or 0

        max_investment = config.trade_amount * config.max_active_trades

        self.stdout.write(f'Total Invested: ${total_invested:.2f}')
        self.stdout.write(f'Maximum Investment: ${max_investment:.2f}')
        self.stdout.write(f'Available for Trading: ${max_investment - total_invested:.2f}')

        # Show active trades
        if active_count > 0:
            self.stdout.write('\nActive Trade Details:')
            for trade in active_trades:
                profit = (trade.currency.current_price - trade.entry_price) / trade.entry_price * 100
                self.stdout.write(
                    f'{trade.currency.symbol}: '
                    f'${trade.buy_amount:.2f} invested, '
                    f'{profit:+.2f}% P/L'
                )