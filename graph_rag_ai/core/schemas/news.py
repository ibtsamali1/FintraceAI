"""
News & Disruption Event Schemas
=================================
Pydantic v2 models for incoming news articles and parsed disruption events.

The news watcher fetches articles, the LLM parses them into structured
DisruptionEvent objects, and those are linked to Neo4j graph entities.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class DisruptionType(str, Enum):
    """Categories of supply-chain disruption events."""
    NATURAL_DISASTER = "natural_disaster"
    GEOPOLITICAL = "geopolitical"
    SANCTIONS = "sanctions"
    TRADE_RESTRICTION = "trade_restriction"
    PORT_CLOSURE = "port_closure"
    LABOR_STRIKE = "labor_strike"
    PANDEMIC = "pandemic"
    CYBER_ATTACK = "cyber_attack"
    REGULATORY_CHANGE = "regulatory_change"
    SHIPPING_DISRUPTION = "shipping_disruption"
    CONFLICT = "conflict"
    INFRASTRUCTURE_FAILURE = "infrastructure_failure"
    FINANCIAL_CRISIS = "financial_crisis"
    OTHER = "other"


class SeverityLevel(str, Enum):
    """Impact severity classification."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class NewsArticle(BaseModel):
    """A raw news article fetched from an external source."""

    title: str = Field(..., min_length=1, description="Article headline.")
    source: str = Field(..., description="Publication or feed name.")
    url: Optional[str] = Field(None, description="Link to the full article.")
    published_at: Optional[datetime] = Field(
        None, description="Publication timestamp."
    )
    content: str = Field(
        ..., min_length=10, description="Article body text or summary."
    )
    raw_metadata: dict = Field(
        default_factory=dict,
        description="Any additional metadata from the news API.",
    )


class DisruptionEvent(BaseModel):
    """
    Structured disruption event extracted from a news article by the LLM.

    Contains normalized parameters that can be matched against Neo4j entities.
    """

    event_type: DisruptionType = Field(
        ..., description="Category of the disruption."
    )
    severity: SeverityLevel = Field(
        default=SeverityLevel.MEDIUM,
        description="Estimated impact severity.",
    )
    title: str = Field(
        ..., min_length=1, description="Short summary of the event."
    )
    description: str = Field(
        ..., min_length=10, description="Detailed description of the event."
    )
    locations: list[str] = Field(
        default_factory=list,
        description="Affected geographic locations (countries, cities, ports, regions).",
    )
    materials: list[str] = Field(
        default_factory=list,
        description="Affected materials, products, or commodities.",
    )
    affected_entities: list[str] = Field(
        default_factory=list,
        description="Names of specific companies or organizations mentioned.",
    )
    source_url: Optional[str] = Field(
        None, description="URL of the source article."
    )
    event_date: Optional[datetime] = Field(
        None, description="When the event occurred or was reported."
    )


class RiskParameters(BaseModel):
    """
    Distilled parameters extracted from a DisruptionEvent, used to
    query the Neo4j graph and find matching/impacted entities.
    """

    locations: list[str] = Field(
        default_factory=list,
        description="Normalized location names to match against graph nodes.",
    )
    materials: list[str] = Field(
        default_factory=list,
        description="Normalized material/product names to match against graph nodes.",
    )
    entity_names: list[str] = Field(
        default_factory=list,
        description="Specific company/org names to match against graph nodes.",
    )
    disruption_type: DisruptionType = Field(
        default=DisruptionType.OTHER,
        description="Type of disruption for risk scoring.",
    )
    severity: SeverityLevel = Field(
        default=SeverityLevel.MEDIUM,
        description="Severity for risk scoring.",
    )

    @property
    def all_search_terms(self) -> list[str]:
        """Combine all parameters into a flat search list."""
        return self.locations + self.materials + self.entity_names
