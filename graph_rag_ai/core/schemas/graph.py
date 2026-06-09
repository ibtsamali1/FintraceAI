"""
Graph Entity & Relationship Schemas
=====================================
Pydantic v2 models for structured graph data extraction from documents.

These schemas enforce strict typing on LLM-extracted entity triplets
before they are ingested into Neo4j.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class EntityLabel(str, Enum):
    """Allowed node labels in the supply-chain knowledge graph."""
    COMPANY = "Company"
    SUPPLIER = "Supplier"
    FACTORY = "Factory"
    PORT = "Port"
    COUNTRY = "Country"
    CITY = "City"
    REGION = "Region"
    PRODUCT = "Product"
    VESSEL = "Vessel"
    PERSON = "Person"
    REGULATOR = "Regulator"
    ORGANIZATION = "Organization"
    AGREEMENT = "Agreement"
    BANK = "Bank"
    INSURER = "Insurer"
    INSURANCE = "Insurance"
    TERMINAL = "Terminal"
    FIELD = "Field"
    LOCATION = "Location"
    SUBSIDIARY = "Subsidiary"
    EXCHANGE = "Exchange"
    WATERWAY = "Waterway"
    FACILITY = "Facility"
    AUTHORITY = "Authority"
    REFINERY = "Refinery"
    SHIPOWNER = "Shipowner"
    MARKET = "Market"
    ROUTE = "Route"
    MATERIAL = "Material"
    ENTITY = "Entity"  # fallback


class RelationshipType(str, Enum):
    """Allowed relationship types between supply-chain entities."""
    SUPPLIES_TO = "SUPPLIES_TO"
    OWNS = "OWNS"
    OPERATES = "OPERATES"
    LOCATED_IN = "LOCATED_IN"
    PART_OF = "PART_OF"
    CONTRACTS_WITH = "CONTRACTS_WITH"
    REGULATED_BY = "REGULATED_BY"
    MANAGES = "MANAGES"
    TRANSPORTS_VIA = "TRANSPORTS_VIA"
    FINANCES = "FINANCES"
    INSPECTS = "INSPECTS"
    INSURES = "INSURES"
    PARTNERS_WITH = "PARTNERS_WITH"
    SUBSIDIARY_OF = "SUBSIDIARY_OF"
    FINANCED_BY = "FINANCED_BY"
    OWNED_BY = "OWNED_BY"
    RECEIVES_FROM = "RECEIVES_FROM"
    SCREENS = "SCREENS"
    REPORTS_TO = "REPORTS_TO"
    REGISTERED_IN = "REGISTERED_IN"
    RELATED_TO = "RELATED_TO"  # fallback
    AFFECTED_BY = "AFFECTED_BY"  # for news events


class EntityNode(BaseModel):
    """A single entity extracted from a document chunk."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="The canonical name of the entity.",
    )
    label: EntityLabel = Field(
        default=EntityLabel.ENTITY,
        description="The type/category of the entity in PascalCase.",
    )
    properties: dict[str, str] = Field(
        default_factory=dict,
        description="Optional additional properties for the node.",
    )

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        return v.strip()


class EntityRelationship(BaseModel):
    """A directed relationship between two entities."""

    from_node: str = Field(
        ...,
        min_length=1,
        description="Name of the source entity.",
    )
    to_node: str = Field(
        ...,
        min_length=1,
        description="Name of the target entity.",
    )
    rel_type: RelationshipType = Field(
        default=RelationshipType.RELATED_TO,
        description="The relationship type in UPPER_SNAKE_CASE.",
    )
    properties: dict[str, str] = Field(
        default_factory=dict,
        description="Optional additional properties for the relationship.",
    )

    @field_validator("from_node", "to_node")
    @classmethod
    def clean_node_name(cls, v: str) -> str:
        return v.strip()


class GraphExtractionResult(BaseModel):
    """
    Complete result of entity/relationship extraction from a text chunk.

    This is the exact schema the LLM is prompted to return.
    """

    nodes: list[EntityNode] = Field(
        default_factory=list,
        description="All entities extracted from the text.",
    )
    relationships: list[EntityRelationship] = Field(
        default_factory=list,
        description="All relationships extracted from the text.",
    )

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def relationship_count(self) -> int:
        return len(self.relationships)

    def get_node_names(self) -> set[str]:
        """Return the set of all entity names."""
        return {n.name for n in self.nodes}
