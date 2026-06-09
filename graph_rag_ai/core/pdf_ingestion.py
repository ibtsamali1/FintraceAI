
import os
import json
import re
import sys
import django
import hashlib
import logging

from pathlib import Path

# Setup Django if running as a standalone script
if not hasattr(django, 'apps') or not django.apps.apps.ready:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'graph_rag_ai.settings')
    django.setup()

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from core.services.llm import get_extraction_llm
from core.services.neo4j_connection import get_driver
from core.services.graph_builder import extract_entities_from_text, ingest_graph_data
from core.config import PDF_PATH, PDF_CHUNK_SIZE, PDF_CHUNK_OVERLAP, PDF_BATCH_SIZE, USE_REDIS_CACHE
from core.services.embedding_cache import (
    cache_chunk_embedding,
    get_chunk_embedding,
    cache_data,
    get_cached_data,
    invalidate_pdf_cache,
    cache_status_summary,
)

logger = logging.getLogger(__name__)

# Configuration imported from core.config (loaded from .env)
# PDF_PATH, PDF_CHUNK_SIZE, PDF_CHUNK_OVERLAP, PDF_BATCH_SIZE


def get_pdf_id(pdf_path: str) -> str:
    """
    Generate a unique PDF ID from filename or path.
    
    Args:
        pdf_path: Path to PDF file
    
    Returns:
        Unique PDF identifier for caching
    """
    filename = Path(pdf_path).name
    # Use first 50 chars of filename + hash for uniqueness
    name_part = filename[:50].replace(".", "_")
    hash_part = hashlib.md5(pdf_path.encode()).hexdigest()[:8]
    return f"{name_part}_{hash_part}"


def load_pdf(path: str):
    print(f"\n Loading PDF: {path}")
    loader = PyPDFLoader(path)
    pages = loader.load()
    print(f"   ✓ {len(pages)} pages loaded")
    return pages

def chunk_documents(pages):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=PDF_CHUNK_SIZE,
        chunk_overlap=PDF_CHUNK_OVERLAP,
        separators=["\n\n", "\n", ".", " ", ""],
        length_function=len,
    )
    chunks = splitter.split_documents(pages)
    print(f"\n {len(chunks)} chunks created")
    return chunks


def create_batches(chunks, batch_size=5):
    return [
        chunks[i:i + batch_size]
        for i in range(0, len(chunks), batch_size)
    ]


def merge_chunks(batch):
    return "\n\n".join(
        c.page_content.strip()
        for c in batch
        if c.page_content.strip()
    )


def run_pipeline(pdf_path, skip_cache=False):
    """
    Run the PDF → chunk → embedding → entity extraction → graph ingestion pipeline.
    
    Args:
        pdf_path: Path to PDF file
        skip_cache: If True, skip cache and regenerate all embeddings
    """

    print(f"\n Starting LLM service...")
    llm = get_extraction_llm()

    print(f" Connecting Neo4j...")
    driver = get_driver()
    
    # Generate PDF ID for caching
    pdf_id = get_pdf_id(pdf_path)
    print(f" PDF ID for caching: {pdf_id}")
    
    # Show cache status if enabled
    if USE_REDIS_CACHE:
        print(f"\n 🔴 Redis caching enabled")
        if skip_cache:
            invalidate_pdf_cache(pdf_id)
            print(f" Cache cleared for {pdf_id}")
    else:
        print(f"\n ⚪ Redis caching disabled")

    try:
        pages = load_pdf(pdf_path)
        chunks = chunk_documents(pages)

        # 🔥 BATCH CHUNKS HERE
        batches = create_batches(chunks, PDF_BATCH_SIZE)

        print(f"\n Processing {len(batches)} batches (instead of {len(chunks)} chunks)\n")

        total_nodes = 0
        total_rels = 0
        skipped = 0
        cache_hits = 0

        for i, batch in enumerate(batches, start=1):

            text = merge_chunks(batch)

            if not text:
                skipped += 1
                continue

            print(f"[Batch {i}/{len(batches)}] chunks={len(batch)} chars={len(text)} → ", end="")

            try:
                # Try to get cached extraction result first
                if USE_REDIS_CACHE and not skip_cache:
                    cache_key = f"extraction:pdf:{pdf_id}:batch:{i}"
                    cached_result = get_cached_data(cache_key)
                    
                    if cached_result is not None:
                        print(f"CACHE HIT → ", end="")
                        graph_data = cached_result
                        cache_hits += 1
                    else:
                        # Extract and cache
                        graph_data = extract_entities_from_text(text)
                        cache_data(cache_key, graph_data, ttl=86400)
                else:
                    graph_data = extract_entities_from_text(text)
            
            except Exception as e:
                print(f"SKIP ({e})")
                skipped += len(batch)
                continue

            stats = ingest_graph_data(graph_data)
            n = stats["nodes_written"]
            r = stats["relationships_written"]
            total_nodes += n
            total_rels += r

            print(f"{n} nodes, {r} rels")

        print("\n" + "═" * 70)
        print(" DONE - PDF Ingestion Pipeline Complete")
        print(f"  Nodes: {total_nodes}")
        print(f"  Relationships: {total_rels}")
        print(f"  Skipped batches: {skipped}")
        
        if USE_REDIS_CACHE:
            print(f"  Cache hits: {cache_hits}/{len(batches)}")
            cache_summary = cache_status_summary()
            print(f"  Total cache stats: {cache_summary['stats']}")
        
        print("═" * 70)

    finally:
        driver.close()



if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Ingest PDF into Neo4j knowledge graph")
    parser.add_argument("--pdf", type=str, default=PDF_PATH, help="Path to PDF file")
    parser.add_argument("--skip-cache", action="store_true", help="Skip cache and regenerate")
    
    args = parser.parse_args()
    
    run_pipeline(args.pdf, skip_cache=args.skip_cache)