"""
PDF Ingestion Celery Task
===========================
Celery background task that processes uploaded PDF documents:
1. Reads the file from disk
2. Splits into text chunks
3. Extracts entities via OpenAI (gpt-4o-mini)
4. Ingests the knowledge graph into Neo4j
5. Updates the Document model with results

Runs as a Celery worker task — never in the Django request thread.

Usage:
    from core.tasks.ingestion import process_pdf_upload_task
    process_pdf_upload_task.delay(document_id)
"""

import logging

from celery import shared_task
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from core.services.graph_builder import process_text_chunks

logger = logging.getLogger(__name__)

# Chunking config
CHUNK_SIZE: int = 600
CHUNK_OVERLAP: int = 90
BATCH_SIZE: int = 5


@shared_task(
    name="core.tasks.ingestion.process_pdf_upload_task",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def process_pdf_upload_task(self, document_id: int) -> dict:
    """
    Process a single uploaded PDF in the Celery worker.

    Args:
        document_id: Primary key of the core.Document model instance.

    Returns:
        Dict with processing results and stats.

    The task updates the Document's status field:
        pending → processing → completed | failed
    """
    # Import models inside the function to avoid Django app-not-ready issues
    import django
    django.setup()  # safe to call multiple times; no-op after first call

    from core.models import Document

    try:
        doc = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        logger.error("Document %d not found — aborting task", document_id)
        return {"error": f"Document {document_id} not found"}

    # Store the Celery task ID on the document for status tracking
    doc.status = "processing"
    doc.celery_task_id = self.request.id or ""
    doc.save(update_fields=["status", "celery_task_id"])

    logger.info(
        "Processing document %d: %s (%s) [task=%s]",
        doc.pk,
        doc.title,
        doc.file.path,
        self.request.id,
    )

    try:
        # ── Step 1: Load PDF pages ───────────────────────────────────
        logger.info("Step 1: Loading PDF from %s", doc.file.path)
        loader = PyPDFLoader(doc.file.path)
        pages = loader.load()
        logger.info("✓ Loaded %d pages", len(pages))

        # ── Step 2: Split into text chunks ───────────────────────────
        logger.info("Step 2: Chunking text (chunk_size=%d, batch_size=%d)", CHUNK_SIZE, BATCH_SIZE)
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", ".", " ", ""],
            length_function=len,
        )
        chunk_docs = splitter.split_documents(pages)
        text_chunks: list[str] = [
            c.page_content for c in chunk_docs if c.page_content.strip()
        ]
        logger.info("✓ Created %d text chunks", len(text_chunks))

        # ── Step 3+4: Extract entities and ingest to Neo4j ───────────
        logger.info("Step 3+4: Extracting entities and ingesting to Neo4j")
        stats = process_text_chunks(text_chunks, batch_size=BATCH_SIZE)
        logger.info(
            "✓ Extraction complete: %d nodes, %d relationships",
            stats["total_nodes"],
            stats["total_relationships"],
        )

        # ── Step 5: Update document record ───────────────────────────
        logger.info("Step 5: Updating document record")
        doc.status = "completed"
        doc.pages_count = len(pages)
        doc.chunks_count = len(text_chunks)
        doc.nodes_extracted = stats["total_nodes"]
        doc.relationships_extracted = stats["total_relationships"]
        doc.save(update_fields=[
            "status",
            "pages_count",
            "chunks_count",
            "nodes_extracted",
            "relationships_extracted",
        ])
        logger.info("✓ Document %d marked as completed", doc.pk)

        logger.info(
            "✅ DOCUMENT %d COMPLETE: %d pages, %d chunks, %d nodes, %d relationships",
            doc.pk,
            len(pages),
            len(text_chunks),
            stats["total_nodes"],
            stats["total_relationships"],
        )

        return {
            "document_id": doc.pk,
            "status": "completed",
            "pages": len(pages),
            "chunks": len(text_chunks),
            **stats,
        }

    except Exception as exc:
        # Mark document as failed
        logger.error("❌ DOCUMENT %d FAILED: %s", doc.pk, exc, exc_info=True)
        doc.status = "failed"
        doc.save(update_fields=["status"])
        return {"document_id": doc.pk, "status": "failed", "error": str(exc)}
