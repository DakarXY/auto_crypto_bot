import json
import logging
from datetime import timedelta
from decimal import Decimal

import dramatiq
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Sum
from django.utils import timezone

from ..models.config import AutoTradingConfig
from ..models.currency import Currency
from ..models.trade import Trade
from ..services.bsc_trade import BSCTradingService
from ..services.notification import NotificationService
from ..services.pancakeswap import PancakeSwapMonitor
from ..services.price_service import PriceService


logger = logging.getLogger('trading')


@dramatiq.actor(queue_name="listings")
async def monitor_new_listings(session=None):
    """Monitor for new token listings"""
    try:
        config = await AutoTradingConfig.get_config()
        if not config.trading_enabled:
            return

        monitor = PancakeSwapMonitor()

        listings = await monitor.get_new_listings()

        listings_json_formatted = json.dumps(listings, indent=2)
        logger.info(f"Try to monitor new listings: {listings_json_formatted}")

        for listing in listings:
            process_new_listing.send(listing)

    except Exception as e:
        raise e
        logger.error(f"Error monitoring listings: {e}")


@dramatiq.actor(queue_name="monitoring")
async def monitor_active_trades():
    """Monitor active trades for exit conditions"""
    try:
        config = await AutoTradingConfig.get_config()
        if not config.trading_enabled:
            return

        price_service = PriceService()

        async for trade in Trade.objects.filter(status='BOUGHT').select_related('currency'):
            current_price = await price_service.get_token_price(trade.currency.address)
            if not current_price:
                continue

            # Update currency price and peak
            currency = trade.currency
            currency.current_price = current_price
            if current_price > currency.price_peak:
                currency.price_peak = current_price
            await currency.asave()

            # Check sell conditions
            drop_from_peak = ((currency.price_peak - current_price) / currency.price_peak) * 100
            profit = ((current_price - trade.entry_price) / trade.entry_price) * 100

            if drop_from_peak >= config.max_price_drop_percent:
                execute_sell.send(trade.id, 'DROP_FROM_PEAK')
            elif current_price < trade.entry_price:
                execute_sell.send(trade.id, 'BELOW_ENTRY')
            elif profit >= ((config.profit_target_multiplier - 1) * 100):
                execute_sell.send(trade.id, 'PROFIT_TARGET')

    except Exception as e:
        logger.error(f"Error monitoring trades: {e}")


@dramatiq.actor(queue_name="maintenance")
async def cleanup_old_data():
    """Cleanup old data"""
    try:
        cutoff_date = timezone.now() - timedelta(days=30)

        # Clean old trades
        await Trade.objects.filter(
            status='SOLD',
            sell_timestamp__lt=cutoff_date
        ).adelete()

        # Clean old currencies
        await Currency.objects.filter(
            status__in=['SOLD', 'REJECTED', 'ERROR'],
            updated_at__lt=cutoff_date
        ).adelete()

        logger.info("Old data cleanup completed")

    except Exception as e:
        logger.error(f"Error cleaning up old data: {e}")


@dramatiq.actor(queue_name="trading", max_retries=3)
async def process_new_listing(listing_data: dict):
    """Process new token listing"""
    try:
        listing_data_json = json.dumps(listing_data, indent=2)
        logger.info(f"Trying to process listing: {listing_data_json}")
        monitor = PancakeSwapMonitor()
        notification = NotificationService()
        config = await AutoTradingConfig.get_config()
        initial_price = Decimal(listing_data['initial_price'])
        currency, created = await Currency.objects.aget_or_create(
            address=listing_data['token_address'],
            defaults={
                'symbol': listing_data['token_symbol'],
                'status': 'NEW',
                'price_first_seen': initial_price,
                'current_price': initial_price,
                'price_peak': initial_price,
                'pool_address': listing_data['pool_address']
            }
        )

        if not created:
            return

        # Security analysis
        analysis = await monitor.analyze_token_contract(currency.address)
        currency.analyze_data = json.dumps(analysis, indent=2, cls=DjangoJSONEncoder)
        await currency.asave(update_fields=["analyze_data"])

        logger.info(f"Token {currency.symbol} analysis: {analysis}")
        transactions_count = None
        try:
            transactions_count = await monitor.get_token_transfers_count(currency.address)
            analysis.update({"transactions_count": transactions_count})
        except Exception as e:
            raise e
            logger.warning(f" Can't get token txs count{e}")

        if transactions_count:
            analysis.update({"total_transfers": transactions_count})
            if not config.max_transactions_count > transactions_count > config.min_transactions_count:
                currency.status = 'REJECTED'
                currency.error_message = f'Transactions count is {transactions_count}'
                await currency.asave()
                await notification.notify_listing_rejected(currency, analysis)
                return
        else:
            currency.status = 'MANUAL'
            currency.error_message = f'Transactions count is {transactions_count}'
            await currency.asave()
            await notification.notify_listing_rejected(currency, analysis)
            return

        if not monitor._is_token_safe(analysis):
            currency.status = 'REJECTED'
            currency.error_message = 'Failed security checks'
            await currency.asave()
            await notification.notify_listing_rejected(currency, analysis)
            return

        # Liquidity check
        if analysis['liquidity'] < config.min_liquidity_usd:
            currency.status = 'REJECTED'
            currency.error_message = 'Insufficient liquidity'
            await currency.asave()
            await notification.notify_listing_rejected(currency, analysis)
            return

        # Notify users
        await notification.notify_potential_trade_found(currency, analysis)

        # Auto-buy if enabled
        if config.trading_enabled and await _can_execute_trade():
            execute_buy.send(currency.id)

    except Exception as e:
        raise e
        logger.error(f"Error processing listing: {e}")
        if 'currency' in locals():
            currency.status = 'ERROR'
            currency.error_message = str(e)
            await currency.asave()


@dramatiq.actor(queue_name="trading", max_retries=3)
async def execute_buy(currency_id: int, amount: Decimal = None):
    """
    Execute buy order for currency
    """
    notification = NotificationService()
    try:
        # Get services and config
        config = await AutoTradingConfig.get_config()
        currency = await Currency.objects.aget(id=currency_id)
        bsc_service = BSCTradingService(currency.address)

        # Check if we can trade
        if not _can_execute_trade():
            logger.warning(f"Cannot execute trade for {currency.symbol} - trading limits reached")
            currency.status = 'REJECTED'
            currency.error_message = 'Trading limits reached'
            await currency.asave()
            return

        # Use configured amount if not specified
        if amount is None:
            amount = Decimal(config.trade_amount)

        # Check USDT balance
        balance = await bsc_service.get_balance_info()
        if balance.get("wallet_balance", 0) < amount:
            logger.warning(f"Insufficient USDT balance for trade: {balance} < {amount}")
            currency.status = 'REJECTED'
            currency.error_message = 'Insufficient balance'
            await currency.asave()
            await notification.notify_error(
                "Insufficient Balance",
                f"Need {amount} USDT, have {balance} USDT"
            )
            return

        # Update status
        currency.status = 'BUYING'
        await currency.asave()

        # Execute buy order
        order = await bsc_service.buy(amount)

        if order['status']:
            # Create trade record
            trade = await Trade.objects.acreate(
                currency=currency,
                quantity=Decimal(order['expected_out']),
                entry_price=Decimal(order['init_price']),
                status='BOUGHT',
                buy_amount=amount,
                buy_timestamp=timezone.now(),
                wallet=bsc_service.bsc_config.wallet,
            )

            # Update currency status
            currency.status = 'BOUGHT'
            await currency.asave()

            # Notify about successful trade
            await notification.notify_trade_execution(trade, is_buy=True)

            # Start monitoring price
            monitor_price.send(trade.id)
        else:
            currency.status = 'ERROR'
            currency.error_message = order['error']
            await currency.asave()
            await notification.notify_error(
                f"Buy failed for {currency.symbol}",
                order['error']
            )

    except Exception as e:
        logger.error(f"Error executing buy: {e}")
        await notification.notify_error("Buy Error", str(e))


@dramatiq.actor(queue_name="trading", max_retries=3)
async def execute_sell(trade_id: int, reason: str):
    """
    Execute sell order for trade
    """
    notification = None
    try:
        trade = await Trade.objects.select_related("currency").aget(id=trade_id)
        bsc_service = BSCTradingService(trade.wallet.currency_to_spend_address)

        # Update status
        trade.currency.status = 'SELLING'
        await trade.currency.asave()

        notification = NotificationService()

        # Execute sell order
        order = await bsc_service.sell(trade.buy_amount)

        trade.status = 'SOLD'
        trade.exit_price = Decimal(order['order']['price'])
        trade.sell_amount = Decimal(order['order']['cummulativeQuoteQty'])
        trade.sell_order_id = order['order']['orderId']
        trade.sell_timestamp = timezone.now()
        trade.sell_reason = reason

        # Calculate profit/loss
        trade.profit_loss = trade.sell_amount - trade.buy_amount
        trade.profit_loss_percentage = (trade.profit_loss / trade.buy_amount) * 100
        await trade.asave()

        # Update currency status
        trade.currency.status = 'SOLD'
        await trade.currency.asave()

        # Notify about successful trade
        await notification.notify_trade_execution(trade, is_buy=False)
        # else:
        #     trade.currency.status = 'ERROR'
        #     trade.currency.error_message = order['error']
        #     await trade.currency.asave()
        #     await notification.notify_error(
        #         f"Sell failed for {trade.currency.symbol}",
        #         order['error']
        #     )

    except Exception as e:
        logger.error(f"Error executing sell: {e}")
        if notification:
            await notification.notify_error("Sell Error", str(e))


@dramatiq.actor(queue_name="trading", max_retries=0)
async def monitor_price(trade_id: int):
    """
    Monitor price for trade and execute sell if conditions are met
    """
    try:
        trade = await Trade.objects.select_related('currency').aget(id=trade_id)
        if trade.status != 'BOUGHT':
            return
            
        config = await AutoTradingConfig.get_config()
        price_service = PriceService()
        
        # Get current price
        current_price = await price_service.get_token_price(trade.currency.address)
        if not current_price:
            return
            
        # Update currency price
        currency = trade.currency
        currency.current_price = current_price
        
        # Update peak price if needed
        if current_price > currency.price_peak:
            currency.price_peak = current_price
        await currency.asave()
        
        # Check sell conditions
        drop_from_peak = ((currency.price_peak - current_price) / currency.price_peak) * 100
        profit = ((current_price - trade.entry_price) / trade.entry_price) * 100
        
        if drop_from_peak >= config.max_price_drop_percent:
            execute_sell.send(trade.id, 'DROP_FROM_PEAK')
        elif current_price < trade.entry_price:
            execute_sell.send(trade.id, 'BELOW_ENTRY')
        elif profit >= ((config.profit_target_multiplier - 1) * 100):
            execute_sell.send(trade.id, 'PROFIT_TARGET')
        else:
            # Schedule next check
            monitor_price.send_with_options(
                args=(trade.id, ),
                delay=timedelta(seconds=config.price_check_interval)
            )
            
    except Exception as e:
        logger.error(f"Error monitoring price: {e}")

async def _can_execute_trade() -> bool:
    """
    Check if we can execute new trade based on limits
    """
    try:
        config = await AutoTradingConfig.get_config()
        
        # Check number of active trades
        active_trades = await Trade.objects.filter(status='BOUGHT').acount()
        if active_trades >= config.max_active_trades:
            return False
            
        # Check total invested amount
        total_invested = await Trade.objects.filter(status='BOUGHT').aaggregate(total=Sum('buy_amount'))
        total_invested = total_invested.get("total") or 0
        
        if total_invested >= (config.trade_amount * config.max_active_trades):
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"Error checking trade limits: {e}")
        return False
