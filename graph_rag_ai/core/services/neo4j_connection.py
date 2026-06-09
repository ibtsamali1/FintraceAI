"""
Neo4j Connection Manager
========================
Provides a reusable, thread-safe Neo4j driver singleton.

Configuration is managed via core.config module, which reads from .env file.

Usage:
    from core.services.neo4j_connection import get_driver, get_session

    # Option 1: get the driver directly
    driver = get_driver()

    # Option 2: use the session context manager (preferred)
    with get_session() as session:
        result = session.run("MATCH (n) RETURN n LIMIT 5")
"""

import logging
from contextlib import contextmanager

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError
from core.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — loaded from .env via core.config
# ---------------------------------------------------------------------------
# NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD are imported from core.config above
# These MUST be set in your .env file or environment

# Validate that credentials are set
if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
    raise ValueError(
        "Neo4j credentials not configured. Set NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD "
        "in your .env file."
    )

# ---------------------------------------------------------------------------
# Singleton driver instance
# ---------------------------------------------------------------------------
_driver = None


def get_driver():
    """
    Return a singleton Neo4j driver instance.

    The driver is created on first call and reused for all subsequent calls.
    This avoids opening/closing connections repeatedly and is the
    recommended pattern from the Neo4j Python driver documentation.
    
    Uses connection pooling to support concurrent access from multiple threads.
    """
    global _driver

    if _driver is not None:
        return _driver

    try:
        # Note: Encryption is handled by URI scheme (neo4j+s://)
        _driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
            max_connection_pool_size=50,  # Max connections in pool
            connection_timeout=30.0,      # 30 second connection timeout
        )
        # Verify connectivity on first creation
        _driver.verify_connectivity()
        logger.info("Neo4j driver connected to %s (pool_size=50)", NEO4J_URI)
    except AuthError:
        logger.error("Neo4j authentication failed — check NEO4J_USER / NEO4J_PASSWORD")
        raise
    except ServiceUnavailable:
        logger.error("Neo4j service unavailable at %s", NEO4J_URI)
        raise

    return _driver


@contextmanager
def get_session(**kwargs):
    """
    Context manager that yields a Neo4j session.

    Automatically closes the session when the block exits.
    Accepts the same keyword arguments as driver.session()
    (e.g., database="neo4j").

    Usage:
        with get_session() as session:
            result = session.run("MATCH (n) RETURN count(n) AS cnt")
            print(result.single()["cnt"])
    """
    driver = get_driver()
    session = driver.session(**kwargs)
    try:
        yield session
    finally:
        session.close()


def close_driver():
    """
    Explicitly close the singleton driver.

    Call this during application shutdown (e.g., in AppConfig.ready or
    an atexit handler) to release all pooled connections cleanly.
    """
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None
        logger.info("Neo4j driver closed")
