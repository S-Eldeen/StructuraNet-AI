"""
llm_utils.py — Shared LLM utility functions for Structranet AI

Consolidates the duplicate _get_client(), _call_with_retry(), and _extract_json()
functions that were previously duplicated in ai_agent.py and config_agent.py.

This module is the SINGLE SOURCE OF TRUTH for OpenAI client initialization,
transient-error retry logic, and LLM JSON extraction across the entire pipeline.
"""

import json
import logging
import os
import re
import time
from typing import Optional

from dotenv import load_dotenv
from openai import (
    OpenAI,
    APITimeoutError,
    APIConnectionError,
    RateLimitError,
    InternalServerError,
)

load_dotenv()

logger = logging.getLogger("structranet.llm_utils")

# ═══════════════════════════════════════════════════════════════════════════════
#  Lazy singleton OpenAI client
# ═══════════════════════════════════════════════════════════════════════════════

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    """Return a lazily-initialized OpenAI client singleton.

    Reads ROUTER_API_KEY and ROUTER_BASE_URL from environment variables.
    Raises ValueError if the API key is missing.
    """
    global _client
    if _client is None:
        key = os.getenv("ROUTER_API_KEY")
        base_url = os.getenv("ROUTER_BASE_URL")
        if not key:
            raise ValueError("ROUTER_API_KEY missing. Check your .env file.")
        _client = OpenAI(base_url=base_url, api_key=key, timeout=500.0)
    return _client


# ═══════════════════════════════════════════════════════════════════════════════
#  Retry wrapper for transient API errors
# ═══════════════════════════════════════════════════════════════════════════════

def _call_with_retry(func, max_retries: int = 2):
    """Call *func* and retry on transient OpenAI errors.

    Exponential back-off: 2^attempt seconds between retries.
    Raises the last exception if all retries are exhausted.

    Parameters
    ----------
    func : callable
        A zero-argument callable that performs the OpenAI API call.
    max_retries : int
        Maximum number of attempts (default 2 = one initial + one retry).
    """
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except (APITimeoutError, APIConnectionError, RateLimitError, InternalServerError) as e:
            if attempt < max_retries:
                wait = 2 ** attempt
                logger.warning("Transient API error (attempt %d/%d): %s — retry in %ds",
                               attempt, max_retries, type(e).__name__, wait)
                time.sleep(wait)
            else:
                raise
    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  JSON extraction from messy LLM output
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_json(text: str) -> str:
    """Strip thought blocks and markdown fences, return raw JSON string.

    Handles three cases:
      1. Clean JSON (starts with '{', ends with '}')
      2. JSON wrapped in markdown code fences or preceded by <thought_process>
      3. JSON buried inside conversational text (regex rescue)
    """
    # Remove <thought_process>...</thought_process> blocks (some reasoning models)
    cleaned = re.sub(r"<thought_process>.*?</thought_process>", "",
                     text.strip(), flags=re.DOTALL)
    # Strip markdown code fences
    cleaned = re.sub(r"^```\w*\n?", "", cleaned.strip()).rstrip("`").strip()
    if cleaned.startswith("{") and cleaned.endswith("}"):
        return cleaned
    # Last resort: find outermost { ... } block
    match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
    return match.group(1) if match else text
