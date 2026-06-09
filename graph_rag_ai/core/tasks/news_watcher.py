"""
News Watcher Celery Task
==========================
Celery background task that scans news feeds for supply-chain disruption events.
Scheduled periodically via Celery Beat (configured in settings.py).

Usage (manual trigger):
    from core.tasks.news_watcher import scan_news_feeds_task
    scan_news_feeds_task.delay()

The Celery Beat schedule in settings.py triggers this automatically:
    CELERY_BEAT_SCHEDULE = {
        "scan-news-feeds-periodically": {
            "task": "core.tasks.news_watcher.scan_news_feeds_task",
            "schedule": 3600.0,  # every hour
        },
    }
"""

import logging

from celery import shared_task

from core.services.news_parser import (
    fetch_news,
    link_event_to_graph,
    parse_disruption,
)

logger = logging.getLogger(__name__)


@shared_task(
    name="core.tasks.news_watcher.scan_news_feeds_task",
    bind=True,
    max_retries=1,
    default_retry_delay=60,
    acks_late=True,
)
def scan_news_feeds_task(self) -> dict:
    """
    Scan news feeds for supply-chain disruption events.

    This task is scheduled by Celery Beat and runs automatically.
    It can also be triggered manually via .delay().

    Returns:
        Dict with processing stats.
    """
    import django
    django.setup()

    from core.models import NewsEvent

    logger.info("Starting news feed scan... [task=%s]", self.request.id)

    articles = fetch_news()

    if not articles:
        logger.info("No articles fetched — scan complete")
        return {
            "articles_fetched": 0,
            "disruptions_detected": 0,
            "events_created": 0,
            "links_created": 0,
        }

    disruptions_detected = 0
    events_created = 0
    total_links = 0

    for article in articles:
        # ── Parse for disruption event ───────────────────────────────
        event = parse_disruption(article)

        if event is None:
            continue

        disruptions_detected += 1

        # ── Store in Django database (deduplicated by title) ─────────
        news_event, created = NewsEvent.objects.get_or_create(
            title=event.title[:500],
            defaults={
                "event_type": event.event_type.value,
                "severity": event.severity.value,
                "description": event.description,
                "locations": event.locations,
                "materials": event.materials,
                "affected_entities": event.affected_entities,
                "source_url": event.source_url or "",
                "source_name": article.source,
                "event_date": event.event_date,
            },
        )

        if created:
            events_created += 1
            logger.info("New disruption event: %s", event.title)

            # ── Link event to Neo4j graph entities ───────────────────
            link_result = link_event_to_graph(event)
            total_links += link_result["links_created"]
        else:
            logger.debug("Duplicate event skipped: %s", event.title)

    result = {
        "articles_fetched": len(articles),
        "disruptions_detected": disruptions_detected,
        "events_created": events_created,
        "links_created": total_links,
    }

    logger.info("News scan complete: %s", result)
    return result
