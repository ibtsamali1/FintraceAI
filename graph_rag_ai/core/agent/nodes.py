"""
Agent Node Functions
=====================
Each function is a step in the LangGraph risk assessment workflow.
They receive the current AgentState and return a partial state update dict.

Workflow:
    parse_query → query_graph → assess_risk → generate_report

LLM Backend:
    OpenAI (gpt-4o-mini) via langchain_openai.ChatOpenAI.
    Uses structured_output (native tool calling) with JSON parse fallback.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from core.schemas.query import (
    ImpactedEntity,
    ParsedQueryParams,
    QueryIntent,
    RiskAssessment,
    RiskLevel,
)
from core.services.graph_query import (
    find_impacted_entities,
    get_neighbors,
    get_node,
)
from core.services.llm import get_extraction_llm, get_reasoning_llm

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JSON fence stripper (shared with graph_builder / news_parser)
# ---------------------------------------------------------------------------
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _extract_json_str(text: str) -> str:
    match = _FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text.strip()


# ═══════════════════════════════════════════════════════════════════════════
# Node 1: Parse the user's natural-language query
# ═══════════════════════════════════════════════════════════════════════════

PARSE_QUERY_PROMPT = """You are a supply-chain intelligence query parser.
Parse the user's question and extract structured parameters for graph querying.

Return ONLY valid JSON (no markdown fences, no extra text) matching this structure:
{
  "entities": ["<entity names mentioned in the query>"],
  "locations": ["<geographic locations mentioned>"],
  "relationship_types": ["<specific relationship types to traverse, if any>"],
  "intent": "<one of: risk_assessment, impact_analysis, supplier_check, route_check, general_query>",
  "max_depth": <integer 1-10, how deep to search the graph>
}

Be thorough — extract ALL entity names, locations, and implied search parameters.
If the user asks about "my supply chain" broadly, set entities to an empty list
and intent to "risk_assessment".
Output ONLY the JSON object.
"""


def parse_query(state: dict[str, Any]) -> dict[str, Any]:
    """
    Node 1: Parse the user's raw question into structured query parameters.

    Uses OpenAI (gpt-4o-mini) to extract entity names, locations, intent, and
    traversal depth from the natural-language question.
    Tries structured_output first; falls back to JSON parsing.
    """
    raw_query = state.get("raw_query", "")
    reasoning_trace = list(state.get("reasoning_trace", []))
    errors = list(state.get("errors", []))

    reasoning_trace.append(f"[parse_query] Parsing user question: '{raw_query}'")

    messages = [
        SystemMessage(content=PARSE_QUERY_PROMPT),
        HumanMessage(content=f"Parse this query: {raw_query}"),
    ]

    # ── Attempt 1: structured_output shim ────────────────────────────
    try:
        llm = get_extraction_llm()
        structured_llm = llm.with_structured_output(ParsedQueryParams)
        parsed: ParsedQueryParams = structured_llm.invoke(messages)

        reasoning_trace.append(
            f"[parse_query] Extracted (structured): entities={parsed.entities}, "
            f"locations={parsed.locations}, intent={parsed.intent.value}"
        )
        return {
            "parsed_params": parsed,
            "reasoning_trace": reasoning_trace,
            "errors": errors,
        }
    except Exception as structured_err:
        logger.debug("structured_output failed in parse_query: %s", structured_err)

    # ── Attempt 2: raw LLM + JSON parse ──────────────────────────────
    try:
        llm = get_extraction_llm()
        raw_response = llm.invoke(messages)
        raw_text: str = (
            raw_response.content
            if hasattr(raw_response, "content")
            else str(raw_response)
        )

        json_str = _extract_json_str(raw_text)
        data = json.loads(json_str)
        parsed = ParsedQueryParams.model_validate(data)

        reasoning_trace.append(
            f"[parse_query] Extracted (JSON parse): entities={parsed.entities}, "
            f"locations={parsed.locations}, intent={parsed.intent.value}"
        )
        return {
            "parsed_params": parsed,
            "reasoning_trace": reasoning_trace,
            "errors": errors,
        }

    except Exception as e:
        logger.exception("parse_query failed entirely")
        errors.append(f"parse_query: {e}")
        # Return safe defaults so the pipeline can continue
        return {
            "parsed_params": ParsedQueryParams(
                entities=[],
                locations=[],
                relationship_types=[],
                intent=QueryIntent.GENERAL_QUERY,
                max_depth=5,
            ),
            "reasoning_trace": reasoning_trace,
            "errors": errors,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Node 2: Query the Neo4j knowledge graph
# ═══════════════════════════════════════════════════════════════════════════

def query_graph(state: dict[str, Any]) -> dict[str, Any]:
    """
    Node 2: Execute targeted Cypher traversals against Neo4j.

    Uses the EXISTING graph_query.py service functions (get_node,
    get_neighbors, find_impacted_entities) — no Cypher duplication.
    """
    parsed = state.get("parsed_params")
    reasoning_trace = list(state.get("reasoning_trace", []))
    errors = list(state.get("errors", []))

    if parsed is None:
        errors.append("query_graph: No parsed parameters available")
        return {"graph_results": {}, "reasoning_trace": reasoning_trace, "errors": errors}

    graph_results: dict[str, Any] = {
        "found_nodes": [],
        "impact_analyses": [],
        "neighbor_maps": [],
    }

    search_terms = parsed.entities + parsed.locations

    for term in search_terms:
        node = get_node(term)

        if node is None:
            reasoning_trace.append(f"[query_graph] Node '{term}' not found in graph")
            continue

        graph_results["found_nodes"].append(node)
        reasoning_trace.append(
            f"[query_graph] Found node: {node['properties'].get('name', term)} "
            f"(labels: {node['labels']})"
        )

        neighbors = get_neighbors(term, limit=20)
        graph_results["neighbor_maps"].append({
            "entity": term,
            "neighbors": neighbors,
        })

        if parsed.intent in (
            QueryIntent.RISK_ASSESSMENT,
            QueryIntent.IMPACT_ANALYSIS,
            QueryIntent.SUPPLIER_CHECK,
        ):
            impact = find_impacted_entities(
                term,
                max_depth=parsed.max_depth,
                direction="both",
            )
            graph_results["impact_analyses"].append({
                "entity": term,
                "impact": impact,
            })
            reasoning_trace.append(
                f"[query_graph] Impact analysis for '{term}': "
                f"{impact.get('count', 0)} entities impacted"
            )

    reasoning_trace.append(
        f"[query_graph] Total: {len(graph_results['found_nodes'])} nodes found, "
        f"{len(graph_results['impact_analyses'])} impact analyses run"
    )

    return {
        "graph_results": graph_results,
        "reasoning_trace": reasoning_trace,
        "errors": errors,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Node 3: Assess risk by correlating graph data with active events
# ═══════════════════════════════════════════════════════════════════════════

def assess_risk(state: dict[str, Any]) -> dict[str, Any]:
    """
    Node 3: Correlate graph traversal results with active disruption events.

    Cross-references the impacted entities from graph traversal with
    NewsEvent records in the Django database to determine risk levels.
    """
    from core.models import NewsEvent

    graph_results = state.get("graph_results", {})
    reasoning_trace = list(state.get("reasoning_trace", []))
    errors = list(state.get("errors", []))

    impacted_entities: list[ImpactedEntity] = []
    active_disruptions: list[dict[str, Any]] = []

    try:
        recent_events = NewsEvent.objects.order_by("-created_at")[:20]
        active_disruptions = [
            {
                "title": evt.title,
                "event_type": evt.event_type,
                "severity": evt.severity,
                "locations": evt.locations,
                "materials": evt.materials,
                "affected_entities": evt.affected_entities,
            }
            for evt in recent_events
        ]
        reasoning_trace.append(
            f"[assess_risk] Found {len(active_disruptions)} active disruption events"
        )
    except Exception as e:
        logger.warning("Could not fetch news events: %s", e)
        reasoning_trace.append(f"[assess_risk] Warning: Could not fetch news events: {e}")

    disrupted_terms: set[str] = set()
    for d in active_disruptions:
        disrupted_terms.update(loc.lower() for loc in d.get("locations", []))
        disrupted_terms.update(ent.lower() for ent in d.get("affected_entities", []))
        disrupted_terms.update(mat.lower() for mat in d.get("materials", []))

    for analysis in graph_results.get("impact_analyses", []):
        impact_data = analysis.get("impact", {})

        for item in impact_data.get("impacted", []):
            node_data = item.get("node", {})
            node_name = node_data.get("properties", {}).get("name", "Unknown")
            node_labels = node_data.get("labels", [])
            depth = item.get("depth", 0)

            name_lower = node_name.lower()
            matches_disruption = any(
                term in name_lower or name_lower in term
                for term in disrupted_terms
            )

            if matches_disruption and depth <= 1:
                risk_level = RiskLevel.CRITICAL
            elif matches_disruption:
                risk_level = RiskLevel.HIGH
            elif depth <= 1:
                risk_level = RiskLevel.MEDIUM
            elif depth <= 3:
                risk_level = RiskLevel.LOW
            else:
                risk_level = RiskLevel.NONE

            impacted_entities.append(
                ImpactedEntity(
                    name=node_name,
                    label=node_labels[0] if node_labels else "Entity",
                    depth=depth,
                    risk_level=risk_level,
                    relationship_path=item.get("relationship_chain", []),
                )
            )

    if any(e.risk_level == RiskLevel.CRITICAL for e in impacted_entities):
        overall_risk = RiskLevel.CRITICAL
    elif any(e.risk_level == RiskLevel.HIGH for e in impacted_entities):
        overall_risk = RiskLevel.HIGH
    elif any(e.risk_level == RiskLevel.MEDIUM for e in impacted_entities):
        overall_risk = RiskLevel.MEDIUM
    elif impacted_entities:
        overall_risk = RiskLevel.LOW
    else:
        overall_risk = RiskLevel.NONE

    reasoning_trace.append(
        f"[assess_risk] {len(impacted_entities)} entities assessed, "
        f"overall risk: {overall_risk.value}"
    )

    return {
        "impacted_entities": impacted_entities,
        "active_disruptions": active_disruptions,
        "overall_risk_level": overall_risk,
        "reasoning_trace": reasoning_trace,
        "errors": errors,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Node 4: Generate the final risk assessment report
# ═══════════════════════════════════════════════════════════════════════════

REPORT_SYSTEM_PROMPT = """You are a supply-chain risk analyst generating a professional risk assessment report.

Based on the graph analysis data and active disruption events provided, generate:
1. An executive summary of the risk situation
2. Specific actionable recommendations for risk mitigation

Be concise, professional, and actionable. Reference specific entities and relationships.
Do NOT make up entities or events — only reference data that was provided to you.
"""


def generate_report(state: dict[str, Any]) -> dict[str, Any]:
    """
    Node 4: Use OpenAI (gpt-4o-mini) to synthesize all findings into a
    human-readable risk assessment report.
    """
    raw_query = state.get("raw_query", "")
    impacted_entities = state.get("impacted_entities", [])
    active_disruptions = state.get("active_disruptions", [])
    overall_risk = state.get("overall_risk_level", RiskLevel.NONE)
    graph_results = state.get("graph_results", {})
    reasoning_trace = list(state.get("reasoning_trace", []))
    errors = list(state.get("errors", []))

    entities_summary = []
    for e in impacted_entities[:30]:
        if isinstance(e, ImpactedEntity):
            entities_summary.append(
                f"- {e.name} ({e.label}): risk={e.risk_level.value}, "
                f"depth={e.depth}, path={e.relationship_path}"
            )
        elif isinstance(e, dict):
            entities_summary.append(f"- {e.get('name', 'Unknown')}: {e}")

    disruptions_summary = []
    for d in active_disruptions[:10]:
        disruptions_summary.append(
            f"- {d.get('title', 'Unknown')}: type={d.get('event_type')}, "
            f"severity={d.get('severity')}, locations={d.get('locations')}"
        )

    context = (
        f"User Question: {raw_query}\n\n"
        f"Overall Risk Level: {overall_risk.value if hasattr(overall_risk, 'value') else overall_risk}\n\n"
        f"Impacted Entities ({len(impacted_entities)} total):\n"
        + "\n".join(entities_summary or ["None found"])
        + f"\n\nActive Disruption Events ({len(active_disruptions)} total):\n"
        + "\n".join(disruptions_summary or ["None active"])
        + f"\n\nGraph Analysis: {len(graph_results.get('found_nodes', []))} entities found in knowledge graph"
    )

    try:
        llm = get_reasoning_llm()

        messages = [
            SystemMessage(content=REPORT_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    "Generate a risk assessment report based on this analysis data:\n\n"
                    + context
                    + "\n\nProvide: 1) Executive summary, 2) Specific recommendations"
                )
            ),
        ]

        response = llm.invoke(messages)
        report_text = (
            response.content.strip()
            if hasattr(response, "content")
            else str(response).strip()
        )

        # Parse recommendations from the LLM output
        lines = report_text.split("\n")
        recommendations: list[str] = []
        in_recommendations = False
        for line in lines:
            stripped = line.strip()
            if "recommendation" in stripped.lower():
                in_recommendations = True
                continue
            if in_recommendations and stripped.startswith(("-", "•", "1", "2", "3", "4", "5")):
                recommendations.append(stripped.lstrip("-•0123456789. "))

        risk_assessment = RiskAssessment(
            query=raw_query,
            overall_risk_level=overall_risk if isinstance(overall_risk, RiskLevel) else RiskLevel(overall_risk),
            summary=report_text,
            impacted_entities=impacted_entities if all(isinstance(e, ImpactedEntity) for e in impacted_entities) else [],
            active_disruptions=[d.get("title", "") for d in active_disruptions],
            recommendations=recommendations or ["Monitor the situation and reassess in 24 hours."],
            reasoning="\n".join(reasoning_trace),
        )

        reasoning_trace.append("[generate_report] Risk assessment report generated successfully")

        return {
            "risk_assessment": risk_assessment,
            "reasoning_trace": reasoning_trace,
            "errors": errors,
        }

    except Exception as e:
        logger.exception("Report generation failed")
        errors.append(f"generate_report: {e}")

        fallback = RiskAssessment(
            query=raw_query,
            overall_risk_level=overall_risk if isinstance(overall_risk, RiskLevel) else RiskLevel.NONE,
            summary=f"Risk assessment could not be fully generated. Error: {e}",
            impacted_entities=[],
            active_disruptions=[],
            recommendations=["Please retry the query or contact support."],
            reasoning="\n".join(reasoning_trace),
        )

        return {
            "risk_assessment": fallback,
            "reasoning_trace": reasoning_trace,
            "errors": errors,
        }
