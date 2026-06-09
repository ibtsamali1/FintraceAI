# Configuration Quick Reference

## Using Config in Your Code

### Import Pattern
```python
from core.config import VARIABLE_NAME

# Example
from core.config import (
    DJANGO_SECRET_KEY,
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_PASSWORD,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    NEWSAPI_KEY,
    PDF_PATH,
    PDF_CHUNK_SIZE,
)
```

## Common Usage Examples

### Django Settings
```python
from core.config import DJANGO_SECRET_KEY, DEBUG, ALLOWED_HOSTS

SECRET_KEY = DJANGO_SECRET_KEY
DEBUG = DEBUG
ALLOWED_HOSTS = ALLOWED_HOSTS
```

### Neo4j Connection
```python
from core.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
from neo4j import GraphDatabase

driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USER, NEO4J_PASSWORD)
)
```

### Ollama LLM
```python
from core.config import OLLAMA_BASE_URL, OLLAMA_MODEL
from langchain_ollama import ChatOllama

llm = ChatOllama(
    base_url=OLLAMA_BASE_URL,
    model=OLLAMA_MODEL
)
```

### NewsAPI
```python
from core.config import NEWSAPI_KEY, NEWSAPI_BASE_URL
import requests

if NEWSAPI_KEY:
    response = requests.get(
        NEWSAPI_BASE_URL,
        params={"apiKey": NEWSAPI_KEY, "q": "supply chain"}
    )
```

### PDF Processing
```python
from core.config import PDF_PATH, PDF_CHUNK_SIZE, PDF_CHUNK_OVERLAP, PDF_BATCH_SIZE
from langchain_community.document_loaders import PyPDFLoader

loader = PyPDFLoader(PDF_PATH)
splitter = RecursiveCharacterTextSplitter(
    chunk_size=PDF_CHUNK_SIZE,
    chunk_overlap=PDF_CHUNK_OVERLAP,
)
```

## .env File Location

```
graph_rag_ai/.env  ← This is where your configuration goes
graph_rag_ai/.env.example  ← Template with placeholders
```

## Essential .env Variables

```bash
# MUST HAVE (app won't start without these)
DJANGO_SECRET_KEY=your-random-secret-key
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password

# RECOMMENDED
DEBUG=True  (False for production)
ALLOWED_HOSTS=localhost,127.0.0.1
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2

# OPTIONAL
NEWSAPI_KEY=your-api-key
PDF_PATH=pdf/document.pdf
PDF_CHUNK_SIZE=600
PDF_CHUNK_OVERLAP=90
PDF_BATCH_SIZE=5
LOG_LEVEL=INFO
```

## Common Tasks

### Debug: Check Current Configuration
```bash
python core/config.py
```

Or in Django shell:
```python
from core.config import get_config_summary
import json
print(json.dumps(get_config_summary(), indent=2))
```

### Generate New Django Secret Key
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### Setup Fresh Environment
```bash
cp graph_rag_ai/.env.example graph_rag_ai/.env
# Edit .env with your values
python manage.py runserver
```

### Test Neo4j Connection
```python
from core.services.neo4j_connection import get_session

with get_session() as session:
    result = session.run("RETURN 'Connected!' as msg")
    print(result.single())
```

### Test Ollama Connection
```python
from core.services.llm import get_extraction_llm

llm = get_extraction_llm()
# Check logs for "Ollama reachable at..."
```

## Troubleshooting

### "Neo4j configuration incomplete"
```bash
# Check .env has all three values
grep NEO4J graph_rag_ai/.env

# Or set environment variables
export NEO4J_URI="neo4j+s://..."
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="..."
```

### "Could not reach Ollama"
```bash
# Make sure Ollama is running
ollama serve

# Check connectivity
curl http://localhost:11434/api/tags

# Verify .env setting
grep OLLAMA graph_rag_ai/.env
```

### Settings not updating
```bash
# Restart Django (development server caches config)
python manage.py runserver
```

## Type Casting

Config automatically handles type conversion:

```python
from core.config import DEBUG, PDF_CHUNK_SIZE, GRAPH_DEPTH_LIMIT

print(type(DEBUG))  # <class 'bool'>
print(type(PDF_CHUNK_SIZE))  # <class 'int'>
print(type(GRAPH_DEPTH_LIMIT))  # <class 'int'>
```

## Security Reminders

- ✅ Never commit `.env` to git
- ✅ Use `.env.example` only for templates
- ✅ Rotate API keys periodically
- ✅ Use strong passwords for production
- ✅ Generate new Django SECRET_KEY per environment
- ✅ Use environment-specific values

## File Locations

```
d:/graphRAG/
├── core/config.py                    ← Configuration module
├── graph_rag_ai/.env                 ← Your actual config (DON'T COMMIT)
├── graph_rag_ai/.env.example         ← Template with instructions
├── .env.example                      ← Root template
├── CONFIG_SETUP.md                   ← Detailed setup guide
├── CONFIGURATION_MIGRATION_SUMMARY.md ← Migration summary
└── CONFIG_QUICK_REFERENCE.md         ← This file
```

## Related Documentation

- [CONFIG_SETUP.md](CONFIG_SETUP.md) - Complete setup guide
- [CONFIGURATION_MIGRATION_SUMMARY.md](CONFIGURATION_MIGRATION_SUMMARY.md) - What changed
- [core/config.py](core/config.py) - Configuration source code
