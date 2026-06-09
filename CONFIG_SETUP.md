# Configuration Management Setup Guide

## Overview

This project now uses **`python-decouple`** for centralized environment-based configuration management. All sensitive values (API keys, database credentials, secrets) are loaded from a `.env` file and should **never** be hardcoded in the source code.

## Key Changes

### 1. **New Configuration Module**
- **File**: [core/config.py](core/config.py)
- Single source of truth for all environment variables
- Provides type-safe access via `decouple`
- Built-in validation for required credentials

### 2. **Updated Files**
All files now import from `core.config` instead of using `os.getenv()`:
- [graph_rag_ai/settings.py](graph_rag_ai/settings.py) - Django config
- [core/services/llm.py](core/services/llm.py) - Ollama LLM config
- [core/services/news_parser.py](core/services/news_parser.py) - NewsAPI config
- [core/pdf_ingestion.py](core/pdf_ingestion.py) - PDF processing config
- [core/views.py](core/views.py) - Health check endpoints

### 3. **Removed Hardcoded Values**
- ✅ Removed NewsAPI key from code
- ✅ Removed PDF path hardcoding
- ✅ Removed Ollama URL hardcoding
- ✅ Removed Django SECRET_KEY insecure default

## Setup Instructions

### Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

This installs `python-decouple>=3.8` (and `python-dotenv>=1.0`).

### Step 2: Create .env File

**Option A: Copy from template**
```bash
cp graph_rag_ai/.env.example graph_rag_ai/.env
```

**Option B: Create manually**
```bash
cd graph_rag_ai
cat > .env << 'EOF'
# Django
DJANGO_SECRET_KEY=your-random-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Neo4j
NEO4J_URI=neo4j+s://your-aura-id.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password-here

# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2

# NewsAPI (optional)
NEWSAPI_KEY=your-key-here

# PDF Processing
PDF_PATH=pdf/document.pdf
PDF_CHUNK_SIZE=600
PDF_CHUNK_OVERLAP=90
PDF_BATCH_SIZE=5

# Logging
LOG_LEVEL=INFO
EOF
```

### Step 3: Generate a Secure Django Secret Key

For production, generate a new random secret key:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Replace the `DJANGO_SECRET_KEY` value in your `.env` file.

### Step 4: Verify Setup

Check that all required variables are set:

```bash
python manage.py shell
>>> from core.config import get_config_summary
>>> import json
>>> print(json.dumps(get_config_summary(), indent=2))
```

Or run the config module directly:

```bash
python core/config.py
```

## Environment Variables Reference

### CRITICAL (Required for App to Start)

| Variable | Description | Example |
|----------|-------------|---------|
| `DJANGO_SECRET_KEY` | Django session/CSRF key | `django-insecure-abc123...` |
| `NEO4J_URI` | Neo4j connection URI | `neo4j+s://instance.databases.neo4j.io` |
| `NEO4J_USER` | Neo4j username | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j password | `secure-password-here` |

### IMPORTANT (Strongly Recommended)

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `DEBUG` | Enable debug mode | `True` | `False` (for production) |
| `ALLOWED_HOSTS` | Allowed hostnames | `localhost,127.0.0.1` | `example.com,www.example.com` |
| `OLLAMA_BASE_URL` | Ollama server URL | `http://localhost:11434` | (same) |
| `OLLAMA_MODEL` | LLM model to use | `llama3.2` | `mistral`, `llama2` |

### OPTIONAL

| Variable | Description | Default |
|----------|-------------|---------|
| `NEWSAPI_KEY` | NewsAPI key (news ingestion) | (empty) |
| `PDF_PATH` | Path to PDF for ingestion | `pdf/document.pdf` |
| `PDF_CHUNK_SIZE` | Text chunk size | `600` |
| `PDF_CHUNK_OVERLAP` | Chunk overlap | `90` |
| `PDF_BATCH_SIZE` | Parallel batch size | `5` |
| `LOG_LEVEL` | Logging verbosity | `INFO` |

## Usage Examples

### In Django Code

```python
from core.config import DJANGO_SECRET_KEY, NEO4J_URI, OLLAMA_MODEL

# Use in settings
SECRET_KEY = DJANGO_SECRET_KEY

# Use in services
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
llm = ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL)
```

### Standalone Scripts

```python
# In pdf_ingestion.py or management commands
from core.config import PDF_PATH, PDF_CHUNK_SIZE, OLLAMA_BASE_URL

loader = PyPDFLoader(PDF_PATH)
splitter = RecursiveCharacterTextSplitter(chunk_size=PDF_CHUNK_SIZE)
```

### Testing/Mocking

For unit tests, you can override environment variables:

```python
import os
from core.config import OLLAMA_BASE_URL

# Test with mock
os.environ['OLLAMA_BASE_URL'] = 'http://test-ollama:11434'
# Note: You may need to reload the config module or clear cache
```

## Security Best Practices

### ✅ DO

- ✅ Store real API keys only in `.env` (never commit)
- ✅ Use `.env.example` as template with placeholder values
- ✅ Generate new `DJANGO_SECRET_KEY` for production
- ✅ Use strong passwords for Neo4j
- ✅ Add `.env` to `.gitignore` (already configured)
- ✅ Use environment-specific values per deployment
- ✅ Rotate API keys periodically

### ❌ DON'T

- ❌ Commit `.env` files to git
- ❌ Use default values for production secrets
- ❌ Share `.env` files unencrypted
- ❌ Hardcode API keys in source code
- ❌ Use weak/default passwords
- ❌ Print secrets to logs

## Deployment

### Docker

Build `.env` file into container during deployment:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
# Copy environment at build time from secure source
COPY .env .env
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
```

Or use Docker secrets/environment variables:

```bash
docker run -e DJANGO_SECRET_KEY="..." -e NEO4J_PASSWORD="..." ...
```

### Heroku / Railway / Platform.as.a.Service

Set environment variables via platform dashboard:

```
DJANGO_SECRET_KEY=your-random-key
NEO4J_URI=neo4j+s://...
NEO4J_USER=neo4j
NEO4J_PASSWORD=...
```

### AWS / Azure / GCP

Use managed secrets services:
- AWS Secrets Manager
- Azure Key Vault
- Google Secret Manager

Configure app to fetch at startup:

```python
import boto3
sm = boto3.client('secretsmanager')
secret = sm.get_secret_value(SecretId='fintrack/prod')
```

## Troubleshooting

### Error: "Neo4j configuration incomplete"

**Problem**: `NEO4J_URI`, `NEO4J_USER`, or `NEO4J_PASSWORD` not set.

**Solution**:
```bash
# Check .env file exists and has values
cat graph_rag_ai/.env

# Or set environment variables
export NEO4J_URI="neo4j+s://..."
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="..."
python manage.py runserver
```

### Error: "Could not reach Ollama at..."

**Problem**: Ollama not running or wrong URL.

**Solution**:
```bash
# Start Ollama
ollama serve

# In another terminal, verify connectivity
curl http://localhost:11434/api/tags

# Check .env
cat graph_rag_ai/.env | grep OLLAMA
```

### Error: "NEWSAPI_KEY not set"

**Problem**: NewsAPI disabled (optional feature).

**Solution**: Optional. To enable news ingestion:
1. Get free key at https://newsapi.org
2. Add to `.env`: `NEWSAPI_KEY=your-key-here`

### Settings not updating after .env change

**Problem**: Django caches configuration.

**Solution**: Restart the Django development server:
```bash
python manage.py runserver
```

## Migration Checklist

- [x] Install `python-decouple` in requirements.txt
- [x] Create `core/config.py` module
- [x] Update `settings.py` to use config
- [x] Update `llm.py` to use config
- [x] Update `news_parser.py` to use config
- [x] Update `pdf_ingestion.py` to use config
- [x] Update `views.py` to use config
- [x] Remove hardcoded API keys from codebase
- [x] Create comprehensive `.env.example`
- [x] Document setup in this guide

## Related Files

- [core/config.py](core/config.py) - Configuration module
- [graph_rag_ai/settings.py](graph_rag_ai/settings.py) - Django settings
- [.env.example](.env.example) - Configuration template
- [graph_rag_ai/.env.example](graph_rag_ai/.env.example) - Project-level template
- [requirements.txt](requirements.txt) - Python dependencies

## Next Steps

1. Copy `.env.example` to `.env` and fill in your values
2. Run migrations: `python manage.py migrate`
3. Start Ollama: `ollama serve`
4. Test setup: `python core/config.py`
5. Run Django: `python manage.py runserver`

For questions or issues, see [SETUP.md](SETUP.md) or project documentation.
