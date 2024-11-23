import logging
from typing import Dict

from django.conf import settings
from telegram import Bot
from telegram.error import TelegramError

from ..models.currency import Currency
from ..models.telegram import TelegramUser
from ..models.trade import Trade

logger = logging.getLogger('trading')

class NotificationService:
    def __init__(self):
        self.bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)

    @staticmethod
    async def add_analysis_info_to_message(analysis: dict, message: str):
        message += "\nAnalysis Details:\n"
        
        def get_param_icon(param):
            param_value = analysis.get(param) 
            match param_value:
                case True:
                    return "❌"
                case False:
                    return "✅"
                case _:
                    return "🤷‍♂️"

        match analysis.get('is_open_source'):
            case True:
                open_source_icon = "✅"
            case False:
                open_source_icon = "❌"
            case _:
                open_source_icon = "🤷‍♂️"
        
        message += (
            f"• Open Source: {open_source_icon}\n"
            f"• Honeypot: {get_param_icon('is_honeypot')}\n"
            f"• Owner Take Back Ownership: {get_param_icon('can_take_back_ownership')}\n"
            f"• Owner Balance Modification: {get_param_icon('owner_change_balance')}\n"
            f"• Self Destruct: {get_param_icon('selfdestruct')}\n"
            f"• Trading Cooldown: {get_param_icon('trading_cooldown')}\n"
            f"• Personal Slippage Modifiable: {get_param_icon('personal_slippage_modifiable')}\n"
            f"• Can Pause Trading: {get_param_icon('transfer_pausable')}\n"
            f"• Transactions count limit: {get_param_icon('is_anti_whale')}\n"
            f"• Can change transactions count: {get_param_icon('anti_whale_modifiable')}\n"
            f"• Can not buy: {get_param_icon('cannot_buy')}\n"
            f"• External Call: {get_param_icon('external_call')}\n"
            f"• Is Proxy: {get_param_icon('is_proxy')}\n"
            f"• Can not sell all: {get_param_icon('cannot_sell_all')}\n"
            f"• Has Whitelist: {get_param_icon('is_whitelisted')}\n"
            f"• Has Blacklist: {get_param_icon('is_blacklisted')}\n"
            

            f"💰 Token Economics:\n"
            f"• DEX: {analysis.get('DEX', '0')}%\n"
            f"• Buy Tax: {analysis.get('buy_tax', 0) or '0'}%\n"
            f"• Sell Tax: {analysis.get('sell_tax', 0) or '0'}%\n"
            f"• Total Supply: {float(analysis.get('total_supply', 0) or 0):,.0f}\n"
            f"• Holders: {int(analysis.get('holder_count', 0)  or 0):,}\n"
            f"• Total transfers count: {analysis.get('transactions_count', 0)}\n"
        )
        if 'liquidity' in analysis:
            message += f"• Liquidity: ${analysis['liquidity']:,.2f}\n"
        return message

    async def notify_listing_rejected(
            self,
            currency: Currency,
            analysis: Dict = None
    ):
        """
        Notify about rejected token listing
        """
        try:
            message = (
                f"❌ Token Listing Rejected\n\n"
                f"Token: {currency.symbol}\n"
                f"Address: {currency.address}\n"
                f"Reason: {currency.error_message}\n"
            )

            if analysis:
                message = await self.add_analysis_info_to_message(analysis, message)

            await self.notify_all_users(message)

        except Exception as e:
            logger.error(f"Error sending listing rejection notification: {e}")

    async def notify_trade_skipped(
            self,
            currency: Currency,
            reason: str,
            details: Dict = None
    ):
        """
        Notify about skipped trade opportunity
        """
        try:
            message = (
                f"⚠️ Trade Opportunity Skipped\n\n"
                f"Token: {currency.symbol}\n"
                f"Address: {currency.address}\n"
                f"Price: ${currency.current_price:.8f}\n"
                f"Reason: {reason}\n"
            )

            if details:
                message += "\nDetails:\n"
                for key, value in details.items():
                    message += f"• {key}: {value}\n"

            await self.notify_all_users(message)

        except Exception as e:
            logger.error(f"Error sending trade skip notification: {e}")

    async def notify_potential_trade_found(
            self,
            currency: Currency,
            analysis: Dict = None
    ):
        """
        Notify about skipped trade opportunity
        """
        try:
            message = (
                f"⚠️ Potential Trade Found\n\n"
                f"Token: {currency.symbol}\n"
                f"Address: {currency.address}\n"
                f"Price: ${currency.current_price:.8f}\n"
            )

            if analysis:
                message = await self.add_analysis_info_to_message(analysis, message)

            await self.notify_all_users(message)

        except Exception as e:
            logger.error(f"Error sending trade skip notification: {e}")

    async def notify_all_users(self, message: str):
        """Send message to all active users"""
        try:
            users = TelegramUser.objects.filter(
                is_active=True,
                notification_enabled=True
            )
            
            async for user in users:
                try:
                    await self.bot.send_message(
                        chat_id=user.telegram_id,
                        text=message,
                        parse_mode='HTML'
                    )
                except TelegramError as e:
                    logger.error(f"Error sending message to user {user.telegram_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Error in notify_all_users: {e}")

    async def send_message(self, message: str, telegram_id):
        """Send message to all active users"""
        try:
            await self.bot.send_message(
                chat_id=telegram_id,
                text=message,
                parse_mode='HTML'
            )
        except TelegramError as e:
            logger.error(f"Error sending message to user {telegram_id}: {e}")

        except Exception as e:
            logger.error(f"Error in notify_all_users: {e}")

    async def notify_trade_execution(self, trade: Trade, is_buy: bool = True):
        """Notify about trade execution"""
        try:
            if is_buy:
                message = (
                    f"🟢 Buy Order Executed\n\n"
                    f"Symbol: {trade.currency.symbol}\n"
                    f"Amount: {trade.buy_amount} USDT\n"
                    f"Price: ${trade.entry_price:.8f}\n"
                    f"Quantity: {trade.quantity}\n"
                    f"Transaction: {trade.buy_order_id}\n"
                    f"Time: {trade.buy_timestamp}"
                )
            else:
                message = (
                    f"🔴 Sell Order Executed\n\n"
                    f"Symbol: {trade.currency.symbol}\n"
                    f"Amount: {trade.sell_amount} USDT\n"
                    f"Exit Price: ${trade.exit_price:.8f}\n"
                    f"Profit/Loss: {trade.profit_loss_percentage:+.2f}%\n"
                    # f"Reason: {trade.get_sell_reason_display()}\n"
                    f"Transaction: {trade.sell_order_id}"
                )
            
            await self.notify_all_users(message)
            
        except Exception as e:
            logger.error(f"Error in notify_trade_execution: {e}")

    async def notify_error(self, title: str, error: str):
        """Notify about errors"""
        try:
            message = (
                f"❌ Error: {title}\n\n"
                f"Details: {error}"
            )
            
            await self.notify_all_users(message)
            
        except Exception as e:
            logger.error(f"Error in notify_error: {e}")