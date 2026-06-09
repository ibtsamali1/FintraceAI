"""
LLM Service Factory
====================
Centralized factory for LLM instances used across FinTrace.

Uses OpenAI gpt-4o-mini for cloud-based inference with native
tool-calling and structured output support.

Provides pre-configured ChatOpenAI instances for different use cases:
- Entity extraction (temperature=0, deterministic structured output)
- Agent reasoning (temperature=0.3, conversational)

Usage:
    from core.services.llm import get_extraction_llm, get_reasoning_llm

    llm = get_extraction_llm()
    result = llm.invoke(messages)
"""

import logging
from functools import lru_cache

from langchain_openai import ChatOpenAI

from core.config import OPENAI_API_KEY

logger = logging.getLogger(__name__)


def _validate_api_key() -> str:
    """Return the OpenAI API key, raising if not configured."""
    if not OPENAI_API_KEY:
        raise ValueError(
            "OPENAI_API_KEY is not set. "
            "Add it to your .env file: OPENAI_API_KEY=sk-..."
        )
    return OPENAI_API_KEY


@lru_cache(maxsize=1)
def get_extraction_llm() -> ChatOpenAI:
    """
    Return a ChatOpenAI instance optimised for structured entity extraction.

    - model: gpt-4o-mini (fast, cost-effective, supports tool calling)
    - temperature=0 for deterministic, reproducible output
    - max_tokens=4096 for entity extraction responses
    - Cached — only one instance per process
    """
    api_key = _validate_api_key()
    logger.info(
        "Initialising extraction LLM: gpt-4o-mini (temperature=0, max_tokens=4096)"
    )
    return ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0,
        max_tokens=4096,
        api_key=api_key,
        request_timeout=60.0,
    )


@lru_cache(maxsize=1)
def get_reasoning_llm() -> ChatOpenAI:
    """
    Return a ChatOpenAI instance optimised for agent reasoning and reports.

    - model: gpt-4o-mini
    - temperature=0.3 for slightly creative, natural-language output
    - max_tokens=4096 for report generation
    - Cached — only one instance per process
    """
    api_key = _validate_api_key()
    logger.info(
        "Initialising reasoning LLM: gpt-4o-mini (temperature=0.3, max_tokens=4096)"
    )
    return ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.3,
        max_tokens=4096,
        api_key=api_key,
        request_timeout=90.0,
    )
