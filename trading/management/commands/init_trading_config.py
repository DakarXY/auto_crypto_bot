from django.core.management.base import BaseCommand

from trading.models.config import AutoTradingConfig


class Command(BaseCommand):
    help = 'Initialize trading configuration'

    def handle(self, *args, **options):
        if not AutoTradingConfig.objects.exists():
            AutoTradingConfig.objects.create()
            self.stdout.write(
                self.style.SUCCESS('Trading configuration initialized')
            )
        else:
            self.stdout.write(
                self.style.WARNING('Trading configuration already exists')
            )
