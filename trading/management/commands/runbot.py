from django.core.management.base import BaseCommand
import asyncio
import logging
from trading.bot import TelegramBotRunner

logger = logging.getLogger('telegram_bot')


class Command(BaseCommand):
    help = 'Run Telegram bot'

    def handle(self, *args, **options):
        self.stdout.write('Starting Telegram bot...')

        try:
            runner = TelegramBotRunner()
            asyncio.run(runner.start())
        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS('Bot stopped by user'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Bot error: {e}'))
            raise
