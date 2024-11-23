import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from django.core.management.base import BaseCommand

from trading.tasks import trading as trading_tasks # noqa Need to import this to process the decorators

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)
LOG.addHandler(logging.StreamHandler())


class Command(BaseCommand):
    help = "Start the task scheduler"

    """Implemented routines"""

    def handle(self, *args, **options):
        scheduler = BlockingScheduler()
        scheduler.add_job(
            trading_tasks.monitor_new_listings.send,
            IntervalTrigger(seconds=300),
        )
        scheduler.add_job(
            trading_tasks.monitor_active_trades.send,
            IntervalTrigger(seconds=300),
        )
        scheduler.add_job(
            trading_tasks.cleanup_old_data.send,
            IntervalTrigger(hours=24),
        )
        try:
            scheduler.start()
        except KeyboardInterrupt:
            scheduler.shutdown()
