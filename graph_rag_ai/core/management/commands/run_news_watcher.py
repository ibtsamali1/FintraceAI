"""
Django management command to run the news watcher scheduler.

This command starts an APScheduler scheduler that periodically scans news feeds
for supply-chain disruption events and links them to the Neo4j knowledge graph.

Usage:
    python manage.py run_news_watcher --interval 60  # Run every 60 minutes
    python manage.py run_news_watcher --once          # Run once and exit

The default interval is read from the NEWS_WATCHER_INTERVAL_MINUTES environment variable.
"""

import logging
from django.core.management.base import BaseCommand
from core.config import NEWS_WATCHER_INTERVAL_MINUTES

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run the periodic news watcher scheduler'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=None,
            help='Interval in minutes between news scans (default: 60)'
        )
        parser.add_argument(
            '--once',
            action='store_true',
            help='Run once and exit (useful for testing)'
        )

    def handle(self, *args, **options):
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger
        from core.tasks.news_watcher import scan_news_feeds
        
        # Get interval from args or config
        interval = options.get('interval') or NEWS_WATCHER_INTERVAL_MINUTES
        once = options.get('once', False)
        
        self.stdout.write(self.style.SUCCESS(f"\n📰 News Watcher Scheduler Starting\n"))
        
        if once:
            self.stdout.write("Running news scan once...")
            try:
                result = scan_news_feeds()
                self.stdout.write(self.style.SUCCESS(f"✓ Scan complete: {result}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"✗ Scan failed: {e}"))
                logger.exception("News watcher scan failed")
            return
        
        # Start scheduler for continuous operation
        scheduler = BackgroundScheduler()
        
        # Schedule the news watcher task
        scheduler.add_job(
            scan_news_feeds,
            trigger=IntervalTrigger(minutes=interval),
            id='news_watcher',
            name='Scan news feeds for supply chain disruptions',
            replace_existing=True
        )
        
        self.stdout.write(f"Scheduled news scan every {interval} minute(s)")
        self.stdout.write("Press Ctrl+C to stop.\n")
        
        try:
            scheduler.start()
        except KeyboardInterrupt:
            self.stdout.write("\nShutting down scheduler...")
            scheduler.shutdown()
            self.stdout.write(self.style.SUCCESS("✓ Stopped"))
