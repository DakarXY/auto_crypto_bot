from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand
from django.utils import timezone
from decimal import Decimal
from datetime import datetime, timedelta
import pandas as pd
from typing import List, Dict
import logging
from ...services.pancakeswap import PancakeSwapMonitor
from ...services.price_service import PriceService
from typing import Optional
import time
import asyncio


class Command(BaseCommand):
    help = 'Analyze potential profit based on historical listings'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Number of days to analyze'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=100,
            help='Number of tokens to analyze'
        )
        parser.add_argument(
            '--output',
            type=str,
            default='trading_analysis.csv',
            help='Output file name'
        )

    def handle(self, *args, **options):
        analyzer = TradingAnalyzer(
            days=options['days'],
            limit=options['limit'],
            output_file=options['output']
        )
        analyzer.run_analysis()


class TradingAnalyzer:
    def __init__(self, days: int, limit: int, output_file: str):
        self.days = days
        self.limit = limit
        self.output_file = output_file
        self.price_service = PriceService()
        self.monitor = PancakeSwapMonitor()

        # Load trading parameters from config
        self.trade_amount = Decimal(30)
        self.max_price_drop = Decimal(20)
        self.profit_target = Decimal(3)

        self.results = []

    def run_analysis(self):
        """Run full analysis process"""
        try:
            print("Starting trading analysis...")

            # Get historical listings
            listings = self._get_historical_listings()
            print(f"Found {len(listings)} listings to analyze")

            # Analyze each listing
            for listing in listings:
                result = self._analyze_listing(listing)
                if result:
                    self.results.append(result)

            # Generate and save report
            self._generate_report()

            print("Analysis completed!")

        except Exception as e:
            raise e
            print(f"Error during analysis: {str(e)}")

    def _get_historical_listings(self) -> List[Dict]:
        """Get historical token listings"""
        start_date = timezone.now() - timedelta(days=self.days)

        # Get listings from contract events
        listings = []
        try:
            # Get past events from PancakeSwap router
            events = async_to_sync(self.monitor.get_past_liquidity_events)(
                from_block=self._get_block_number(start_date),
                to_block='latest',
                limit=self.limit
            )

            for event in events:
                # Get receipt to find pool

                event_hash = event.get('hash')
                if not event_hash:
                    continue

                receipt = async_to_sync(self.monitor._get_transaction_receipt)(event_hash)
                if not receipt:
                    continue

                token_pair = self.monitor._parse_liquidity_transaction(event)
                if not token_pair:
                    continue

                token_a, token_b = token_pair

                pool_address = self.monitor._find_pool_from_receipt(receipt, [token_a, token_b])
                if not pool_address:
                    continue

                token_data = async_to_sync(self.monitor._get_token_data)(event['hash'], pool_address, event)
                if token_data:
                    listings.append(token_data)

            return listings

        except Exception as e:
            raise e
            logging.error(f"Error getting historical listings: {e}")
            return []

    def _analyze_listing(self, listing: Dict) -> Optional[Dict]:
        """Analyze single listing for potential profit"""
        try:
            # Get price history
            prices = self._get_price_history(listing['token_address'])
            if not prices:
                return None

            # Check security requirements
            security = self._check_token_security(listing['token_address'])
            if not security['is_safe']:
                return None

            # Simulate trading
            entry_price = prices[0]  # Initial price
            peak_price = entry_price
            exit_price = entry_price
            exit_reason = None
            holding_time = 0

            for i, price in enumerate(prices[1:], 1):
                # Update peak price
                if price > peak_price:
                    peak_price = price

                # Check exit conditions
                drop_from_peak = (peak_price - price) / peak_price * 100
                price_change = (price - entry_price) / entry_price * 100

                if drop_from_peak >= self.max_price_drop:
                    exit_price = price
                    exit_reason = 'DROP_FROM_PEAK'
                    holding_time = i
                    break
                elif price < entry_price:
                    exit_price = price
                    exit_reason = 'BELOW_ENTRY'
                    holding_time = i
                    break
                elif price >= (entry_price * self.profit_target):
                    exit_price = price
                    exit_reason = 'PROFIT_TARGET'
                    holding_time = i
                    break

            # Calculate results
            tokens_bought = self.trade_amount / entry_price
            exit_value = tokens_bought * exit_price
            profit_usdt = exit_value - self.trade_amount
            profit_percentage = (exit_value / self.trade_amount - 1) * 100

            return {
                'token_address': listing['token_address'],
                'token_symbol': listing['token_symbol'],
                'listing_time': listing['timestamp'],
                'initial_liquidity_usd': listing['initial_liquidity'],
                'entry_price_usdt': entry_price,
                'peak_price_usdt': peak_price,
                'exit_price_usdt': exit_price,
                'exit_reason': exit_reason,
                'holding_time_minutes': holding_time,
                'profit_usdt': profit_usdt,
                'profit_percentage': profit_percentage,
                'would_trade': security['is_safe'],
                'security_issues': security['issues']
            }

        except Exception as e:
            raise e
            logging.error(f"Error analyzing listing {listing['token_address']}: {e}")
            return None

    def _get_price_history(self, token_address: str) -> List[Decimal]:
        """Get historical prices for token"""
        try:
            # Get minute candles for the first 24 hours
            candles = async_to_sync(self.price_service.get_historical_prices)(
                token_address,
                interval='1m',
                start_time=int(time.time()) - 60 * 60 * 24 * 15  # 30 days
            )
            return [Decimal(str(candle['close'])) for candle in candles]

        except Exception as e:
            raise e
            logging.error(f"Error getting price history: {e}")
            return []

    def _check_token_security(self, token_address: str) -> Dict:
        """Check token security parameters"""
        try:
            security = async_to_sync(self.monitor.analyze_token_contract)(token_address)

            issues = []
            if not security['is_open_source']:
                issues.append("Not open source")
            if security['is_honeypot']:
                issues.append("Honeypot")
            if security['can_take_back_ownership']:
                issues.append("Recoverable ownership")
            if security['owner_change_balance']:
                issues.append("Owner can modify balances")

            return {
                'is_safe': len(issues) == 0,
                'issues': issues
            }

        except Exception as e:
            raise e
            logging.error(f"Error checking security: {e}")
            return {'is_safe': False, 'issues': ["Error checking security"]}

    def _generate_report(self):
        """Generate analysis report"""
        try:
            # Convert results to DataFrame
            df = pd.DataFrame(self.results)

            # Calculate statistics
            if df.to_dict():
                stats = {
                    'Total Tokens Analyzed': len(df),
                    'Tradeable Tokens': len(df[df['would_trade']]),
                    'Average Profit (USDT)': df[df['would_trade']]['profit_usdt'].mean(),
                    'Average Profit (%)': df[df['would_trade']]['profit_percentage'].mean(),
                    'Profitable Trades (%)': (df[df['would_trade']]['profit_usdt'] > 0).mean() * 100,
                    'Average Holding Time (min)': df[df['would_trade']]['holding_time_minutes'].mean(),
                    'Exit Reasons': df[df['would_trade']]['exit_reason'].value_counts().to_dict()
                }

                # Save detailed results
                df.to_csv(self.output_file, index=False)

                # Print summary
                print("\nAnalysis Summary:")
                for key, value in stats.items():
                    print(f"{key}: {value}")

                print(f"\nDetailed results saved to {self.output_file}")
            else:
                print("Error generating report: no tokens")
        except Exception as e:
            raise e
            print(f"Error generating report: {str(e)}")

    def _get_block_number(self, timestamp: datetime) -> int:
        async_to_sync(self.monitor.get_configs)()
        """Get approximate block number for timestamp"""
        try:
            # BSC averages 3 second block time
            current_block = asyncio.run(self.monitor.w3.eth.block_number)
            current_time = timezone.now()

            # Calculate blocks back
            seconds_diff = (current_time - timestamp).total_seconds()
            blocks_back = int(seconds_diff / 3)  # 3 seconds per block

            return max(0, current_block - blocks_back)

        except Exception as e:
            raise e
            logging.error(f"Error getting block number: {e}")
            return 0