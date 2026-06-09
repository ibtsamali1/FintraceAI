"""
Celery Application Configuration
==================================
Initializes the Celery app for FinTrace, using Redis as the message broker
and result backend. Auto-discovers tasks from all installed Django apps.

Usage (start the worker):
    celery -A graph_rag_ai worker --loglevel=info

Usage (start periodic scheduler):
    celery -A graph_rag_ai beat --loglevel=info

Combined worker + beat (development only):
    celery -A graph_rag_ai worker --beat --loglevel=info
"""

import os

from celery import Celery

# Set the default Django settings module before Celery starts,
# so that the worker process can bootstrap Django correctly.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "graph_rag_ai.settings")

app = Celery("graph_rag_ai")

# Pull all CELERY_* keys from Django settings (namespace="CELERY").
# e.g. settings.CELERY_BROKER_URL → app.conf.broker_url
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover @shared_task decorated functions in all INSTALLED_APPS.
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Quick smoke-test task — prints the request object to worker stdout."""
    print(f"Request: {self.request!r}")
