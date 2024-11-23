import logging
from decimal import Decimal

from asgiref.sync import async_to_sync
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models.config import AutoTradingConfig
from .models.currency import Currency
from .models.trade import Trade
from .tasks.trading import execute_sell

logger = logging.getLogger('trading')

@receiver(pre_save, sender=Currency)
def update_price_peak(sender, instance, **kwargs):
    """Update price peak if current price is higher"""
    try:
        if instance.id:
            old_instance = Currency.objects.get(id=instance.id)
            if instance.current_price > old_instance.price_peak:
                instance.price_peak = instance.current_price
    except Currency.DoesNotExist:
        # New instance, set peak to current price
        instance.price_peak = instance.current_price

@receiver(post_save, sender=Currency)
def check_trading_conditions(sender, instance, created, **kwargs):
    """Check trading conditions when currency is updated"""
    if not created and instance.status == 'BOUGHT':
        try:
            trade = Trade.objects.get(
                currency=instance,
                status='BOUGHT'
            )
            
            config = async_to_sync(AutoTradingConfig.get_config)()
            
            # Calculate metrics
            drop_from_peak = (instance.price_peak - instance.current_price) / instance.price_peak * 100
            profit = (instance.current_price - trade.entry_price) / trade.entry_price * 100
            
            # Check exit conditions
            if drop_from_peak >= config.max_price_drop_percent:
                execute_sell.send(trade.id, 'DROP_FROM_PEAK')
            elif instance.current_price < trade.entry_price:
                execute_sell.send(trade.id, 'BELOW_ENTRY')
            elif profit >= ((config.profit_target_multiplier - 1) * 100):
                execute_sell.send(trade.id, 'PROFIT_TARGET')
                
        except ObjectDoesNotExist:
            logger.warning(f"No active trade found for currency {instance.symbol}")
        except Exception as e:
            logger.error(f"Error checking trading conditions: {e}")

@receiver(post_save, sender=Trade)
def update_currency_status(sender, instance, created, **kwargs):
    """Update currency status when trade status changes"""
    try:
        currency = instance.currency
        if instance.status == 'BOUGHT':
            currency.status = 'BOUGHT'
        elif instance.status == 'SOLD':
            currency.status = 'SOLD'
        currency.save()
    except Exception as e:
        logger.error(f"Error updating currency status: {e}")