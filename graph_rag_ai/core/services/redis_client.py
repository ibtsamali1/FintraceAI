"""
Redis Client Service
====================
Centralized Redis connection management for caching, task queuing, and sessions.

Provides:
- Thread-safe connection pooling
- Automatic reconnection on failure
- Convenient methods for caching embeddings and intermediate results
- JSON serialization for complex objects

Usage:
    from core.services.redis_client import get_redis, cache_embedding, get_cached_embedding

    # Direct Redis access
    redis_client = get_redis()
    redis_client.set("key", "value", ex=3600)

    # Embedding caching
    cache_embedding("chunk_id", embedding_vector, ttl=86400)
    embedding = get_cached_embedding("chunk_id")

    # Batch operations
    with get_redis() as r:
        r.mset({"key1": "val1", "key2": "val2"})
"""

import json
import logging
from typing import Any, Optional, List, Dict
from contextlib import contextmanager

import redis
from redis.connection import ConnectionPool
from redis.exceptions import RedisError, ConnectionError

from core.config import REDIS_URL, REDIS_CACHE_TIMEOUT, REDIS_EMBEDDING_CACHE_TTL, USE_REDIS_CACHE

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────
# Global Redis connection pool (singleton)
# ─────────────────────────────────────────────────────────────────────────
_connection_pool: Optional[ConnectionPool] = None
_redis_client: Optional[redis.Redis] = None


def _init_redis_pool() -> ConnectionPool:
    """Initialize Redis connection pool (lazy singleton pattern)."""
    global _connection_pool
    
    if _connection_pool is None:
        try:
            logger.info(f"Initializing Redis connection pool: {REDIS_URL}")
            _connection_pool = redis.ConnectionPool.from_url(
                REDIS_URL,
                decode_responses=True,  # Automatically decode bytes to strings
                max_connections=20,
                socket_keepalive=True,
                socket_keepalive_options={
                    1: 1,  # TCP_KEEPIDLE
                    2: 1,  # TCP_KEEPINTVL
                    3: 3,  # TCP_KEEPCNT
                },
                retry_on_timeout=True,
                health_check_interval=30,
            )
            logger.info("✓ Redis connection pool initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Redis pool: {e}")
            raise
    
    return _connection_pool


def get_redis() -> redis.Redis:
    """
    Get thread-safe Redis client with connection pooling.
    
    Returns:
        redis.Redis: Connected Redis client
        
    Raises:
        ConnectionError: If unable to connect to Redis
    """
    global _redis_client
    
    if _redis_client is None:
        pool = _init_redis_pool()
        _redis_client = redis.Redis(connection_pool=pool)
        
        # Test connection
        try:
            _redis_client.ping()
            logger.info("✓ Redis connection verified")
        except RedisError as e:
            logger.error(f"Redis connection failed: {e}")
            raise
    
    return _redis_client


def reset_redis() -> None:
    """Reset Redis connection (useful for testing)."""
    global _redis_client, _connection_pool
    
    if _redis_client is not None:
        try:
            _redis_client.close()
        except Exception as e:
            logger.warning(f"Error closing Redis connection: {e}")
    
    if _connection_pool is not None:
        try:
            _connection_pool.disconnect()
        except Exception as e:
            logger.warning(f"Error disconnecting pool: {e}")
    
    _redis_client = None
    _connection_pool = None
    logger.info("Redis connections reset")


# ─────────────────────────────────────────────────────────────────────────
# Embedding Cache Functions
# ─────────────────────────────────────────────────────────────────────────

def cache_embedding(
    key: str,
    embedding: List[float],
    ttl: Optional[int] = None,
) -> bool:
    """
    Cache an embedding vector in Redis.
    
    Args:
        key: Unique identifier for the chunk/embedding (e.g., "chunk_123")
        embedding: Vector of floats (embedding)
        ttl: Time-to-live in seconds (uses REDIS_EMBEDDING_CACHE_TTL if None)
    
    Returns:
        True if cached successfully, False otherwise
    """
    if not USE_REDIS_CACHE:
        return False
    
    try:
        r = get_redis()
        ttl = ttl or REDIS_EMBEDDING_CACHE_TTL
        
        # Store embedding as JSON
        embedding_json = json.dumps(embedding)
        result = r.setex(
            f"embedding:{key}",
            ttl,
            embedding_json,
        )
        
        logger.debug(f"Cached embedding for {key} (TTL: {ttl}s)")
        return bool(result)
    
    except RedisError as e:
        logger.warning(f"Failed to cache embedding {key}: {e}")
        return False


def get_cached_embedding(key: str) -> Optional[List[float]]:
    """
    Retrieve a cached embedding from Redis.
    
    Args:
        key: Embedding key (e.g., "chunk_123")
    
    Returns:
        List of floats if found, None otherwise
    """
    if not USE_REDIS_CACHE:
        return None
    
    try:
        r = get_redis()
        value = r.get(f"embedding:{key}")
        
        if value is None:
            return None
        
        embedding = json.loads(value)
        logger.debug(f"Retrieved cached embedding for {key}")
        return embedding
    
    except (RedisError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to retrieve embedding {key}: {e}")
        return None


def cache_embeddings_batch(
    embeddings: Dict[str, List[float]],
    ttl: Optional[int] = None,
) -> int:
    """
    Cache multiple embeddings in a single operation (more efficient).
    
    Args:
        embeddings: Dict mapping keys to embedding vectors
        ttl: Time-to-live in seconds
    
    Returns:
        Number of embeddings successfully cached
    """
    if not USE_REDIS_CACHE or not embeddings:
        return 0
    
    try:
        r = get_redis()
        ttl = ttl or REDIS_EMBEDDING_CACHE_TTL
        
        # Use pipeline for atomic operations
        pipe = r.pipeline()
        for key, embedding in embeddings.items():
            embedding_json = json.dumps(embedding)
            pipe.setex(f"embedding:{key}", ttl, embedding_json)
        
        results = pipe.execute()
        count = sum(1 for r in results if r)
        
        logger.debug(f"Batch cached {count}/{len(embeddings)} embeddings (TTL: {ttl}s)")
        return count
    
    except RedisError as e:
        logger.warning(f"Batch cache failed: {e}")
        return 0


def get_embeddings_batch(keys: List[str]) -> Dict[str, List[float]]:
    """
    Retrieve multiple embeddings from cache.
    
    Args:
        keys: List of embedding keys
    
    Returns:
        Dict mapping found keys to their embeddings
    """
    if not USE_REDIS_CACHE or not keys:
        return {}
    
    try:
        r = get_redis()
        redis_keys = [f"embedding:{k}" for k in keys]
        values = r.mget(redis_keys)
        
        embeddings = {}
        for key, value in zip(keys, values):
            if value is not None:
                embeddings[key] = json.loads(value)
        
        logger.debug(f"Retrieved {len(embeddings)}/{len(keys)} cached embeddings")
        return embeddings
    
    except (RedisError, json.JSONDecodeError) as e:
        logger.warning(f"Batch retrieval failed: {e}")
        return {}


# ─────────────────────────────────────────────────────────────────────────
# Generic Cache Functions
# ─────────────────────────────────────────────────────────────────────────

def cache_data(
    key: str,
    data: Any,
    ttl: Optional[int] = None,
) -> bool:
    """
    Cache any JSON-serializable data.
    
    Args:
        key: Cache key
        data: Data to cache (must be JSON-serializable)
        ttl: Time-to-live in seconds (uses REDIS_CACHE_TIMEOUT if None)
    
    Returns:
        True if cached successfully
    """
    if not USE_REDIS_CACHE:
        return False
    
    try:
        r = get_redis()
        ttl = ttl or REDIS_CACHE_TIMEOUT
        
        data_json = json.dumps(data)
        r.setex(key, ttl, data_json)
        
        logger.debug(f"Cached data for {key}")
        return True
    
    except (RedisError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to cache data {key}: {e}")
        return False


def get_cached_data(key: str) -> Optional[Any]:
    """
    Retrieve cached data from Redis.
    
    Args:
        key: Cache key
    
    Returns:
        Cached data if found, None otherwise
    """
    if not USE_REDIS_CACHE:
        return None
    
    try:
        r = get_redis()
        value = r.get(key)
        
        if value is None:
            return None
        
        data = json.loads(value)
        logger.debug(f"Retrieved cached data for {key}")
        return data
    
    except (RedisError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to retrieve cached data {key}: {e}")
        return None


def delete_cache_key(key: str) -> bool:
    """Delete a single cache key."""
    try:
        r = get_redis()
        result = r.delete(key)
        return bool(result)
    except RedisError as e:
        logger.warning(f"Failed to delete cache key {key}: {e}")
        return False


def delete_cache_pattern(pattern: str) -> int:
    """
    Delete all keys matching a pattern.
    
    Args:
        pattern: Pattern to match (e.g., "embedding:*", "chunk_*")
    
    Returns:
        Number of keys deleted
    """
    try:
        r = get_redis()
        keys = r.keys(pattern)
        
        if not keys:
            return 0
        
        return r.delete(*keys)
    
    except RedisError as e:
        logger.warning(f"Failed to delete cache pattern {pattern}: {e}")
        return 0


def clear_all_cache() -> bool:
    """Clear all cached data (use carefully!)."""
    try:
        r = get_redis()
        r.flushdb()
        logger.warning("All cache data cleared")
        return True
    except RedisError as e:
        logger.error(f"Failed to clear cache: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────────────────────────────────

def check_redis_health() -> tuple[bool, str]:
    """
    Check Redis connection and basic functionality.
    
    Returns:
        Tuple of (is_healthy, message)
    """
    try:
        r = get_redis()
        
        # Test ping
        r.ping()
        
        # Get basic info
        info = r.info("stats")
        total_connections = info.get("total_connections_received", 0)
        
        message = f"✓ Redis healthy (total connections: {total_connections})"
        return True, message
    
    except Exception as e:
        message = f"✗ Redis unavailable: {e}"
        return False, message


if __name__ == "__main__":
    # Quick test when run as script
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    print("\n🔌 Redis Service Health Check\n")
    healthy, msg = check_redis_health()
    print(msg)
    
    if healthy:
        print("\n✓ Redis is ready for use!")
        sys.exit(0)
    else:
        print("\n✗ Redis connection failed")
        sys.exit(1)
