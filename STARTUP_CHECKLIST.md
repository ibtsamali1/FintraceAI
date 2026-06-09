# FinTrace Project Startup Checklist

## Pre-Setup (One-Time)

- [ ] **Python Environment**
  - [ ] Python 3.9+ installed
  - [ ] Virtual environment created: `python -m venv venv`
  - [ ] Virtual environment activated

- [ ] **Neo4j Database**
  - [ ] Neo4j instance available (Aura or local)
  - [ ] Have connection string ready
  - [ ] Have username and password ready

- [ ] **Ollama (Local LLM)**
  - [ ] Ollama downloaded and installed from https://ollama.ai
  - [ ] Ollama can be started with `ollama serve`

## Setup (First Time)

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```
**Status**: ⏳ Pending

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env with your Neo4j and API credentials
# CRITICAL: Set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
```
**Status**: ⏳ Pending

### 3. Initialize Django Database
```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
```
**Status**: ⏳ Pending

### 4. Verify Setup
```bash
python manage.py health_check
# Should output: ✅ All services healthy!
```
**Status**: ⏳ Pending

## Running the Application

### Terminal 1: Ollama Server
```bash
ollama serve
```
- Keep this running in the background
- First time: Will start the server
- Subsequent times: Keeps the llama3.2 model loaded

### Terminal 2: Ollama Model (First Time Only)
```bash
ollama pull llama3.2
```
- Only needed if llama3.2 is not already installed
- Takes a few minutes (4GB download)

### Terminal 3: Django Development Server
```bash
python manage.py runserver
# App available at http://localhost:8000
```

### Terminal 4 (Optional): News Watcher
```bash
python manage.py run_news_watcher --interval 60
# Scans news feeds every 60 minutes
# Comment out if NEWSAPI_KEY not set
```

## Quick Tests

### 1. Health Check
```bash
curl http://localhost:8000/health/
# Expected: {"status": "ok", "services": {...}}
```

### 2. Upload a PDF
```bash
curl -X POST -F "files=@sample.pdf" http://localhost:8000/api/upload/
# Expected: {"uploads": [{"document_id": 1, ...}]}
```

### 3. Query the Graph
```bash
curl http://localhost:8000/api/graph/stats/
# Expected: {"nodes": {...}, "relationships": {...}}
```

## Admin Panel

- **URL**: http://localhost:8000/admin
- **Login**: Use superuser created during `createsuperuser`
- **View**: Documents, NewsEvents, and run management commands

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Neo4j authentication failed" | Check NEO4J_* in .env |
| "Ollama service unavailable" | Run `ollama serve` in a terminal |
| "Module not found" | Activate venv and run `pip install -r requirements.txt` |
| "Health check fails" | Run `python manage.py health_check` to see details |
| "Database error" | Run `python manage.py migrate --run-syncdb` |

## Next Steps

1. ✅ Upload PDFs via `/api/upload/`
2. ✅ Query the knowledge graph via `/api/graph/`
3. ✅ Use the risk assessment agent via `/api/query/`
4. ✅ Monitor disruptions via `/api/graph/impacted/`
5. ✅ Configure news watcher (if NEWSAPI_KEY is set)

## Documentation

- [SETUP.md](SETUP.md) — Comprehensive setup and usage guide
- [API_REFERENCE.md](API_REFERENCE.md) — Full API endpoint documentation
- [core/services/](core/services/) — Service layer implementations
- [core/agent/](core/agent/) — LangGraph risk assessment workflow

---

**Status**: Ready for startup! 🚀

Once all items are checked, run the startup commands in the order listed above.
