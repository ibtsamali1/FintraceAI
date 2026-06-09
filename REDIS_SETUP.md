# Redis Integration Guide

## Overview

Redis has been integrated into the FinTrace project for caching and task queuing in the PDF → chunk → embedding pipeline. This guide covers setup, usage, and best practices.

## Key Features

### 1. **Embedding Caching**
- Cache LLM-generated embeddings from PDF chunks
- Reduces redundant LLM API calls
- Configurable TTL (24 hours by default)

### 2. **Intermediate Result Caching**
- Cache entity extraction results from batches
- Cache graph query results
- General-purpose JSON caching

### 3. **Task Queuing** (Optional)
- Queue PDF ingestion tasks
- Distributed task processing with Celery
- Background job execution

### 4. **Session Management**
- Optional Django session storage in Redis
- Faster session access than database

---

## Installation & Setup

### Step 1: Install Redis

**Windows (via WSL or Chocolatey)**
```bash
# Using Chocolatey
choco install redis

# Or use WSL
wsl apt-get install redis-server
```

**macOS**
```bash
brew install redis
```

**Linux (Ubuntu/Debian)**
```bash
sudo apt-get install redis-server
```

**Docker**
```bash
docker run -d -p 6379:6379 redis:latest
```

### Step 2: Verify Redis Installation

```bash
# Test Redis connection
redis-cli ping
# Expected output: PONG

# Check server info
redis-cli info
```

### Step 3: Install Python Dependencies

Already added to `requirements.txt`:
```bash
pip install -r requirements.txt
```

Installs:
- `redis>=5.0` - Python Redis client
- `celery>=5.3` - Task queue (optional)
- `django-redis>=5.4` - Django Redis integration (optional)

---

## Configuration

### Environment Variables

Set in `.env` file (auto-loaded via `core/config.py`):

```bash
# Redis connection URL
REDIS_URL=redis://localhost:6379/0

# Cache timeout (seconds, 1 hour)
REDIS_CACHE_TIMEOUT=3600

# Embedding cache TTL (seconds, 24 hours)
REDIS_EMBEDDING_CACHE_TTL=86400

# Enable/disable caching
USE_REDIS_CACHE=True
```

### REDIS_URL Format

```
redis://[password@]host:port/db
```

**Examples:**
```bash
# Local development
redis://localhost:6379/0

# With password
redis://user:password@localhost:6379/0

# Docker container
redis://redis:6379/0

# Remote Redis Cloud
redis://:password@redis-12345.c123.us-east-1-2.ec2.cloud.redislabs.com:12345/0
```

---

## Usage

### 1. Basic Redis Access

```python
from core.services.redis_client import get_redis

# Get Redis client
r = get_redis()

# Set a value
r.set("key", "value")

# Get a value
value = r.get("key")

# Set with expiration (60 seconds)
r.setex("temp_key", 60, "value")
```

### 2. Caching Embeddings

```python
from core.services.embedding_cache import (
    cache_chunk_embedding,
    get_chunk_embedding,
    cache_chunk_embeddings_batch,
)

# Cache single embedding
embedding = llm.embed_query("chunk text")
cache_chunk_embedding("pdf_123", "chunk_456", embedding)

# Retrieve embedding
cached = get_chunk_embedding("pdf_123", "chunk_456")
if cached:
    embedding = cached
else:
    embedding = llm.embed_query("chunk text")

# Batch operations (more efficient)
embeddings = {
    "chunk_1": [0.1, 0.2, ...],
    "chunk_2": [0.3, 0.4, ...],
}
cached_count, total = cache_chunk_embeddings_batch("pdf_123", embeddings)
```

### 3. PDF Ingestion with Caching

```bash
# Run with caching (default)
python core/pdf_ingestion.py --pdf /path/to/document.pdf

# Run with caching enabled (show cache hits)
python core/pdf_ingestion.py

# Clear cache and regenerate
python core/pdf_ingestion.py --skip-cache
```

**Output example:**
```
Processing 10 batches (instead of 50 chunks)

[Batch 1/10] chunks=5 chars=3000 → CACHE HIT → 12 nodes, 8 rels
[Batch 2/10] chunks=5 chars=3100 → 15 nodes, 10 rels
...
DONE - PDF Ingestion Pipeline Complete
  Nodes: 145
  Relationships: 89
  Cache hits: 5/10
  Total cache stats: {'hits': 5, 'misses': 5, 'writes': 5, 'errors': 0}
```

### 4. Check Cache Status

```python
from core.services.embedding_cache import cache_status_summary

status = cache_status_summary()
print(status)

# Output:
# {
#     "redis_healthy": True,
#     "redis_status": "✓ Redis healthy (total connections: 42)",
#     "cache_enabled": True,
#     "ttl_seconds": 86400,
#     "stats": {
#         "hits": 15,
#         "misses": 8,
#         "writes": 12,
#         "errors": 0,
#         "hit_rate_percent": 65.2
#     }
# }
```

### 5. Health Check Endpoint

Check all services including Redis:

```bash
curl http://localhost:8000/api/health/

# Output:
# {
#     "status": "ok",
#     "services": {
#         "neo4j": "ok",
#         "ollama": "ok",
#         "newsapi": "ok",
#         "redis": "ok"
#     }
# }
```

---

## Advanced Usage

### Generic Caching

```python
from core.services.redis_client import cache_data, get_cached_data

# Cache any JSON-serializable data
data = {"entities": ["Company A", "Port B"], "risk_level": "high"}
cache_data("query_result:123", data, ttl=3600)

# Retrieve data
result = get_cached_data("query_result:123")
```

### Cache Invalidation

```python
from core.services.embedding_cache import invalidate_pdf_cache
from core.services.redis_client import delete_cache_pattern, clear_all_cache

# Invalidate cache for specific PDF
deleted = invalidate_pdf_cache("pdf_123")
print(f"Deleted {deleted} cache entries")

# Delete by pattern
delete_cache_pattern("embedding:*")  # Clear all embeddings
delete_cache_pattern("extraction:*")  # Clear all extractions

# Clear entire cache (use carefully!)
clear_all_cache()
```

### Connection Management

```python
from core.services.redis_client import get_redis, reset_redis

# Get client
r = get_redis()

# Use client
r.ping()

# Reset connections (useful after errors or in tests)
reset_redis()

# Get fresh connection
r = get_redis()  # New connection created
```

---

## Monitoring & Debugging

### Check Redis Info

```bash
# Basic stats
redis-cli info stats

# Memory usage
redis-cli info memory

# Connected clients
redis-cli client list

# All keys
redis-cli keys "*"

# Cache size
redis-cli dbsize
```

### Python Debugging

```python
from core.services.redis_client import check_redis_health
from core.services.embedding_cache import cache_status_summary

# Check connection
healthy, msg = check_redis_health()
print(msg)

# Get full status
summary = cache_status_summary()
import json
print(json.dumps(summary, indent=2))
```

### Test Redis Connection

```bash
# Direct test
python core/services/redis_client.py

# Or via Django shell
python manage.py shell
>>> from core.services.redis_client import check_redis_health
>>> healthy, msg = check_redis_health()
>>> print(msg)
```

---

## Performance Tuning

### Adjust Cache TTLs

```bash
# In .env file

# Short TTL for frequently-changing data (1 hour)
REDIS_CACHE_TIMEOUT=3600

# Long TTL for embeddings (24 hours - won't change)
REDIS_EMBEDDING_CACHE_TTL=86400

# Very long TTL for rarely-changing data (7 days)
# Use directly in code: cache_data(key, data, ttl=604800)
```

### Connection Pooling

Automatically handled by `redis_client.py`:
- Max 20 concurrent connections
- TCP keepalive enabled
- Health checks every 30 seconds
- Automatic reconnection

### Batch Operations

Use batch functions for multiple items:

```python
# ❌ Slow - multiple round trips
for chunk_id, embedding in embeddings.items():
    cache_chunk_embedding(pdf_id, chunk_id, embedding)

# ✅ Fast - single operation
cache_chunk_embeddings_batch(pdf_id, embeddings)
```

### Monitor Memory Usage

```bash
# Check Redis memory
redis-cli info memory

# Set maximum memory limit (in redis.conf)
maxmemory 1gb
maxmemory-policy allkeys-lru  # Evict least-recently-used keys
```

---

## Troubleshooting

### "Redis connection failed"

**Problem**: `ConnectionError: [Errno 111] Connection refused`

**Solutions:**
1. Check Redis is running: `redis-cli ping`
2. Verify REDIS_URL in .env: `redis://localhost:6379/0`
3. Check firewall allows port 6379
4. Restart Redis: `redis-server` or `docker restart redis`

### "No space left on device"

**Problem**: `OSError: [Errno 28] No space left on device`

**Solutions:**
1. Check available disk: `df -h`
2. Clear old cache: `redis-cli flushdb`
3. Set memory limit in Redis config
4. Increase disk space

### Caching disabled silently

**Problem**: Cache appears to work but nothing is cached

**Solutions:**
1. Check `USE_REDIS_CACHE=True` in .env
2. Verify Redis connection: `python core/services/redis_client.py`
3. Check logs for errors
4. Ensure Redis is actually running

### Slow performance

**Problem**: App slower with Redis than without

**Solutions:**
1. Network latency - use local Redis or docker
2. Serialization overhead - use `decode_responses=True` (already configured)
3. TTL too short - increase `REDIS_CACHE_TIMEOUT`
4. Monitor with `redis-cli --stat`

---

## Deployment

### Docker Compose

```yaml
version: '3.8'

services:
  redis:
    image: redis:latest
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s

  web:
    image: fintrace:latest
    environment:
      REDIS_URL: redis://redis:6379/0
    depends_on:
      redis:
        condition: service_healthy
    ports:
      - "8000:8000"

volumes:
  redis_data:
```

**Start:**
```bash
docker-compose up
```

### AWS ElastiCache

```bash
# Example .env for AWS ElastiCache
REDIS_URL=redis://:password@my-redis.ng.0001.use1.cache.amazonaws.com:6379/0
```

### Redis Cloud

```bash
# Example .env for Redis Cloud
REDIS_URL=redis://:password@redis-12345.c123.us-east-1-2.ec2.cloud.redislabs.com:12345/0
```

---

## Best Practices

✅ **DO:**
- Use batch operations when caching multiple items
- Set appropriate TTLs for different data types
- Monitor cache hit rates
- Use Redis for read-heavy workloads
- Enable persistence (`appendonly yes`)
- Monitor memory usage

❌ **DON'T:**
- Store large blobs in cache (use files instead)
- Set TTL to 0 (use database for permanent data)
- Cache sensitive data without encryption
- Assume cache will never fail (always have fallback)
- Store millions of small keys (use hash instead)

---

## Files Modified

- [requirements.txt](../requirements.txt) - Added redis, celery, django-redis
- [core/config.py](../core/config.py) - Added Redis configuration
- [core/services/redis_client.py](../core/services/redis_client.py) - Redis connection management
- [core/services/embedding_cache.py](../core/services/embedding_cache.py) - Embedding cache service
- [core/pdf_ingestion.py](../core/pdf_ingestion.py) - Integrated Redis caching
- [core/views.py](../core/views.py) - Added Redis health check

---

## Next Steps

1. **Start Redis**: `redis-server` or use Docker
2. **Verify connection**: `python core/services/redis_client.py`
3. **Test caching**: `python core/pdf_ingestion.py`
4. **Monitor**: `redis-cli monitor` or `redis-cli --stat`
5. **Deploy**: Use Docker Compose or managed Redis service

---

## Reference

- [Redis Documentation](https://redis.io/documentation)
- [Redis Commands](https://redis.io/commands)
- [Python Redis Client](https://github.com/redis/redis-py)
- [Celery Task Queue](https://docs.celeryproject.org/)
- [Django Redis](https://github.com/jazzband/django-redis)
