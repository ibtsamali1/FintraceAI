"""
News Parser Service
====================
Fetches news articles from NewsAPI, parses them for supply-chain
disruption events using OpenAI (gpt-4o-mini), and links detected events
to affected entities in the Neo4j knowledge graph.

gpt-4o-mini supports native tool-calling and structured output.
A manual JSON parsing fallback is retained for resilience.

Usage:
    from core.services.news_parser import fetch_news, parse_disruption, link_event_to_graph

    articles = fetch_news(["supply chain", "port closure"])
    for article in articles:
        event = parse_disruption(article)
        if event:
            link_event_to_graph(event)
"""

import json
import logging
from datetime import datetime
from typing import Optional

import requests
from langchain_core.messages import HumanMessage, SystemMessage

from core.schemas.news import (
    DisruptionEvent,
    NewsArticle,
    RiskParameters,
)
from core.services.llm import get_extraction_llm
from core.services.neo4j_connection import get_session
from core.config import NEWSAPI_KEY, NEWSAPI_BASE_URL, DEFAULT_NEWS_KEYWORDS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (imported from core.config)
# ---------------------------------------------------------------------------
# NEWSAPI_KEY — loaded from .env via config module
# NEWSAPI_BASE_URL — constant endpoint for news search
# DEFAULT_NEWS_KEYWORDS — default search keywords if none provided

# ---------------------------------------------------------------------------
# JSON extraction helper (reusable)
# ---------------------------------------------------------------------------
import re as _re
_FENCE_RE = _re.compile(r"```(?:json)?\s*(.*?)```", _re.DOTALL)


def _extract_json_str(text: str) -> str:
    """Strip markdown code fences and return the inner JSON string."""
    match = _FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text.strip()


# ---------------------------------------------------------------------------
# Disruption extraction prompt
# ---------------------------------------------------------------------------
DISRUPTION_SYSTEM_PROMPT = """You are a supply-chain risk intelligence analyst.
Analyze the news article and determine if it describes a supply-chain disruption event.

If it IS a disruption event, return ONLY valid JSON (no markdown) matching this structure:
{
  "event_type": "<one of: natural_disaster, geopolitical, sanctions, trade_restriction, port_closure, labor_strike, pandemic, cyber_attack, regulatory_change, shipping_disruption, conflict, infrastructure_failure, financial_crisis, other>",
  "severity": "<one of: critical, high, medium, low, informational>",
  "title": "<short event title>",
  "description": "<detailed description of the disruption and its potential supply-chain impact>",
  "locations": ["<affected countries/cities/ports/regions>"],
  "materials": ["<affected materials/products/commodities>"],
  "affected_entities": ["<specific companies/organizations mentioned>"]
}

If the article does NOT describe a supply-chain disruption, return:
{"event_type": null}

Output ONLY the JSON object. No explanation, no markdown fences.
"""


def fetch_news(
    keywords: Optional[list[str]] = None,
    page_size: int = 10,
) -> list[NewsArticle]:
    """
    Fetch recent news articles from NewsAPI matching supply-chain keywords.

    Args:
        keywords: Search terms. Defaults to supply-chain disruption keywords.
        page_size: Max articles to fetch per request (1-100).

    Returns:
        List of validated NewsArticle objects.
    """
    if not NEWSAPI_KEY:
        logger.warning("NEWSAPI_KEY not set — skipping news fetch")
        return []

    if keywords is None:
        keywords = DEFAULT_NEWS_KEYWORDS

    query = " OR ".join(f'"{kw}"' for kw in keywords[:5])

    try:
        response = requests.get(
            NEWSAPI_BASE_URL,
            params={
                "q": query,
                "apiKey": NEWSAPI_KEY,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": min(page_size, 100),
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

    except requests.RequestException as e:
        logger.error("NewsAPI request failed: %s", e)
        return []

    articles: list[NewsArticle] = []
    for item in data.get("articles", []):
        try:
            content = item.get("content") or item.get("description") or ""
            if len(content) < 20:
                continue

            articles.append(
                NewsArticle(
                    title=item.get("title", "Untitled"),
                    source=item.get("source", {}).get("name", "Unknown"),
                    url=item.get("url"),
                    published_at=_parse_datetime(item.get("publishedAt")),
                    content=content,
                    raw_metadata=item,
                )
            )
        except Exception as e:
            logger.debug("Skipping malformed article: %s", e)
            continue

    logger.info("Fetched %d articles from NewsAPI", len(articles))
    return articles


def parse_disruption(article: NewsArticle) -> Optional[DisruptionEvent]:
    """
    Use OpenAI (gpt-4o-mini) to analyze a news article and extract a structured
    disruption event if one is present.

    Tries structured_output first; falls back to manual JSON parsing.

    Args:
        article: A validated NewsArticle.

    Returns:
        A DisruptionEvent if a disruption was detected, else None.
    """
    llm = get_extraction_llm()

    user_prompt = (
        f"Analyze this news article for supply-chain disruption:\n\n"
        f"Title: {article.title}\n"
        f"Source: {article.source}\n"
        f"Date: {article.published_at}\n\n"
        f"Content:\n{article.content[:3000]}"
    )

    messages = [
        SystemMessage(content=DISRUPTION_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ]

    # ── Attempt 1: structured_output shim ────────────────────────────
    try:
        structured_llm = llm.with_structured_output(DisruptionEvent)
        event: DisruptionEvent = structured_llm.invoke(messages)

        if event.event_type is None:
            logger.debug("No disruption in '%s' (structured_output)", article.title)
            return None

        event.source_url = article.url
        event.event_date = article.published_at

        logger.info(
            "Parsed disruption (structured): type=%s severity=%s locations=%s",
            event.event_type.value, event.severity.value, event.locations,
        )
        return event

    except Exception as structured_err:
        logger.debug(
            "structured_output failed (%s) — falling back to JSON parse",
            structured_err,
        )

    # ── Attempt 2: raw invocation + manual JSON parse ─────────────────
    try:
        raw_response = llm.invoke(messages)
        raw_text: str = (
            raw_response.content
            if hasattr(raw_response, "content")
            else str(raw_response)
        )

        json_str = _extract_json_str(raw_text)
        data = json.loads(json_str)

        if data.get("event_type") is None:
            logger.debug("No disruption in '%s' (JSON parse)", article.title)
            return None

        event = DisruptionEvent.model_validate(data)
        event.source_url = article.url
        event.event_date = article.published_at

        logger.info(
            "Parsed disruption (JSON parse): type=%s severity=%s locations=%s",
            event.event_type.value, event.severity.value, event.locations,
        )
        return event

    except Exception as e:
        logger.debug("No disruption parsed from '%s': %s", article.title, e)
        return None


def link_event_to_graph(event: DisruptionEvent) -> dict[str, int]:
    """
    Create an event node in Neo4j and link it to affected graph entities.

    For each location, material, and entity name in the disruption event,
    attempts to find a matching node in the graph and creates an
    AFFECTED_BY relationship.

    Args:
        event: A validated DisruptionEvent.

    Returns:
        Dict with counts of created links: {"event_node_created": bool, "links_created": N}
    """
    links_created = 0

    with get_session() as session:
        # Create the DisruptionEvent node
        session.run(
            """
            MERGE (e:DisruptionEvent {title: $title})
            SET e.event_type = $event_type,
                e.severity = $severity,
                e.description = $description,
                e.source_url = $source_url,
                e.event_date = $event_date,
                e.updated_at = datetime()
            """,
            title=event.title,
            event_type=event.event_type.value,
            severity=event.severity.value,
            description=event.description,
            source_url=event.source_url or "",
            event_date=str(event.event_date) if event.event_date else "",
        )

        # Link to affected entities by matching against existing graph nodes
        all_terms = event.locations + event.materials + event.affected_entities

        for term in all_terms:
            if not term or not term.strip():
                continue

            result = session.run(
                """
                MATCH (n)
                WHERE toLower(n.name) CONTAINS toLower($term)
                WITH n LIMIT 5
                MATCH (e:DisruptionEvent {title: $event_title})
                MERGE (n)-[:AFFECTED_BY]->(e)
                RETURN count(n) AS linked
                """,
                term=term.strip(),
                event_title=event.title,
            )

            record = result.single()
            if record:
                links_created += record["linked"]

    logger.info(
        "Linked event '%s' to %d graph entities",
        event.title, links_created,
    )

    return {
        "event_node_created": True,
        "links_created": links_created,
    }


def extract_risk_parameters(event: DisruptionEvent) -> RiskParameters:
    """
    Extract normalized search parameters from a disruption event.

    These parameters are used by the LangGraph agent to execute
    targeted Cypher queries against the knowledge graph.

    Args:
        event: A validated DisruptionEvent.

    Returns:
        RiskParameters for graph querying.
    """
    return RiskParameters(
        locations=event.locations,
        materials=event.materials,
        entity_names=event.affected_entities,
        disruption_type=event.event_type,
        severity=event.severity,
    )


def _parse_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO datetime string from NewsAPI, returning None on failure."""
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
