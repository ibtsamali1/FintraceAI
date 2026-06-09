# FinTrace — Agentic GraphRAG Supply Chain Monitor

A Django-based supply chain intelligence system that combines Neo4j knowledge graphs with LLM agents to detect and assess supply chain disruptions in real-time.

## Quick Start

### Prerequisites
- Python 3.9+
- Neo4j (Aura cloud or local instance)
- Ollama (for local LLM inference)
- NewsAPI key (optional, for news watcher)

### 1. Set Up Environment

```bash
# Clone/navigate to the project
cd graph_rag_ai

# Copy the example environment file
cp .env.example .env

# Edit .env with your configuration
# CRITICAL: Set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
nano .env
```

### 2. Install Dependencies

```bash
# Create a Python virtual environment (recommended)
python -m venv venv

# Activate it
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install Python packages
pip install -r requirements.txt
```

### 3. Set Up Ollama (Local LLM)

```bash
# Download Ollama from https://ollama.ai
# Start Ollama server in a separate terminal:
ollama serve

# In another terminal, pull the llama3.2 model:
ollama pull llama3.2
```

### 4. Initialize Django

```bash
# Run migrations
python manage.py migrate

# Create a superuser (for admin panel)
python manage.py createsuperuser

# Collect static files
python manage.py collectstatic --noinput
```

### 5. Verify Installation

```bash
# Run the health check command
python manage.py health_check

# You should see: ✅ All services healthy!
```

### 6. Start the Development Server

```bash
# In one terminal, start the Django dev server:
python manage.py runserver

# The app will be available at http://localhost:8000

# In another terminal (optional), start the news watcher scheduler:
python manage.py run_news_watcher --interval 60
```

## Usage

### Web Dashboard
- **URL**: http://localhost:8000/
- View uploaded documents, news events, and interact with the knowledge graph

### API Endpoints

#### Health Check
```bash
curl http://localhost:8000/health/
```

#### Upload PDF for Knowledge Graph Extraction
```bash
curl -X POST -F "files=@document.pdf" http://localhost:8000/api/upload/
```

#### Query Graph Nodes
```bash
curl http://localhost:8000/api/graph/node/?name=NordOil
```

#### Find Neighbors
```bash
curl "http://localhost:8000/api/graph/neighbors/?name=NordOil&direction=both&limit=50"
```

#### Find Shortest Path Between Entities
```bash
curl "http://localhost:8000/api/graph/path/?from=NordOil&to=Singapore"
```

#### Find Impacted Entities
```bash
curl "http://localhost:8000/api/graph/impacted/?name=NordOil&max_depth=5"
```

#### Risk Assessment Agent Query
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"question": "What would happen if NordOil shuts down?"}' \
  http://localhost:8000/api/query/
```

### Command Line Tools

#### Run PDF Ingestion Standalone
```bash
# Extract entities from a PDF and populate Neo4j
python core/pdf_ingestion.py
```

#### Scan News for Disruptions (Once)
```bash
python manage.py run_news_watcher --once
```

#### Scan News Periodically
```bash
# Scans every 60 minutes (configurable with --interval)
python manage.py run_news_watcher --interval 60
```

#### Health Check
```bash
python manage.py health_check
```

## Project Structure

```
graph_rag_ai/
├── core/                          # Main Django app
│   ├── agent/                     # LangGraph risk assessment nodes
│   │   ├── graph.py              # Workflow orchestration
│   │   ├── nodes.py              # Node implementations
│   │   └── state.py              # State definition
│   ├── services/                 # Reusable service layer
│   │   ├── neo4j_connection.py   # Neo4j driver singleton
│   │   ├── graph_builder.py      # Entity extraction & ingestion
│   │   ├── graph_query.py        # Query engine
│   │   ├── llm.py                # Ollama factory
│   │   └── news_parser.py        # News fetching & parsing
│   ├── tasks/                    # Background tasks
│   │   ├── ingestion.py          # PDF processing
│   │   └── news_watcher.py       # News scanning
│   ├── schemas/                  # Pydantic models
│   │   ├── graph.py              # Entity/relationship schemas
│   │   ├── news.py               # News event schemas
│   │   └── query.py              # Query schemas
│   ├── management/commands/      # Django management commands
│   │   ├── health_check.py       # Service health check
│   │   └── run_news_watcher.py   # News watcher scheduler
│   ├── models.py                 # Django ORM models
│   ├── views.py                  # API endpoints
│   ├── urls.py                   # URL routing
│   ├── admin.py                  # Django admin config
│   └── pdf_ingestion.py          # Standalone PDF ingestion
├── graph_rag_ai/                 # Django project settings
│   ├── settings.py               # Django configuration
│   ├── urls.py                   # Root URL config
│   ├── asgi.py                   # ASGI config
│   ├── wsgi.py                   # WSGI config
│   └── celery.py                 # (Legacy: not used)
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment variable template
├── manage.py                     # Django CLI
└── README.md                     # This file
```

## Configuration

All configuration is managed via environment variables in `.env`:

### Critical Settings
- **NEO4J_URI**: Neo4j connection string (required)
- **NEO4J_USER**: Neo4j username (required)
- **NEO4J_PASSWORD**: Neo4j password (required)
- **DJANGO_SECRET_KEY**: Secret key for Django (change in production!)
- **DEBUG**: Set to False in production

### Optional Settings
- **NEWSAPI_KEY**: NewsAPI key for supply chain news (leave blank to disable)
- **OLLAMA_BASE_URL**: Ollama server URL (default: http://localhost:11434)
- **OLLAMA_MODEL**: LLM model to use (default: llama3.2)
- **PDF_PATH**: Default PDF path for standalone ingestion
- **NEWS_WATCHER_INTERVAL_MINUTES**: How often to scan news (default: 60)

## How It Works

### 1. PDF Ingestion Pipeline
- User uploads a PDF via the web interface or API
- PDF is processed in a background thread (no Celery required)
- Text is chunked using LangChain's RecursiveCharacterTextSplitter
- Ollama (llama3.2) extracts entities and relationships
- Results are validated via Pydantic and ingested into Neo4j

### 2. Knowledge Graph
- Entities (companies, ports, products, etc.) stored as Neo4j nodes
- Relationships (supplies_to, located_in, etc.) stored as edges
- Graph enables supply chain traversal and impact analysis

### 3. News Watcher
- Periodically fetches news articles from NewsAPI
- Ollama analyzes articles for supply chain disruptions
- Events are stored in Django database and linked to graph entities

### 4. Risk Assessment Agent
- Uses LangGraph to orchestrate a multi-step workflow
- Steps: parse_query → query_graph → assess_risk → generate_report
- Returns structured risk assessments with confidence scores

## Troubleshooting

### "Neo4j authentication failed"
```
Check that NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD are set correctly in .env
```

### "Ollama service unavailable"
```
Make sure Ollama is running: ollama serve
And llama3.2 is pulled: ollama pull llama3.2
```

### "NEWSAPI_KEY not set"
```
This is optional. Leave it blank to disable news watcher.
```

### Database Migrations Failed
```
python manage.py migrate --run-syncdb
```

### Permissions Error on PDF Upload
```
Ensure the media/ directory is writable:
chmod -R 755 media/
```

## Production Deployment

### Before Going Live
1. ✅ Change `DJANGO_SECRET_KEY` to a random 50+ character string
2. ✅ Set `DEBUG = False` in settings.py or environment
3. ✅ Set `ALLOWED_HOSTS` to your domain
4. ✅ Use a production WSGI server (Gunicorn, uWSGI)
5. ✅ Use PostgreSQL instead of SQLite
6. ✅ Set up SSL/TLS certificates
7. ✅ Use environment variables (never hardcode credentials)
8. ✅ Run the health check: `python manage.py health_check`

### Recommended Setup
```bash
# Use Gunicorn for production
pip install gunicorn

# Run with Gunicorn
gunicorn graph_rag_ai.wsgi --bind 0.0.0.0:8000 --workers 4

# Use a reverse proxy (Nginx) in front
# Use systemd or supervisor to keep it running
# Set up log rotation
```

## Development

### Running Tests
```bash
python manage.py test core
```

### Linting
```bash
pip install flake8
flake8 core/
```

### Adding New Entity Types
1. Update [core/schemas/graph.py](core/schemas/graph.py) with new EntityLabel
2. Update extraction prompts in [core/services/graph_builder.py](core/services/graph_builder.py)
3. Optionally add Django admin customization in [core/admin.py](core/admin.py)

## API Reference

See [API_REFERENCE.md](API_REFERENCE.md) for detailed endpoint documentation.

## License

Proprietary — FinTrace Supply Chain Monitor

## Support

For issues or questions:
1. Check the [troubleshooting](#troubleshooting) section
2. Run `python manage.py health_check` to diagnose
3. Check Django logs in `graph_rag_ai/logs/` (if configured)
4. Review [core/services/](core/services/) for service implementations
