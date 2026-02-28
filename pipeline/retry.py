"""Retry logic for LLM API calls to handle transient network errors."""

import time

from openai import APIConnectionError

MAX_RETRIES = 3
INITIAL_BACKOFF = 2  # seconds


def invoke_with_retry(structured_llm, prompt, *, max_retries: int = MAX_RETRIES):
    """Invoke structured LLM with retries on connection errors.

    Handles transient network failures (DNS, connection refused, timeouts)
    with exponential backoff.
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            return structured_llm.invoke(prompt)
        except APIConnectionError as e:
            last_error = e
            if attempt == max_retries - 1:
                raise
            wait = INITIAL_BACKOFF ** attempt
            print(
                f"  [retry] Connection failed, retrying in {wait}s "
                f"({attempt + 1}/{max_retries})"
            )
            time.sleep(wait)
    raise last_error

