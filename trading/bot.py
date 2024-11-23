import asyncio
import os
import django
import logging
import signal

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from trading.services.telegram_bot import TradingBot

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger('telegram_bot')


class TelegramBotRunner:
    def __init__(self):
        self.bot = TradingBot()
        self._is_running = False
        self._tasks = set()

    async def start(self):
        """Start the bot and set up signal handlers"""
        self._is_running = True

        # Set up signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(self.shutdown(sig))
            )

        try:
            logger.info("Starting Telegram bot...")

            # Start the bot
            bot_task = asyncio.create_task(self.bot.start())
            self._tasks.add(bot_task)
            bot_task.add_done_callback(self._tasks.discard)

            # Wait until shutdown is called
            while self._is_running:
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Bot error: {e}")
            await self.shutdown()

    async def shutdown(self, signal=None):
        """Gracefully shut down the bot"""
        if signal:
            logger.info(f"Received exit signal {signal.name}...")

        self._is_running = False
        logger.info("Shutting down bot...")

        # Stop the bot application
        if hasattr(self.bot, 'application'):
            await self.bot.application.stop()
            await self.bot.application.shutdown()

        # Cancel all running tasks
        tasks = [t for t in self._tasks if not t.done()]
        for task in tasks:
            task.cancel()

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # Stop the event loop
        loop = asyncio.get_running_loop()
        loop.stop()


async def main():
    """Main entry point"""
    runner = TelegramBotRunner()
    await runner.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
