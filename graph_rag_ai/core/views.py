import json
import logging

import requests

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from core.services.graph_query import (
    get_node,
    get_neighbors,
    find_path,
    find_impacted_entities,
    get_graph_statistics,
)
from core.services.redis_client import check_redis_health
from core.config import OPENAI_API_KEY, NEWSAPI_KEY, NEWSAPI_BASE_URL

logger = logging.getLogger(__name__)


# ───────────────────────────────────────────────────────────────────────────
# Graph Query API Views
# ───────────────────────────────────────────────────────────────────────────


@require_GET
def api_get_node(request):
    """
    GET /api/graph/node/?name=<name>&label=<optional_label>
    Find a single node by its name property.
    """
    name = request.GET.get("name", "").strip()
    if not name:
        return JsonResponse({"error": "Missing required parameter: name"}, status=400)

    label = request.GET.get("label", "").strip() or None

    try:
        node = get_node(name, label=label)
    except Exception as e:
        logger.exception("Error in api_get_node")
        return JsonResponse({"error": str(e)}, status=500)

    if node is None:
        return JsonResponse({"error": f"Node '{name}' not found"}, status=404)

    return JsonResponse({"node": node})


@require_GET
def api_get_neighbors(request):
    """
    GET /api/graph/neighbors/?name=<name>&direction=both&rel_type=&limit=50
    Get all directly connected nodes for a given node.
    """
    name = request.GET.get("name", "").strip()
    if not name:
        return JsonResponse({"error": "Missing required parameter: name"}, status=400)

    direction = request.GET.get("direction", "both").strip()
    if direction not in ("both", "outgoing", "incoming"):
        return JsonResponse(
            {"error": "direction must be 'both', 'outgoing', or 'incoming'"}, status=400
        )

    rel_type = request.GET.get("rel_type", "").strip() or None
    limit = min(int(request.GET.get("limit", 50)), 200)

    try:
        data = get_neighbors(name, direction=direction, rel_type=rel_type, limit=limit)
    except Exception as e:
        logger.exception("Error in api_get_neighbors")
        return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse(data)


@require_GET
def api_find_path(request):
    """
    GET /api/graph/path/?from=<name>&to=<name>&max_depth=10
    Find the shortest path between two nodes.
    """
    from_name = request.GET.get("from", "").strip()
    to_name = request.GET.get("to", "").strip()

    if not from_name or not to_name:
        return JsonResponse({"error": "Missing required parameters: from, to"}, status=400)

    max_depth = min(int(request.GET.get("max_depth", 10)), 20)

    try:
        path = find_path(from_name, to_name, max_depth=max_depth)
    except Exception as e:
        logger.exception("Error in api_find_path")
        return JsonResponse({"error": str(e)}, status=500)

    if path is None:
        return JsonResponse(
            {"error": f"No path found between '{from_name}' and '{to_name}'"}, status=404
        )

    return JsonResponse(path)


@require_GET
def api_find_impacted(request):
    """
    GET /api/graph/impacted/?name=<name>&max_depth=5&direction=both
    Find all entities impacted if the given node is disrupted.
    """
    name = request.GET.get("name", "").strip()
    if not name:
        return JsonResponse({"error": "Missing required parameter: name"}, status=400)

    max_depth = min(int(request.GET.get("max_depth", 5)), 15)

    direction = request.GET.get("direction", "both").strip()
    if direction not in ("both", "outgoing", "incoming"):
        return JsonResponse(
            {"error": "direction must be 'both', 'outgoing', or 'incoming'"}, status=400
        )

    try:
        data = find_impacted_entities(name, max_depth=max_depth, direction=direction)
    except Exception as e:
        logger.exception("Error in api_find_impacted")
        return JsonResponse({"error": str(e)}, status=500)

    if data.get("error"):
        return JsonResponse(data, status=404)

    return JsonResponse(data)


@require_GET
def api_graph_stats(request):
    """
    GET /api/graph/stats/
    Return summary statistics about the knowledge graph.
    """
    try:
        stats = get_graph_statistics()
    except Exception as e:
        logger.exception("Error in api_graph_stats")
        return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse(stats)


# ═══════════════════════════════════════════════════════════════════════════
# PDF Upload — Celery Background Task Processing
# ═══════════════════════════════════════════════════════════════════════════


def _dispatch_ingestion_task(document_id: int) -> str:
    """
    Dispatch PDF processing to a Celery worker via Redis broker.
    Returns the Celery AsyncResult task ID for status tracking.
    Django returns the HTTP response immediately; processing continues in the worker.
    """
    from core.tasks.ingestion import process_pdf_upload_task

    result = process_pdf_upload_task.delay(document_id)
    logger.info(
        "Celery task dispatched for document %d (task_id=%s)",
        document_id,
        result.id,
    )
    return result.id


@csrf_exempt
@require_POST
def api_upload_pdf(request):
    """
    POST /api/upload/

    Upload one or more PDF files for knowledge graph extraction.
    Files are saved to disk and processed in a background thread.
    Returns immediately with document IDs for status polling.

    Returns:
        JSON list of {document_id, filename, status} — use /api/doc/<id>/status/ to poll.
    """
    from core.models import Document

    files = request.FILES.getlist("files")
    if not files:
        return JsonResponse(
            {"error": "No files uploaded. Send PDF files in 'files' field."},
            status=400,
        )

    results = []

    for uploaded_file in files:
        # Validate file type
        if not uploaded_file.name.lower().endswith(".pdf"):
            results.append({
                "filename": uploaded_file.name,
                "error": "Only PDF files are accepted.",
            })
            continue

        # Create Document record (status=pending)
        doc = Document.objects.create(
            title=uploaded_file.name,
            file=uploaded_file,
            status="pending",
        )

        # Dispatch to Celery worker via Redis — returns instantly
        task_id = _dispatch_ingestion_task(doc.pk)

        # Store the Celery task ID for optional status polling
        doc.celery_task_id = task_id
        doc.save(update_fields=["celery_task_id"])

        results.append({
            "document_id": doc.pk,
            "filename": uploaded_file.name,
            "status": "pending",
            "task_id": task_id,
        })

        logger.info(
            "PDF dispatched to Celery: doc=%d file=%s task=%s",
            doc.pk, uploaded_file.name, task_id,
        )

    return JsonResponse({"uploads": results}, status=202)


@require_GET
def api_document_status(request, doc_id: int):
    """
    GET /api/doc/<doc_id>/status/

    Poll the processing status of an uploaded PDF document.
    Reads directly from the SQLite database — no Redis/Celery required.

    Returns:
        JSON with document status, and result stats when completed.
    """
    from core.models import Document

    try:
        doc = Document.objects.get(pk=doc_id)
    except Document.DoesNotExist:
        return JsonResponse({"error": f"Document {doc_id} not found"}, status=404)

    response = {
        "document_id": doc.pk,
        "status": doc.status,
        "filename": doc.title,
        "ready": doc.status in ("completed", "failed"),
    }

    if doc.status == "completed":
        response["result"] = {
            "pages": doc.pages_count,
            "chunks": doc.chunks_count,
            "total_nodes": doc.nodes_extracted,
            "total_relationships": doc.relationships_extracted,
        }
    elif doc.status == "failed":
        response["error"] = "Document processing failed. Check server logs."

    return JsonResponse(response)


# ═══════════════════════════════════════════════════════════════════════════
# Health Check
# ═══════════════════════════════════════════════════════════════════════════


@require_GET
def health_check(request):
    """
    GET /health/
    
    Check the health of all external services (Neo4j, Ollama, NewsAPI).
    Returns 200 if all services are OK, 503 if any are unavailable.
    """
    import os
    import requests
    
    status = {
        "status": "ok",
        "services": {},
    }
    
    # Check Neo4j
    try:
        from core.services.neo4j_connection import get_driver
        driver = get_driver()
        driver.verify_connectivity()
        status["services"]["neo4j"] = "ok"
    except Exception as e:
        status["services"]["neo4j"] = f"error: {str(e)}"
        status["status"] = "degraded"
    
    # Check OpenAI API
    try:
        if not OPENAI_API_KEY:
            status["services"]["openai"] = "error: OPENAI_API_KEY not set"
            status["status"] = "degraded"
        else:
            import openai
            client = openai.OpenAI(api_key=OPENAI_API_KEY, timeout=5.0)
            models = client.models.list()
            model_ids = [m.id for m in models.data]
            if "gpt-4o-mini" in model_ids:
                status["services"]["openai"] = "ok (gpt-4o-mini available)"
            else:
                status["services"]["openai"] = "warning: gpt-4o-mini not found in available models"
    except Exception as e:
        status["services"]["openai"] = f"error: {str(e)}"
        status["status"] = "degraded"
    
    # Check NewsAPI (optional)
    try:
        if not NEWSAPI_KEY:
            status["services"]["newsapi"] = "disabled (no NEWSAPI_KEY)"
        else:
            resp = requests.get(
                "https://newsapi.org/v2/top-headlines",
                params={"apiKey": NEWSAPI_KEY, "country": "us", "pageSize": 1},
                timeout=10
            )
            status["services"]["newsapi"] = "ok" if resp.status_code == 200 else f"error: HTTP {resp.status_code}"
    except Exception as e:
        status["services"]["newsapi"] = f"error: {str(e)}"
    
    # Check Redis (optional)
    try:
        redis_healthy, redis_msg = check_redis_health()
        if redis_healthy:
            status["services"]["redis"] = "ok"
        else:
            status["services"]["redis"] = f"warning: {redis_msg}"
    except Exception as e:
        status["services"]["redis"] = f"error: {str(e)}"
    
    http_status = 200 if status["status"] == "ok" else 503
    return JsonResponse(status, status=http_status)


# ═══════════════════════════════════════════════════════════════════════════
# Risk Query Agent
# ═══════════════════════════════════════════════════════════════════════════


@csrf_exempt
@require_POST
def api_query_agent(request):
    """
    POST /api/query/

    Submit a natural-language question to the LangGraph risk assessment agent.
    """
    from core.agent.graph import run_risk_agent

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse(
            {"error": "Invalid JSON body. Send {\"question\": \"...\"}"},
            status=400,
        )

    question = body.get("question", "").strip()
    if not question:
        return JsonResponse({"error": "Missing required field: question"}, status=400)

    if len(question) < 5:
        return JsonResponse(
            {"error": "Question must be at least 5 characters."},
            status=400,
        )

    logger.info("Agent query received: '%s'", question)

    try:
        assessment = run_risk_agent(question)
        return JsonResponse(assessment.model_dump(mode="json"), status=200)

    except Exception as e:
        logger.exception("Agent query failed")
        return JsonResponse({"error": f"Risk assessment failed: {e}"}, status=500)


# ═══════════════════════════════════════════════════════════════════════════
# Dashboard View
# ═══════════════════════════════════════════════════════════════════════════


def dashboard_view(request):
    """
    GET /
    Render the FinTrace dashboard page.
    """
    from core.models import Document, NewsEvent

    documents = Document.objects.all()[:20]
    news_events = NewsEvent.objects.filter(is_active=True).order_by("-created_at")[:15]

    return render(request, "core/dashboard.html", {
        "documents": documents,
        "news_events": news_events,
    })
