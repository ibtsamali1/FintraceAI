# core/tasks — Celery background tasks for FinTrace
from .ingestion import process_pdf_upload_task
from .news_watcher import scan_news_feeds_task

__all__ = [
    "process_pdf_upload_task",
    "scan_news_feeds_task",
]
