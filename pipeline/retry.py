import time
from typing import Callable, TypeVar

from anthropic import APIConnectionError, APITimeoutError, RateLimitError

from config import RETRY_BASE_DELAY_SECONDS, RETRY_MAX_ATTEMPTS

T = TypeVar("T")

RETRYABLE_EXCEPTIONS = (APIConnectionError, APITimeoutError, RateLimitError)


def invoke_with_retry(fn: Callable[[], T]) -> T:
    last_exc: Exception | None = None
    for attempt in range(RETRY_MAX_ATTEMPTS):
        try:
            return fn()
        except RETRYABLE_EXCEPTIONS as exc:
            last_exc = exc
            if attempt < RETRY_MAX_ATTEMPTS - 1:
                time.sleep(RETRY_BASE_DELAY_SECONDS * (2**attempt))
    raise last_exc
