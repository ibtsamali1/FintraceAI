"""
Django settings for graph_rag_ai project (FinTrace).

Configuration is managed centrally via core.config module,
which reads from .env file using python-decouple.
All environment variables should be set in .env, not here.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Import configuration from centralized config module
from core.config import DJANGO_SECRET_KEY, DEBUG, ALLOWED_HOSTS


# Quick-start development settings - unsuitable for production
SECRET_KEY = DJANGO_SECRET_KEY

# DEBUG and ALLOWED_HOSTS already imported above


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'graph_rag_ai.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'graph_rag_ai.wsgi.application'


# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# Static files
STATIC_URL = 'static/'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ═══════════════════════════════════════════════════════════════════════════
# Media files (uploaded PDFs)
# ═══════════════════════════════════════════════════════════════════════════

MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"

# Allow uploads up to 50 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 52428800   # 50 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 52428800   # 50 MB


# ═══════════════════════════════════════════════════════════════════════════
# LLM Configuration — Ollama (local, no API key required)
# Imported from core.config (managed via .env)
# ═══════════════════════════════════════════════════════════════════════════
# OLLAMA_BASE_URL and OLLAMA_MODEL are available from:
# from core.config import OLLAMA_BASE_URL, OLLAMA_MODEL


# ═══════════════════════════════════════════════════════════════════════════
# External API Keys
# Imported from core.config (managed via .env)
# ═══════════════════════════════════════════════════════════════════════════
# NEWSAPI_KEY is available from:
# from core.config import NEWSAPI_KEY


# ═══════════════════════════════════════════════════════════════════════════
# Logging Configuration
# ═══════════════════════════════════════════════════════════════════════════

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} | {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "core": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": True,
        },
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# Celery — Async Task Queue (Redis Broker)
# ═══════════════════════════════════════════════════════════════════════════

from core.config import REDIS_URL, NEWS_WATCHER_INTERVAL_MINUTES

# Broker & result backend — both use Redis
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)

# Serialization — JSON only (safe, no pickle)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

# Task execution safety
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 600          # hard kill after 10 min
CELERY_TASK_SOFT_TIME_LIMIT = 540     # SoftTimeLimitExceeded after 9 min
CELERY_WORKER_MAX_TASKS_PER_CHILD = 50  # recycle workers to avoid memory leaks

# ── Celery Beat — Periodic Task Schedule ─────────────────────────────────
CELERY_BEAT_SCHEDULE = {
    "scan-news-feeds-periodically": {
        "task": "core.tasks.news_watcher.scan_news_feeds_task",
        "schedule": float(NEWS_WATCHER_INTERVAL_MINUTES * 60),  # seconds
        "options": {"queue": "default"},
    },
}
