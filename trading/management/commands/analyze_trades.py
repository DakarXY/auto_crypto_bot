from django.core.management.base import BaseCommand

from trading.models.trade import Trade


class Command(BaseCommand):
    help = 'Analyze trading performance'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Number of days to analyze'
        )
        parser.add_argument(
            '--output',
            type=str,
            default='trading_analysis.csv',
            help='Output file path'
        )

    def handle(self, *args, **options):
        import csv
        from datetime import timedelta

        from django.db.models import Avg, Count, Sum
        from django.utils import timezone

        days = options['days']
        start_date = timezone.now() - timedelta(days=days)

        # Get trades
        trades = Trade.objects.filter(
            buy_timestamp__gte=start_date
        ).select_related('currency')

        # Calculate statistics
        total_trades = trades.count()
        completed_trades = trades.filter(status='SOLD').count()
        active_trades = trades.filter(status='BOUGHT').count()

        profit_trades = trades.filter(
            status='SOLD',
            profit_loss__gt=0
        ).count()

        total_profit = trades.filter(
            status='SOLD'
        ).aggregate(
            total=Sum('profit_loss')
        )['total'] or 0

        avg_profit = trades.filter(
            status='SOLD'
        ).aggregate(
            avg=Avg('profit_loss_percentage')
        )['avg'] or 0

        # Print summary
        self.stdout.write('\nTrading Analysis Summary:')
        self.stdout.write(f'Period: Last {days} days')
        self.stdout.write(f'Total Trades: {total_trades}')
        self.stdout.write(f'Completed Trades: {completed_trades}')
        self.stdout.write(f'Active Trades: {active_trades}')
        self.stdout.write(f'Profitable Trades: {profit_trades}')
        self.stdout.write(f'Total Profit: ${total_profit:.2f} USDT')
        self.stdout.write(f'Average Profit: {avg_profit:.2f}%')

        # Export detailed data
        with open(options['output'], 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                'Symbol',
                'Buy Date',
                'Sell Date',
                'Buy Amount',
                'Sell Amount',
                'Profit/Loss',
                'Profit %',
                'Hold Time (hours)',
                'Sell Reason'
            ])

            for trade in trades.filter(status='SOLD'):
                hold_time = (trade.sell_timestamp - trade.buy_timestamp).total_seconds() / 3600

                writer.writerow([
                    trade.currency.symbol,
                    trade.buy_timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    trade.sell_timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    trade.buy_amount,
                    trade.sell_amount,
                    trade.profit_loss,
                    trade.profit_loss_percentage,
                    round(hold_time, 2),
                    trade.get_sell_reason_display()
                ])

        self.stdout.write(f'\nDetailed analysis exported to {options["output"]}')
