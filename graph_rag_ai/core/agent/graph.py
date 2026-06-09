"""
LangGraph Workflow Assembly
============================
Assembles the 4-node risk assessment agent as a LangGraph StateGraph.

Workflow:
    parse_query → query_graph → assess_risk → generate_report

Usage:
    from core.agent.graph import run_risk_agent
    from core.schemas.query import RiskAssessment

    result: RiskAssessment = run_risk_agent("Will the Suez Canal closure affect NordOil?")
"""

import logging
from typing import Optional

from langgraph.graph import END, StateGraph

from core.agent.nodes import (
    assess_risk,
    generate_report,
    parse_query,
    query_graph,
)
from core.agent.state import AgentState
from core.schemas.query import RiskAssessment, RiskLevel

logger = logging.getLogger(__name__)


def build_risk_agent() -> StateGraph:
    """
    Construct the LangGraph StateGraph for risk assessment.

    Returns a compiled graph ready to be invoked with an initial state.
    The workflow is a simple linear chain:

        parse_query → query_graph → assess_risk → generate_report → END
    """
    workflow = StateGraph(AgentState)

    # ── Add nodes ────────────────────────────────────────────────────
    workflow.add_node("parse_query", parse_query)
    workflow.add_node("query_graph", query_graph)
    workflow.add_node("assess_risk", assess_risk)
    workflow.add_node("generate_report", generate_report)

    # ── Define edges (linear chain) ──────────────────────────────────
    workflow.set_entry_point("parse_query")
    workflow.add_edge("parse_query", "query_graph")
    workflow.add_edge("query_graph", "assess_risk")
    workflow.add_edge("assess_risk", "generate_report")
    workflow.add_edge("generate_report", END)

    return workflow.compile()


# Module-level compiled graph (reused across invocations)
_compiled_agent = None


def _get_agent():
    """Lazy-initialize and cache the compiled agent."""
    global _compiled_agent
    if _compiled_agent is None:
        _compiled_agent = build_risk_agent()
        logger.info("LangGraph risk agent compiled successfully")
    return _compiled_agent


def run_risk_agent(query: str) -> RiskAssessment:
    """
    Run the full risk assessment agent pipeline for a user query.

    This is the primary entry point called by Django views.

    Args:
        query: The user's natural-language question about supply chain risk.

    Returns:
        A fully populated RiskAssessment with findings and recommendations.

    Example:
        >>> result = run_risk_agent("Will the Suez Canal closure affect NordOil?")
        >>> print(result.overall_risk_level)
        >>> print(result.summary)
    """
    agent = _get_agent()

    # Initialize the agent state
    initial_state: AgentState = {
        "raw_query": query,
        "parsed_params": None,
        "graph_results": {},
        "impacted_entities": [],
        "active_disruptions": [],
        "overall_risk_level": RiskLevel.NONE,
        "risk_assessment": None,
        "reasoning_trace": [],
        "errors": [],
    }

    logger.info("Running risk agent for query: '%s'", query)

    try:
        # Execute the full workflow
        final_state = agent.invoke(initial_state)

        assessment = final_state.get("risk_assessment")

        if assessment is not None:
            logger.info(
                "Agent completed: risk=%s, impacted=%d entities",
                assessment.overall_risk_level.value,
                len(assessment.impacted_entities),
            )
            return assessment

        # Should not reach here, but provide a fallback
        logger.warning("Agent returned no risk_assessment — building fallback")
        return RiskAssessment(
            query=query,
            overall_risk_level=RiskLevel.NONE,
            summary="The agent could not produce a risk assessment for this query.",
            recommendations=["Please rephrase your question and try again."],
            reasoning="\n".join(final_state.get("reasoning_trace", [])),
        )

    except Exception as e:
        logger.exception("Risk agent execution failed")
        return RiskAssessment(
            query=query,
            overall_risk_level=RiskLevel.NONE,
            summary=f"Risk assessment failed due to an internal error: {e}",
            recommendations=["Please try again later or contact support."],
        )
