"""
Embedding Cache Service
=======================
High-level service for caching and retrieving embeddings in the PDF → chunk → embedding pipeline.

Provides:
- Automatic caching of generated embeddings
- Retrieval with cache hit/miss tracking
- Batch operations for efficient bulk caching
- TTL-based expiration for stale embeddings

Usage:
    from core.services.embedding_cache import cache_chunk_embedding, get_chunk_embedding

    # After generating embeddings from LLM
    embedding = llm.embed_query("text content")
    cache_chunk_embedding("pdf_123", "chunk_456", embedding)

    # Next time, retrieve from cache
    cached = get_chunk_embedding("pdf_123", "chunk_456")
    if cached:
        embedding = cached  # Use cached embedding
        logger.info("Cache hit!")
    else:
        embedding = llm.embed_query("text content")  # Generate new
"""

import logging
import hashlib
from typing import List, Optional, Dict, Tuple
from datetime import datetime

from core.services.redis_client import (
    cache_embedding,
    get_cached_embedding,
    cache_embeddings_batch,
    get_embeddings_batch,
    cache_data,
    get_cached_data,
    delete_cache_key,
    delete_cache_pattern,
    check_redis_health,
)
from core.config import USE_REDIS_CACHE, REDIS_EMBEDDING_CACHE_TTL

logger = logging.getLogger(__name__)


class EmbeddingCacheStats:
    """Track embedding cache statistics."""
    
    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.writes = 0
        self.errors = 0
    
    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate percentage."""
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0
    
    def __repr__(self) -> str:
        return (
            f"CacheStats(hits={self.hits}, misses={self.misses}, "
            f"writes={self.writes}, hit_rate={self.hit_rate:.1f}%)"
        )


# Global cache statistics
_cache_stats = EmbeddingCacheStats()


def _make_cache_key(pdf_id: str, chunk_id: str) -> str:
    """
    Generate cache key for a chunk.
    
    Args:
        pdf_id: Document/PDF identifier
        chunk_id: Chunk identifier within PDF
    
    Returns:
        Cache key string
    """
    return f"embedding:pdf:{pdf_id}:chunk:{chunk_id}"


def _make_stats_key(pdf_id: str) -> str:
    """Generate cache key for PDF processing statistics."""
    return f"cache_stats:pdf:{pdf_id}"


def cache_chunk_embedding(
    pdf_id: str,
    chunk_id: str,
    embedding: List[float],
    metadata: Optional[Dict] = None,
    ttl: Optional[int] = None,
) -> bool:
    """
    Cache an embedding for a PDF chunk.
    
    Args:
        pdf_id: Document/PDF identifier (e.g., "pdf_123" or document hash)
        chunk_id: Chunk identifier within document (e.g., "chunk_456")
        embedding: Embedding vector from LLM
        metadata: Optional metadata (chunk text, position, etc.)
        ttl: Custom TTL in seconds (uses default if None)
    
    Returns:
        True if cached successfully
    
    Example:
        >>> chunk_text = "Supply chain disruption occurred..."
        >>> embedding = ollama_llm.embed_query(chunk_text)
        >>> cache_chunk_embedding("pdf_supply_chain", "chunk_5", embedding)
        True
    """
    if not USE_REDIS_CACHE:
        return False
    
    try:
        cache_key = _make_cache_key(pdf_id, chunk_id)
        ttl = ttl or REDIS_EMBEDDING_CACHE_TTL
        
        # Cache the embedding
        success = cache_embedding(cache_key, embedding, ttl=ttl)
        
        if success:
            _cache_stats.writes += 1
            logger.debug(f"Cached embedding for {pdf_id}/{chunk_id}")
            
            # Cache metadata if provided
            if metadata:
                try:
                    meta_key = _make_meta_key(pdf_id, chunk_id)
                    cache_data(meta_key, metadata, ttl=ttl)
                except Exception as e:
                    logger.warning(f"Failed to cache metadata: {e}")
        
        return success
    
    except Exception as e:
        _cache_stats.errors += 1
        logger.error(f"Error caching embedding: {e}")
        return False


def get_chunk_embedding(pdf_id: str, chunk_id: str) -> Optional[List[float]]:
    """
    Retrieve cached embedding for a PDF chunk.
    
    Args:
        pdf_id: Document/PDF identifier
        chunk_id: Chunk identifier
    
    Returns:
        Embedding vector if cached, None if not found or cache disabled
    
    Example:
        >>> embedding = get_chunk_embedding("pdf_supply_chain", "chunk_5")
        >>> if embedding:
        ...     print("Cache hit!")
        ... else:
        ...     print("Cache miss - generate new embedding")
    """
    if not USE_REDIS_CACHE:
        return None
    
    try:
        cache_key = _make_cache_key(pdf_id, chunk_id)
        embedding = get_cached_embedding(cache_key)
        
        if embedding is not None:
            _cache_stats.hits += 1
            logger.debug(f"Cache HIT for {pdf_id}/{chunk_id}")
        else:
            _cache_stats.misses += 1
            logger.debug(f"Cache MISS for {pdf_id}/{chunk_id}")
        
        return embedding
    
    except Exception as e:
        _cache_stats.errors += 1
        logger.warning(f"Error retrieving cached embedding: {e}")
        return None


def get_chunk_metadata(pdf_id: str, chunk_id: str) -> Optional[Dict]:
    """Retrieve metadata associated with a cached embedding."""
    if not USE_REDIS_CACHE:
        return None
    
    try:
        meta_key = _make_meta_key(pdf_id, chunk_id)
        return get_cached_data(meta_key)
    except Exception as e:
        logger.warning(f"Error retrieving metadata: {e}")
        return None


def cache_chunk_embeddings_batch(
    pdf_id: str,
    chunk_embeddings: Dict[str, List[float]],
    ttl: Optional[int] = None,
) -> Tuple[int, int]:
    """
    Cache multiple chunk embeddings efficiently (batch operation).
    
    Args:
        pdf_id: Document/PDF identifier
        chunk_embeddings: Dict mapping chunk_id → embedding vector
        ttl: Custom TTL in seconds
    
    Returns:
        Tuple of (successful_count, total_count)
    
    Example:
        >>> embeddings = {
        ...     "chunk_1": [0.1, 0.2, ...],
        ...     "chunk_2": [0.3, 0.4, ...],
        ... }
        >>> cached, total = cache_chunk_embeddings_batch("pdf_123", embeddings)
        >>> print(f"Cached {cached}/{total} embeddings")
    """
    if not USE_REDIS_CACHE or not chunk_embeddings:
        return 0, len(chunk_embeddings)
    
    try:
        # Build cache keys
        cache_dict = {
            _make_cache_key(pdf_id, chunk_id): embedding
            for chunk_id, embedding in chunk_embeddings.items()
        }
        
        ttl = ttl or REDIS_EMBEDDING_CACHE_TTL
        count = cache_embeddings_batch(cache_dict, ttl=ttl)
        _cache_stats.writes += count
        
        logger.info(f"Batch cached {count}/{len(chunk_embeddings)} embeddings for {pdf_id}")
        return count, len(chunk_embeddings)
    
    except Exception as e:
        _cache_stats.errors += 1
        logger.error(f"Batch cache error: {e}")
        return 0, len(chunk_embeddings)


def get_chunk_embeddings_batch(
    pdf_id: str,
    chunk_ids: List[str],
) -> Dict[str, List[float]]:
    """
    Retrieve multiple cached embeddings efficiently.
    
    Args:
        pdf_id: Document/PDF identifier
        chunk_ids: List of chunk identifiers
    
    Returns:
        Dict mapping found chunk_ids to embeddings
    
    Example:
        >>> chunk_ids = ["chunk_1", "chunk_2", "chunk_3"]
        >>> cached = get_chunk_embeddings_batch("pdf_123", chunk_ids)
        >>> print(f"Found {len(cached)}/{len(chunk_ids)} embeddings in cache")
    """
    if not USE_REDIS_CACHE or not chunk_ids:
        return {}
    
    try:
        cache_keys = [_make_cache_key(pdf_id, cid) for cid in chunk_ids]
        embeddings_dict = get_embeddings_batch(cache_keys)
        
        # Re-map to chunk_id keys
        result = {}
        for key, embedding in embeddings_dict.items():
            parts = key.split(":")
            if len(parts) >= 4 and parts[0] == "pdf" and parts[1] == pdf_id:
                result[parts[3]] = embedding
        
        # Update stats
        hits = len(result)
        misses = len(chunk_ids) - hits
        _cache_stats.hits += hits
        _cache_stats.misses += misses
        
        logger.debug(f"Batch retrieved {hits}/{len(chunk_ids)} cached embeddings for {pdf_id}")
        return result
    
    except Exception as e:
        _cache_stats.errors += 1
        logger.warning(f"Batch retrieval error: {e}")
        return {}


def invalidate_pdf_cache(pdf_id: str) -> int:
    """
    Invalidate all cached embeddings for a PDF.
    
    Args:
        pdf_id: Document/PDF identifier
    
    Returns:
        Number of cache entries deleted
    
    Example:
        >>> deleted = invalidate_pdf_cache("pdf_123")
        >>> print(f"Invalidated {deleted} cache entries")
    """
    if not USE_REDIS_CACHE:
        return 0
    
    try:
        pattern = f"embedding:pdf:{pdf_id}:*"
        count = delete_cache_pattern(pattern)
        
        # Also delete metadata pattern
        meta_pattern = f"metadata:pdf:{pdf_id}:*"
        count += delete_cache_pattern(meta_pattern)
        
        # Delete stats
        stats_key = _make_stats_key(pdf_id)
        if delete_cache_key(stats_key):
            count += 1
        
        logger.info(f"Invalidated {count} cache entries for PDF {pdf_id}")
        return count
    
    except Exception as e:
        logger.warning(f"Error invalidating PDF cache: {e}")
        return 0


def get_cache_stats() -> EmbeddingCacheStats:
    """Get current cache statistics."""
    return _cache_stats


def reset_cache_stats() -> None:
    """Reset cache statistics."""
    global _cache_stats
    _cache_stats = EmbeddingCacheStats()
    logger.info("Cache statistics reset")


def cache_status_summary() -> Dict:
    """Get summary of cache status and statistics."""
    healthy, msg = check_redis_health()
    
    return {
        "redis_healthy": healthy,
        "redis_status": msg,
        "cache_enabled": USE_REDIS_CACHE,
        "ttl_seconds": REDIS_EMBEDDING_CACHE_TTL,
        "stats": {
            "hits": _cache_stats.hits,
            "misses": _cache_stats.misses,
            "writes": _cache_stats.writes,
            "errors": _cache_stats.errors,
            "hit_rate_percent": _cache_stats.hit_rate,
        },
    }


if __name__ == "__main__":
    # Quick test when run as script
    import logging
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    print("\n📊 Embedding Cache Service Status\n")
    
    summary = cache_status_summary()
    import json
    print(json.dumps(summary, indent=2))
