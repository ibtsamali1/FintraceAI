"""
Agent State Definition
========================
TypedDict defining the shared mutable state that flows through
the LangGraph risk assessment workflow.

Each node function receives the current state and returns partial
updates that are merged into the state for the next node.
"""

from __future__ import annotations

from typing import Any, Optional

from typing_extensions import TypedDict

from core.schemas.query import (
    ImpactedEntity,
    ParsedQueryParams,
    RiskAssessment,
    RiskLevel,
)


class AgentState(TypedDict, total=False):
    """
    Shared state for the LangGraph risk assessment agent.

    Fields are populated progressively as the workflow executes:
    1. parse_query → fills parsed_params
    2. query_graph → fills graph_results
    3. assess_risk → fills impacted_entities, active_disruptions
    4. generate_report → fills risk_assessment
    """

    # ── Input ────────────────────────────────────────────────────────
    raw_query: str
    """The user's original natural-language question."""

    # ── After parse_query node ───────────────────────────────────────
    parsed_params: Optional[ParsedQueryParams]
    """Structured parameters extracted from the user's question."""

    # ── After query_graph node ───────────────────────────────────────
    graph_results: dict[str, Any]
    """Raw results from Neo4j graph traversals."""

    # ── After assess_risk node ───────────────────────────────────────
    impacted_entities: list[ImpactedEntity]
    """Entities identified as at-risk."""

    active_disruptions: list[dict[str, Any]]
    """Active disruption events from the database."""

    overall_risk_level: RiskLevel
    """Aggregate risk level across all findings."""

    # ── After generate_report node ───────────────────────────────────
    risk_assessment: Optional[RiskAssessment]
    """The final structured risk assessment report."""

    # ── Diagnostics ──────────────────────────────────────────────────
    reasoning_trace: list[str]
    """Step-by-step reasoning log from each node."""

    errors: list[str]
    """Any errors encountered during processing."""
