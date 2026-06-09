"""
Centralized Configuration Management for FinTrace
====================================================

This module provides a single source of truth for all environment-based
configuration using python-decouple. All sensitive values (API keys, secrets,
credentials) are loaded from the .env file.

All configuration should be imported from this module:
    from core.config import DJANGO_SECRET_KEY, NEO4J_URI, OLLAMA_MODEL, etc.

This ensures:
- Type safety (cast functions for different types)
- Default fallbacks with sensible production defaults
- Clear documentation of all required environment variables
- Easy testing via environment variable mocking

Usage:
    from core.config import (
        DJANGO_SECRET_KEY, DEBUG, OLLAMA_BASE_URL, NEO4J_URI,
        NEWSAPI_KEY, PDF_PATH, CHUNK_SIZE
    )
"""

import logging
from decouple import config, Csv
from pathlib import Path

logger = logging.getLogger(__name__)

# =============================================================================
# Django Configuration
# =============================================================================
DJANGO_SECRET_KEY: str = config(
    "DJANGO_SECRET_KEY",
    default="django-insecure-change-this-in-production",
    cast=str,
)
"""Django secret key for session/CSRF protection. MUST be changed in production."""

DEBUG: bool = config(
    "DEBUG",
    default=True,
    cast=bool,
)
"""Enable Django debug mode (development only)."""

ALLOWED_HOSTS: list = config(
    "ALLOWED_HOSTS",
    default="localhost,127.0.0.1",
    cast=Csv(),
)
"""Comma-separated list of allowed hostnames."""

# =============================================================================
# OpenAI API Configuration (gpt-4o-mini)
# =============================================================================
OPENAI_API_KEY: str = config(
    "OPENAI_API_KEY",
    default="",
    cast=str,
)
"""
OpenAI API key for gpt-4o-mini inference.
Used for entity extraction, news disruption parsing, and agent reasoning.
Get a key at: https://platform.openai.com/api-keys
"""

if not OPENAI_API_KEY:
    logger.warning(
        "OPENAI_API_KEY is not set. LLM-powered features (entity extraction, "
        "news parsing, risk agent) will fail. Set it in your .env file."
    )


# =============================================================================
# Neo4j Database Configuration
# =============================================================================
NEO4J_URI: str = config(
    "NEO4J_URI",
    default="neo4j+s://6fcfab01.databases.neo4j.io",
    cast=str,
)
"""
Neo4j connection URI.
- Aura (cloud): neo4j+s://[instance-id].databases.neo4j.io
- Local: neo4j://localhost:7687
"""

NEO4J_USER: str = config(
    "NEO4J_USER",
    default="neo4j",
    cast=str,
)
"""Neo4j database username."""

NEO4J_PASSWORD: str = config(
    "NEO4J_PASSWORD",
    default="",
    cast=str,
)
"""Neo4j database password (CRITICAL: Never commit real values)."""

# Validate Neo4j configuration
if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
    logger.error(
        "Neo4j configuration incomplete. Set NEO4J_URI, NEO4J_USER, and "
        "NEO4J_PASSWORD in your .env file."
    )

# =============================================================================
# Ollama LLM Configuration (Local Inference)
# =============================================================================
OLLAMA_BASE_URL: str = config(
    "OLLAMA_BASE_URL",
    default="http://localhost:11434",
    cast=str,
)
"""
Ollama API base URL. Defaults to local development server.
Ensure Ollama is running: ollama serve
"""

OLLAMA_MODEL: str = config(
    "OLLAMA_MODEL",
    default="llama3.2",
    cast=str,
)
"""
Ollama model name. Must be pulled before use: ollama pull llama3.2
Options: llama3.2, llama2, mistral, neural-chat, etc.
"""

# =============================================================================
# NewsAPI Configuration (Optional)
# =============================================================================
NEWSAPI_KEY: str = config(
    "NEWSAPI_KEY",
    default="",
    cast=str,
)
"""
NewsAPI key for fetching supply chain news.
Get a free key at: https://newsapi.org
Leave empty to disable news ingestion.
"""

NEWSAPI_BASE_URL: str = "https://newsapi.org/v2/everything"
"""NewsAPI endpoint (read-only constant)."""

# =============================================================================
# PDF Processing Configuration
# =============================================================================
PDF_PATH: str = config(
    "PDF_PATH",
    default=str(Path(__file__).resolve().parent.parent.parent / "pdf" / "document.pdf"),
    cast=str,
)
"""
Path to PDF file for ingestion.
Defaults to: <project_root>/pdf/document.pdf
Can be absolute or relative to project root.
"""

PDF_CHUNK_SIZE: int = config(
    "PDF_CHUNK_SIZE",
    default=600,
    cast=int,
)
"""Document chunk size for text splitting (characters)."""

PDF_CHUNK_OVERLAP: int = config(
    "PDF_CHUNK_OVERLAP",
    default=90,
    cast=int,
)
"""Character overlap between document chunks for context preservation."""

PDF_BATCH_SIZE: int = config(
    "PDF_BATCH_SIZE",
    default=5,
    cast=int,
)
"""Number of chunks to process in parallel during ingestion."""

# =============================================================================
# Supply Chain Keywords (for news parsing)
# =============================================================================
DEFAULT_NEWS_KEYWORDS: list = [
    "supply chain disruption",
    "shipping delays",
    "port congestion",
    "logistics crisis",
    "trade war",
    "tariffs",
    "semiconductor shortage",
    "raw material shortage",
]
"""Default keywords for supply chain news search when none provided."""

# =============================================================================
# Logging Configuration
# =============================================================================
LOG_LEVEL: str = config(
    "LOG_LEVEL",
    default="INFO",
    cast=str,
)
"""Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)."""

# =============================================================================
# Optional/Advanced Configuration
# =============================================================================
USE_STRUCTURED_OUTPUTS: bool = config(
    "USE_STRUCTURED_OUTPUTS",
    default=True,
    cast=bool,
)
"""Whether to use LLM structured output mode (with fallback to JSON parsing)."""

GRAPH_DEPTH_LIMIT: int = config(
    "GRAPH_DEPTH_LIMIT",
    default=3,
    cast=int,
)
"""Maximum traversal depth for graph queries (prevents expensive queries)."""

# =============================================================================
# Task Scheduling Configuration
# =============================================================================
NEWS_WATCHER_INTERVAL_MINUTES: int = config(
    "NEWS_WATCHER_INTERVAL_MINUTES",
    default=60,
    cast=int,
)
"""Interval in minutes between periodic news watcher scans."""

# =============================================================================
# Redis Configuration (Caching, Task Queuing, Sessions)
# =============================================================================
REDIS_URL: str = config(
    "REDIS_URL",
    default="redis://localhost:6379/0",
    cast=str,
)
"""
Redis connection URL for caching, task queuing, and sessions.
Format: redis://[password@]host:port/db
Examples:
  - Local: redis://localhost:6379/0
  - Docker: redis://redis:6379/0
  - Remote: redis://user:password@redis.example.com:6379/0
"""

REDIS_CACHE_TIMEOUT: int = config(
    "REDIS_CACHE_TIMEOUT",
    default=3600,  # 1 hour
    cast=int,
)
"""Default cache timeout in seconds (for embeddings, results, etc.)."""

REDIS_EMBEDDING_CACHE_TTL: int = config(
    "REDIS_EMBEDDING_CACHE_TTL",
    default=86400,  # 24 hours
    cast=int,
)
"""Time-to-live for cached embeddings in seconds (24 hours by default)."""

USE_REDIS_CACHE: bool = config(
    "USE_REDIS_CACHE",
    default=True,
    cast=bool,
)
"""Whether to enable Redis caching for embeddings and chunk processing."""

# =============================================================================
# Summary and Validation
# =============================================================================
def get_config_summary() -> dict:
    """
    Returns a dictionary of all public configuration (non-sensitive values).
    Useful for debugging and health checks.
    """
    return {
        "debug": DEBUG,
        "allowed_hosts": ALLOWED_HOSTS,
        "neo4j_uri": NEO4J_URI,
        "neo4j_user": NEO4J_USER,
        "ollama_base_url": OLLAMA_BASE_URL,
        "ollama_model": OLLAMA_MODEL,
        "newsapi_enabled": bool(NEWSAPI_KEY),
        "pdf_path": PDF_PATH,
        "log_level": LOG_LEVEL,
        "redis_cache_enabled": USE_REDIS_CACHE,
        "redis_cache_timeout": REDIS_CACHE_TIMEOUT,
        "redis_embedding_ttl": REDIS_EMBEDDING_CACHE_TTL,
    }


if __name__ == "__main__":
    # Quick diagnostics when run as script
    import json
    print("FinTrace Configuration Summary:")
    print(json.dumps(get_config_summary(), indent=2))
