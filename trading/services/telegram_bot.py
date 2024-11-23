import asyncio
import json
import logging

from decimal import Decimal, getcontext

from django.utils import timezone
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from ..models.config import AutoTradingConfig
from ..models.currency import Currency
from ..models.trade import Trade
from .telegram_auth import TelegramAuthService
from .notification import NotificationService
from .bsc_trade import BSCTradingService
from ..tasks.trading import monitor_price, execute_sell

logger = logging.getLogger('telegram_bot')


class TradingBot:
    def __init__(self):
        self.auth_service = TelegramAuthService()
        self.notification_service = NotificationService()
        self.application = None
        self._running = False

    async def start(self):
        """Initialize and start the bot"""
        try:
            # Initialize application
            self.application = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

            # Add command handlers
            commands = [
                ('start', self.cmd_start),
                ('help', self.cmd_help),
                ('status', self.cmd_status),
                ('trades', self.cmd_trades),
                ('buy', self.cmd_buy),
                ('sell', self.cmd_sell),
                ('balance', self.cmd_balance),
                ('settings', self.cmd_settings),
            ]

            for command, callback in commands:
                self.application.add_handler(CommandHandler(command, callback))

            # Add auth handlers from auth service
            auth_handlers = self.auth_service.get_handlers()
            for handler in auth_handlers:
                self.application.add_handler(handler)

            # Add callback query handler
            self.application.add_handler(CallbackQueryHandler(self.button_click))

            # Add error handler
            # self.application.add_error_handler(self.error_handler)

            # Start the bot
            self._running = True
            async with self.application:
                await self.application.initialize()
                await self.application.start()
                await self.application.updater.start_polling(
                    allowed_updates=Update.ALL_TYPES,
                    drop_pending_updates=True
                )

                logger.info("Bot started successfully")

                # Keep the bot running
                while self._running:
                    await asyncio.sleep(1)

        except Exception as e:
            raise e
            logger.error(f"Error starting bot: {e}")
            raise

    async def stop(self):
        """Stop the bot gracefully"""
        try:
            self._running = False
            if self.application and self.application.updater:
                await self.application.updater.stop()
            if self.application:
                await self.application.stop()
                await self.application.shutdown()
        except Exception as e:
            raise e
            logger.error(f"Error stopping bot: {e}")
            raise

    @staticmethod
    async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors in telegram updates"""
        logger.error(f"Update {update} caused error {context.error}")
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "Sorry, an error occurred while processing your request."
            )

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        await update.message.reply_text(
            "Welcome to Crypto Trading Bot! 🚀\n\n"
            "Available commands:\n"
            "/help - Show available commands\n"
            "/status - Show bot status\n"
            "/trades - Show active trades\n"
            "/balance - Show account balance\n"
            "/settings - Bot settings"
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        await update.message.reply_text(
            "🤖 Bot Commands:\n\n"
            "Trading:\n"
            "/status - Show bot status\n"
            "/trades - Show active trades\n"
            "/buy <token> <amount> - Buy token\n"
            "/balance - Show account balance\n\n"
            "Settings:\n"
            "/settings - Bot settings"
        )

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        if not await self.auth_service.check_auth(update.effective_user.id):
            await update.message.reply_text("Please register first with /register")
            return

        config = await AutoTradingConfig.get_config()
        active_trades = await Trade.objects.filter(status='BOUGHT').acount()

        status_text = (
            "🤖 Bot Status\n\n"
            f"Trading Enabled: {'✅' if config.trading_enabled else '❌'}\n"
            f"Active Trades: {active_trades}/{config.max_active_trades}\n"
            f"Trade Amount: {config.trade_amount} USDT\n\n"
            "Settings:\n"
            f"Max Drop: {config.max_price_drop_percent}%\n"
            f"Profit Target: {(config.profit_target_multiplier - 1) * 100}%"
        )

        await update.message.reply_text(status_text)

    async def cmd_trades(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /trades command"""
        if not await self.auth_service.check_auth(update.effective_user.id):
            await update.message.reply_text("Please register first with /register")
            return

        trades = Trade.objects.filter(
            status='BOUGHT'
        ).select_related('currency')

        if not await trades.aexists():
            await update.message.reply_text("No active trades")
            return

        message = "📊 Active Trades:\n\n"
        async for trade in trades:
            profit = ((trade.currency.current_price - trade.entry_price) / trade.entry_price) * 100
            message += (
                f"Token: {trade.currency.symbol}\n"
                f"Entry: ${trade.entry_price:.8f}\n"
                f"Current: ${trade.currency.current_price:.8f}\n"
                f"P/L: {profit:+.2f}%\n\n"
            )

        await update.message.reply_text(message)

    async def cmd_buy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /buy command"""
        if not await self.auth_service.check_auth(update.effective_user.id):
            await update.message.reply_text("Please register first with /register")
            return

        if len(context.args) < 2:
            await update.message.reply_text(
                "Usage: /buy <currency_code> <amount>\n"
                "Example: /buy BTC 50"
            )
            return

        try:
            currency_symbol = context.args[0]
            currency = await Currency.objects.filter(symbol=currency_symbol).afirst()
            amount = Decimal(context.args[1])

            trader = BSCTradingService(currency.address)# currency.address)
            # Execute buy through auto trader

            try:
                result = await trader.buy(amount=amount)
                if result['status']:
                    # Create trade record
                    trade = await Trade.objects.acreate(
                        currency=currency,
                        quantity=Decimal(result['expected_out']).quantize(Decimal("1.0000000000")),
                        entry_price=Decimal(result['init_price']).quantize(Decimal("1.0000000000")),
                        status='BOUGHT',
                        buy_amount=amount.quantize(Decimal("1.0000000000")),
                        buy_timestamp=timezone.now(),
                        wallet=trader.bsc_config.wallet,
                    )

                    # Update currency status
                    currency.status = 'BOUGHT'
                    await currency.asave()

                    # Start monitoring price
                    monitor_price.send(trade.id)
                formatted = json.dumps(result, indent=2, cls=DjangoJSONEncoder)
                await update.message.reply_text(f"Buy order executed successfully! \n{formatted}")
            except Exception as e:
                raise e
                await update.message.reply_text(f"Buy failed: {e}")

        except ValueError as e:
            raise e
            await update.message.reply_text("Invalid amount format")
        except Exception as e:
            raise e
            logger.error(f"Buy error: {e}")
            await update.message.reply_text(f"Error executing buy: {str(e)}")


    async def cmd_sell(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /buy command"""
        if not await self.auth_service.check_auth(update.effective_user.id):
            await update.message.reply_text("Please register first with /register")
            return

        if len(context.args) < 1:
            await update.message.reply_text(
                "Usage: /sell <currency_code> <amount>(or empty to sell all)\n"
                "Example: /sell BTC 50"
            )
            return

        try:
            currency_symbol = context.args[0]
            currency = await Currency.objects.filter(symbol=currency_symbol).afirst()
            if len(context.args) > 1:
                amount = Decimal(context.args[1])
            else:
                amount = None

            trader = BSCTradingService(currency.address)# currency.address)
            # Execute buy through auto trader

            try:
                result = await trader.sell(amount=amount)
                if result['status']:
                    # Create trade record
                    trade = await Trade.objects.acreate(
                        currency=currency,
                        quantity=Decimal(result['expected_out']).quantize(Decimal("1.0000000000")),
                        exit_price=Decimal(result['sell_price']).quantize(Decimal("1.0000000000")),
                        status='SOLD',
                        sell_amount=amount.quantize(Decimal("1.0000000000")),
                        sell_timestamp=timezone.now(),
                        wallet=trader.bsc_config.wallet,
                    )


                formatted = json.dumps(result, indent=2, cls=DjangoJSONEncoder)
                await update.message.reply_text(f"Sell order executed successfully! \n{formatted}")
            except Exception as e:
                raise e
                await update.message.reply_text(f"Sell failed: {e}")
        except ValueError as e:
            raise e
            await update.message.reply_text("Invalid amount format")
        except Exception as e:
            raise e
            logger.error(f"Sell error: {e}")
            await update.message.reply_text(f"Error executing sell: {str(e)}")

    async def cmd_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /balance command"""
        if not await self.auth_service.check_auth(update.effective_user.id):
            await update.message.reply_text("Please register first with /register")
            return

        try:
            currency_code = context.args[0]
            currency = Currency.objects().filter(symbol=currency_code).afirst()

            trader = BSCTradingService(currency.address)
            balance = await trader.get_token_balance(currency.address)

            message = (
                "💰 Balance Information\n\n"
                f"Available: ${balance:.2f}\n"
            )

            await update.message.reply_text(message)

        except Exception as e:
            raise e
            logger.error(f"Balance error: {e}")
            await update.message.reply_text("Error getting balance information")

    async def cmd_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /settings command"""
        if not await self.auth_service.check_auth(update.effective_user.id):
            await update.message.reply_text("Please register first with /register")
            return

        config = await AutoTradingConfig.get_config()

        settings_text = (
            "⚙️ Bot Settings\n\n"
            f"Trading Enabled: {'✅' if config.trading_enabled else '❌'}\n"
            f"Trade Amount: {config.trade_amount} USDT\n"
            f"Max Active Trades: {config.max_active_trades}\n"
            f"Max Price Drop: {config.max_price_drop_percent}%\n"
            f"Profit Target: {(config.profit_target_multiplier - 1) * 100}%\n"
            f"Min Liquidity: ${config.min_liquidity_usd:,.2f}"
        )

        await update.message.reply_text(settings_text)

    async def button_click(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button clicks"""
        query = update.callback_query
        await query.answer()

        try:
            if query.data.startswith('trade_'):
                action, trade_id = query.data.split('_')[1:]
                if action == 'sell':
                    execute_sell.send(
                        trade_id=int(trade_id),
                        reason='MANUAL'
                    )
                    await query.edit_message_text("Sell order executed!")

        except Exception as e:
            raise e
            logger.error(f"Button click error: {e}")
            await query.edit_message_text(f"Error: {str(e)}")
