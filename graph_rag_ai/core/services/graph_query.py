"""
Graph Query Engine
==================
Service functions to query the Neo4j supply-chain knowledge graph.

All functions use the shared Neo4j connection from neo4j_connection.py.
They return plain Python dicts/lists so views can serialize them to JSON.

Functions:
    get_node              — Find a single node by name
    get_neighbors         — Get directly connected nodes
    find_path             — Shortest path between two nodes
    find_impacted_entities — Traverse graph to find all entities impacted
                             when a given node is disrupted
    query_graph           — Execute arbitrary Cypher (power-user)
    get_all_nodes         — List all nodes, optionally filtered by label
    get_all_relationships — List all relationships
    get_graph_statistics  — Node/relationship counts by type
"""

import logging
from typing import Optional

from core.services.neo4j_connection import get_session

logger = logging.getLogger(__name__)


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────

def _node_to_dict(node):
    """Convert a Neo4j Node object to a plain dict."""
    return {
        "id": node.element_id,
        "labels": list(node.labels),
        "properties": dict(node),
    }


def _relationship_to_dict(rel):
    """Convert a Neo4j Relationship object to a plain dict."""
    return {
        "id": rel.element_id,
        "type": rel.type,
        "from": _node_to_dict(rel.start_node),
        "to": _node_to_dict(rel.end_node),
        "properties": dict(rel),
    }


# ───────────────────────────────────────────────────────────────────────────
# Core Query Functions
# ───────────────────────────────────────────────────────────────────────────

def get_node(name: str, label: Optional[str] = None) -> Optional[dict]:
    """
    Find a single node by its `name` property.

    Args:
        name:  Exact name of the node (case-sensitive).
        label: Optional label to narrow the search (e.g. "Company").

    Returns:
        Dict with node data, or None if not found.
    """
    if label:
        cypher = "MATCH (n {name: $name}) WHERE $label IN labels(n) RETURN n LIMIT 1"
        params = {"name": name, "label": label}
    else:
        cypher = "MATCH (n {name: $name}) RETURN n LIMIT 1"
        params = {"name": name}

    with get_session() as session:
        result = session.run(cypher, params)
        record = result.single()

    if record is None:
        logger.debug("Node not found: name=%s label=%s", name, label)
        return None

    return _node_to_dict(record["n"])


def get_neighbors(
    name: str,
    direction: str = "both",
    rel_type: Optional[str] = None,
    limit: int = 50,
    query_timeout: int = 30,
) -> dict:
    """
    Get all nodes directly connected to the node with the given name.

    Args:
        name:      Name of the center node.
        direction: "outgoing", "incoming", or "both" (default).
        rel_type:  Optional relationship type filter (e.g. "SUPPLIES_TO").
        limit:     Max neighbors to return (default 50).

    Returns:
        Dict with "center_node" and list of "neighbors", each containing
        the neighbor node and the connecting relationship.
    """
    # Build relationship pattern based on direction
    rel_pattern = f"[r:{rel_type}]" if rel_type else "[r]"

    if direction == "outgoing":
        pattern = f"(center)-{rel_pattern}->(neighbor)"
    elif direction == "incoming":
        pattern = f"(center)<-{rel_pattern}-(neighbor)"
    else:
        pattern = f"(center)-{rel_pattern}-(neighbor)"

    cypher = (
        f"MATCH {pattern} "
        f"WHERE center.name = $name "
        f"RETURN center, r, neighbor "
        f"LIMIT $limit"
    )

    neighbors = []
    center_node = None

    with get_session() as session:
        result = session.run(cypher, name=name, limit=limit)

        for record in result:
            if center_node is None:
                center_node = _node_to_dict(record["center"])

            neighbors.append({
                "node": _node_to_dict(record["neighbor"]),
                "relationship": {
                    "type": record["r"].type,
                    "properties": dict(record["r"]),
                },
            })

    if center_node is None:
        # Node exists but has no neighbors, or doesn't exist
        center_node = get_node(name)

    return {
        "center_node": center_node,
        "neighbors": neighbors,
        "count": len(neighbors),
    }


def find_path(from_name: str, to_name: str, max_depth: int = 10) -> Optional[dict]:
    """
    Find the shortest path between two nodes (by name).

    Uses Neo4j's built-in shortestPath algorithm, which is efficient
    even on large graphs. Includes query timeout protection.

    Args:
        from_name: Name of the start node.
        to_name:   Name of the end node.
        max_depth: Maximum path length to search (default 10).

    Returns:
        Dict with "nodes" and "relationships" along the path,
        or None if no path exists.
    """
    cypher = (
        "MATCH (a {name: $from_name}), (b {name: $to_name}), "
        f"p = shortestPath((a)-[*..{max_depth}]-(b)) "
        "RETURN p"
    )

    try:
        with get_session() as session:
            result = session.run(cypher, from_name=from_name, to_name=to_name)
            record = result.single()
    except Exception as e:
        logger.warning("Path search failed: %s", e)
        return None

    if record is None:
        logger.debug("No path found between '%s' and '%s'", from_name, to_name)
        return None

    path = record["p"]

    path_nodes = [_node_to_dict(node) for node in path.nodes]
    path_rels = []
    for rel in path.relationships:
        path_rels.append({
            "type": rel.type,
            "from": rel.start_node["name"],
            "to": rel.end_node["name"],
            "properties": dict(rel),
        })

    return {
        "nodes": path_nodes,
        "relationships": path_rels,
        "length": len(path_rels),
    }


def find_impacted_entities(
    name: str,
    max_depth: int = 5,
    direction: str = "both",
    query_timeout: int = 30,
    limit: int = 1000,
) -> dict:
    """
    Find all entities that would be impacted if the given node is disrupted.

    Performs a variable-length path traversal from the source node to
    discover all transitively connected entities within max_depth hops.

    Example:
        If graph contains: Supplier A -> Factory B -> Product C
        And Supplier A is disrupted, this returns:
        [Supplier A, Factory B, Product C]

    Args:
        name:           Name of the disrupted/affected node.
        max_depth:      How many hops to traverse (default 5).
        direction:      "outgoing" (downstream), "incoming" (upstream),
                        or "both" (default).
        query_timeout:  Max seconds to wait for Neo4j query (default 30).
        limit:          Max results to return (default 1000).

    Returns:
        Dict with "source" node, list of "impacted" entities grouped
        by depth, and total "count".
    """
    # Build traversal pattern based on direction
    if direction == "outgoing":
        pattern = f"(source)-[r*1..{max_depth}]->(target)"
    elif direction == "incoming":
        pattern = f"(source)<-[r*1..{max_depth}]-(target)"
    else:
        pattern = f"(source)-[r*1..{max_depth}]-(target)"

    cypher = (
        f"MATCH p = {pattern} "
        f"WHERE source.name = $name "
        f"WITH target, min(length(p)) AS depth, "
        f"     collect(DISTINCT [rel IN relationships(p) | type(rel)]) AS paths "
        f"RETURN target, depth, paths "
        f"ORDER BY depth "
        f"LIMIT $limit"
    )

    source_node = get_node(name)
    if source_node is None:
        return {
            "source": None,
            "impacted": [],
            "count": 0,
            "error": f"Node '{name}' not found",
        }

    impacted = []
    seen_ids = set()

    try:
        with get_session() as session:
            result = session.run(cypher, name=name, limit=limit)

            for record in result:
                target = record["target"]
                target_id = target.element_id

                # Deduplicate — a node may appear via multiple paths
                if target_id in seen_ids:
                    continue
                seen_ids.add(target_id)

                impacted.append({
                    "node": _node_to_dict(target),
                    "depth": record["depth"],
                    "relationship_chain": record["paths"][0] if record["paths"] else [],
                })
    except Exception as e:
        logger.warning("Graph traversal for '%s' failed: %s (returning partial results)", name, e)

    return {
        "source": source_node,
        "impacted": impacted,
        "count": len(impacted),
        "max_depth_searched": max_depth,
        "direction": direction,
        "limit_enforced": len(impacted) >= limit,
    }


def query_graph(cypher: str, params: Optional[dict] = None) -> list:
    """
    Execute an arbitrary Cypher query and return all records as dicts.

    This is a power-user / admin function. Use with caution.

    Args:
        cypher: A valid Cypher query string.
        params: Optional parameter dict for parameterised queries.

    Returns:
        List of dicts, one per result record.
    """
    if params is None:
        params = {}

    with get_session() as session:
        result = session.run(cypher, params)
        records = []
        for record in result:
            row = {}
            for key in record.keys():
                value = record[key]
                # Convert Neo4j types to serializable dicts
                if hasattr(value, "labels"):
                    row[key] = _node_to_dict(value)
                elif hasattr(value, "type") and hasattr(value, "start_node"):
                    row[key] = _relationship_to_dict(value)
                else:
                    row[key] = value
            records.append(row)

    return records


def get_all_nodes(label: Optional[str] = None, limit: int = 100) -> list:
    """
    Return all nodes, optionally filtered by label.

    Args:
        label: Optional node label filter (e.g. "Company", "Port").
        limit: Maximum nodes to return (default 100).

    Returns:
        List of node dicts.
    """
    if label:
        cypher = f"MATCH (n:{label}) RETURN n LIMIT $limit"
    else:
        cypher = "MATCH (n) RETURN n LIMIT $limit"

    with get_session() as session:
        result = session.run(cypher, limit=limit)
        return [_node_to_dict(record["n"]) for record in result]


def get_all_relationships(limit: int = 100) -> list:
    """
    Return all relationships in the graph.

    Args:
        limit: Maximum relationships to return (default 100).

    Returns:
        List of relationship dicts.
    """
    cypher = "MATCH (a)-[r]->(b) RETURN a, r, b LIMIT $limit"

    with get_session() as session:
        result = session.run(cypher, limit=limit)
        relationships = []
        for record in result:
            relationships.append({
                "from": _node_to_dict(record["a"]),
                "relationship": record["r"].type,
                "to": _node_to_dict(record["b"]),
            })
        return relationships


def get_graph_statistics() -> dict:
    """
    Return summary statistics about the graph.

    Returns:
        Dict with:
        - total_nodes: int
        - total_relationships: int
        - nodes_by_label: dict[str, int]
        - relationships_by_type: dict[str, int]
    """
    stats = {}

    with get_session() as session:
        # Total node count
        result = session.run("MATCH (n) RETURN count(n) AS cnt")
        stats["total_nodes"] = result.single()["cnt"]

        # Total relationship count
        result = session.run("MATCH ()-[r]->() RETURN count(r) AS cnt")
        stats["total_relationships"] = result.single()["cnt"]

        # Nodes grouped by label
        result = session.run(
            "MATCH (n) UNWIND labels(n) AS label "
            "RETURN label, count(*) AS cnt ORDER BY cnt DESC"
        )
        stats["nodes_by_label"] = {
            record["label"]: record["cnt"] for record in result
        }

        # Relationships grouped by type
        result = session.run(
            "MATCH ()-[r]->() "
            "RETURN type(r) AS rel_type, count(*) AS cnt ORDER BY cnt DESC"
        )
        stats["relationships_by_type"] = {
            record["rel_type"]: record["cnt"] for record in result
        }

    return stats
