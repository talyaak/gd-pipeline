"""Retry logic for LLM API calls to handle transient network errors."""

import time

from openai import APIConnectionError, APITimeoutError, RateLimitError
from pydantic import ValidationError

MAX_RETRIES = 3
INITIAL_BACKOFF = 2  # seconds


def invoke_with_retry(structured_llm, prompt, *, max_retries: int = MAX_RETRIES):
    """Invoke structured LLM with retries on connection errors.

    Handles transient network failures (DNS, connection refused, timeouts,
    rate limits) with exponential backoff. Pydantic validation errors from
    malformed/partial tool args (a known free-tier model failure mode) are
    retried and, if never corrected, surface as a None return so call-site
    fallbacks engage instead of crashing the run.
    """
    for attempt in range(max_retries):
        try:
            return structured_llm.invoke(prompt)
        except (APIConnectionError, APITimeoutError, RateLimitError) as e:
            if attempt == max_retries - 1:
                raise
            wait = INITIAL_BACKOFF * (2 ** attempt)
            print(
                f"  [retry] {type(e).__name__}, retrying in {wait}s "
                f"({attempt + 1}/{max_retries})"
            )
            time.sleep(wait)
        except ValidationError as e:
            wait = INITIAL_BACKOFF * (2 ** attempt)
            if attempt == max_retries - 1:
                print(f"  [retry] ValidationError after {max_retries} attempts, giving up: {str(e)[:200]}")
                return None
            print(
                f"  [retry] ValidationError (partial tool args), retrying in {wait}s "
                f"({attempt + 1}/{max_retries})"
            )
            time.sleep(wait)

