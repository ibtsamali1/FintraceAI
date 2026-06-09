"""
Graph Builder Service
======================
Extracts entities and relationships from text using OpenAI (gpt-4o-mini) with
Pydantic-validated structured output, then ingests them into Neo4j.

gpt-4o-mini supports native tool-calling and structured output via LangChain's
`.with_structured_output()` method. A manual JSON parsing fallback is retained
for resilience.

Usage:
    from core.services.graph_builder import extract_entities_from_text, ingest_graph_data

    result = extract_entities_from_text("NordOil supplies crude oil to...")
    stats = ingest_graph_data(result)
"""

import json
import re
import logging
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from core.schemas.graph import (
    EntityNode,
    EntityRelationship,
    GraphExtractionResult,
)
from core.services.llm import get_extraction_llm
from core.services.neo4j_connection import get_session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Validation patterns — matching pdf_ingestion.py for consistency
# ---------------------------------------------------------------------------
LABEL_RE = re.compile(r"^[A-Z][A-Za-z]+$")
TYPE_RE = re.compile(r"^[A-Z][A-Z_]+$")

# ---------------------------------------------------------------------------
# JSON extraction helper — strips markdown fences if present
# ---------------------------------------------------------------------------
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _extract_json_str(text: str) -> str:
    """Strip markdown code fences and return the inner JSON string."""
    match = _FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    # Try to find the outermost {...} block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text.strip()


# ---------------------------------------------------------------------------
# Extraction prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are a supply-chain knowledge graph extraction engine.
Extract all entities and relationships from the provided text.

Return ONLY valid JSON matching this exact structure (no markdown, no extra text):
{
  "nodes": [
    {"name": "<entity name>", "label": "<PascalCase type>", "properties": {}}
  ],
  "relationships": [
    {"from_node": "<source entity name>", "to_node": "<target entity name>", "rel_type": "<UPPER_SNAKE_CASE>", "properties": {}}
  ]
}

Rules:
- Every node must appear in at least one relationship.
- Infer relationships if not explicitly stated.
- Node labels: single PascalCase word (Company, Supplier, Factory, Port, Country, Product, Vessel, Regulator, Organization, Bank, etc.)
- Relationship types: UPPER_SNAKE_CASE (SUPPLIES_TO, OWNS, OPERATES, LOCATED_IN, PART_OF, CONTRACTS_WITH, REGULATED_BY, MANAGES, TRANSPORTS_VIA, FINANCES, INSPECTS, INSURES, PARTNERS_WITH, SUBSIDIARY_OF, RELATED_TO)
- Be thorough: extract ALL entities and relationships present in the text.
- Output ONLY the JSON object. No explanation, no markdown fences.
"""

USER_PROMPT_TEMPLATE = """Extract all entities and relationships from this text:

{text}"""


def extract_entities_from_text(text: str, timeout_seconds: int = 60) -> GraphExtractionResult:
    """
    Use OpenAI (gpt-4o-mini) to extract entities and relationships from raw text.

    Tries `.with_structured_output()` first (native tool calling).
    Falls back to manual JSON parsing if structured output fails.

    Args:
        text: The raw text chunk to extract from.
        timeout_seconds: Max seconds to wait for LLM response (default: 60).

    Returns:
        A validated GraphExtractionResult with nodes and relationships.
    """
    if not text or not text.strip():
        return GraphExtractionResult(nodes=[], relationships=[])

    import socket
    
    llm = get_extraction_llm()

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=USER_PROMPT_TEMPLATE.format(text=text[:4000])),
    ]

    # ── Attempt 1: structured_output shim (may work on newer llama3.2 builds) ─
    try:
        structured_llm = llm.with_structured_output(GraphExtractionResult)
        result: GraphExtractionResult = structured_llm.invoke(messages)
        logger.info(
            "Extracted %d nodes, %d relationships (structured_output) from %d chars",
            result.node_count, result.relationship_count, len(text),
        )
        return result
    except (socket.timeout, TimeoutError) as timeout_err:
        logger.warning(
            "LLM request timeout (structured_output) after %ds: %s — retrying with JSON parse",
            timeout_seconds, timeout_err,
        )
    except Exception as structured_err:
        logger.debug(
            "with_structured_output failed (%s) — falling back to JSON parse",
            structured_err,
        )

    # ── Attempt 2: raw invocation + manual JSON parse ─────────────────────────
    try:
        raw_response = llm.invoke(messages)
        raw_text: str = (
            raw_response.content
            if hasattr(raw_response, "content")
            else str(raw_response)
        )

        json_str = _extract_json_str(raw_text)
        data = json.loads(json_str)
        result = GraphExtractionResult.model_validate(data)

        logger.info(
            "Extracted %d nodes, %d relationships (JSON parse) from %d chars",
            result.node_count, result.relationship_count, len(text),
        )
        return result

    except (socket.timeout, TimeoutError) as timeout_err:
        logger.error(
            "LLM request timeout (JSON parse) after %ds for %d chars: %s — skipping batch",
            timeout_seconds, len(text), timeout_err,
        )
        # Return empty result rather than crashing the whole pipeline
        return GraphExtractionResult(nodes=[], relationships=[])
    except Exception as e:
        logger.error("Entity extraction failed: %s", e)
        # Return empty result rather than crashing the whole pipeline
        return GraphExtractionResult(nodes=[], relationships=[])


def ingest_graph_data(
    data: GraphExtractionResult,
) -> dict[str, int]:
    """
    Write extracted entities and relationships to Neo4j using MERGE operations.

    Reuses the shared neo4j_connection.get_session() singleton.
    Validates labels and relationship types with the same regex patterns
    used in pdf_ingestion.py for consistency.

    Args:
        data: A validated GraphExtractionResult.

    Returns:
        Dict with counts: {"nodes_written": N, "relationships_written": N}
    """
    nodes_written = 0
    rels_written = 0

    with get_session() as session:
        # ── Write nodes ──────────────────────────────────────────────
        for node in data.nodes:
            name = node.name.strip()
            label = node.label.value

            if not name:
                continue
            if not LABEL_RE.match(label):
                label = "Entity"

            session.run(
                f"MERGE (n:{label} {{name: $name}})",
                name=name,
            )
            nodes_written += 1

        # ── Write relationships ──────────────────────────────────────
        for rel in data.relationships:
            from_name = rel.from_node.strip()
            to_name = rel.to_node.strip()
            rel_type = rel.rel_type.value

            if not (from_name and to_name and rel_type):
                continue
            if not TYPE_RE.match(rel_type):
                rel_type = "RELATED_TO"

            session.run(
                f"""
                MATCH (x {{name: $from_name}})
                MATCH (y {{name: $to_name}})
                MERGE (x)-[:{rel_type}]->(y)
                """,
                from_name=from_name,
                to_name=to_name,
            )
            rels_written += 1

    logger.info("Ingested %d nodes, %d relationships", nodes_written, rels_written)

    return {
        "nodes_written": nodes_written,
        "relationships_written": rels_written,
    }


def process_text_chunks(
    chunks: list[str],
    batch_size: int = 5,
) -> dict[str, int]:
    """
    Process multiple text chunks: extract entities and ingest into Neo4j.

    This is the high-level function called by Celery tasks.
    Chunks are batched and merged before extraction to reduce LLM calls.

    Args:
        chunks: List of text strings from document splitting.
        batch_size: Number of chunks to merge per LLM call.

    Returns:
        Aggregate stats: {"total_nodes": N, "total_relationships": N, "batches_processed": N}
    """
    total_nodes = 0
    total_rels = 0
    batches_processed = 0
    errors = 0

    batches = [
        chunks[i : i + batch_size]
        for i in range(0, len(chunks), batch_size)
    ]

    logger.info("Processing %d batches from %d chunks", len(batches), len(chunks))

    for i, batch in enumerate(batches, start=1):
        merged_text = "\n\n".join(c.strip() for c in batch if c.strip())

        if not merged_text:
            continue

        try:
            graph_data = extract_entities_from_text(merged_text)
            stats = ingest_graph_data(graph_data)

            total_nodes += stats["nodes_written"]
            total_rels += stats["relationships_written"]
            batches_processed += 1

            logger.info(
                "[Batch %d/%d] %d nodes, %d rels",
                i, len(batches),
                stats["nodes_written"],
                stats["relationships_written"],
            )

        except Exception as e:
            errors += 1
            logger.error("[Batch %d/%d] Failed: %s", i, len(batches), e)
            continue

    return {
        "total_nodes": total_nodes,
        "total_relationships": total_rels,
        "batches_processed": batches_processed,
        "errors": errors,
    }
