"""
Query & Risk Assessment Schemas
=================================
Pydantic v2 models for user queries, LangGraph agent state, and
the final risk assessment reports.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Risk classification for individual entities."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class QueryIntent(str, Enum):
    """Classified intent of a user's natural-language query."""
    RISK_ASSESSMENT = "risk_assessment"
    IMPACT_ANALYSIS = "impact_analysis"
    SUPPLIER_CHECK = "supplier_check"
    ROUTE_CHECK = "route_check"
    GENERAL_QUERY = "general_query"


class UserQuery(BaseModel):
    """Parsed and validated user query input."""

    raw_question: str = Field(
        ...,
        min_length=5,
        description="The user's original natural-language question.",
    )
    entity_focus: Optional[list[str]] = Field(
        None,
        description="Specific entity names the user is asking about.",
    )
    intent: Optional[QueryIntent] = Field(
        None,
        description="Classified intent (populated by the agent).",
    )


class ParsedQueryParams(BaseModel):
    """
    Structured parameters extracted from the user's question by the LLM.
    These drive the Cypher queries against Neo4j.
    """

    entities: list[str] = Field(
        default_factory=list,
        description="Entity names to search for in the graph.",
    )
    locations: list[str] = Field(
        default_factory=list,
        description="Geographic locations mentioned in the query.",
    )
    relationship_types: list[str] = Field(
        default_factory=list,
        description="Specific relationship types to traverse.",
    )
    intent: QueryIntent = Field(
        default=QueryIntent.GENERAL_QUERY,
        description="Classified intent of the query.",
    )
    max_depth: int = Field(
        default=5,
        ge=1,
        le=15,
        description="Maximum graph traversal depth.",
    )


class ImpactedEntity(BaseModel):
    """A single entity identified as impacted by an event or disruption."""

    name: str = Field(..., description="Entity name.")
    label: str = Field(..., description="Entity type/label.")
    depth: int = Field(
        ..., ge=0, description="Hops from the disruption source."
    )
    risk_level: RiskLevel = Field(
        default=RiskLevel.MEDIUM,
        description="Assessed risk level for this entity.",
    )
    relationship_path: list[str] = Field(
        default_factory=list,
        description="Chain of relationship types from source to this entity.",
    )
    explanation: str = Field(
        default="",
        description="LLM-generated explanation of why this entity is at risk.",
    )


class RiskAssessment(BaseModel):
    """
    The final output of the LangGraph risk agent.
    A complete risk assessment report for the user's query.
    """

    query: str = Field(..., description="The original user question.")
    overall_risk_level: RiskLevel = Field(
        ..., description="Aggregate risk level across all impacted entities."
    )
    summary: str = Field(
        ..., description="Executive summary of the risk assessment."
    )
    impacted_entities: list[ImpactedEntity] = Field(
        default_factory=list,
        description="List of entities identified as at-risk.",
    )
    active_disruptions: list[str] = Field(
        default_factory=list,
        description="Active disruption events relevant to this query.",
    )
    recommendations: list[str] = Field(
        default_factory=list,
        description="Actionable recommendations for risk mitigation.",
    )
    reasoning: str = Field(
        default="",
        description="Step-by-step reasoning trace from the agent.",
    )
    generated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp of report generation.",
    )

    @property
    def critical_count(self) -> int:
        return sum(
            1 for e in self.impacted_entities
            if e.risk_level == RiskLevel.CRITICAL
        )

    @property
    def high_count(self) -> int:
        return sum(
            1 for e in self.impacted_entities
            if e.risk_level == RiskLevel.HIGH
        )
