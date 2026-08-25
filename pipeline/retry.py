import asyncio
import time
from dataclasses import dataclass
from typing import Callable, TypeVar, Optional, Any
from enum import Enum

from openai import APIConnectionError, APITimeoutError, RateLimitError, BadRequestError, InternalServerError
from config import RETRY_BASE_DELAY_SECONDS, RETRY_MAX_ATTEMPTS

T = TypeVar("T")


class ErrorCategory(Enum):
    """Categorized errors for targeted rework."""
    TRANSIENT = "transient"           # Network, rate limit - retry same prompt
    TRUNCATION = "truncation"         # Hit max_tokens - need larger limit or shorter prompt
    SYNTAX = "syntax"                 # Invalid HTML/JS - static validation catchable
    MRAID = "mraid"                   # MRAID integration issues
    SEMANTIC = "semantic"             # Game logic wrong - needs design rework
    VALIDATION = "validation"         # Static validation failures
    UNKNOWN = "unknown"               # Unclassified


@dataclass
class PipelineError(Exception):
    """Structured pipeline error with category and recovery hints."""
    category: ErrorCategory
    message: str
    recoverable: bool = True
    hint: Optional[str] = None
    node: Optional[str] = None
    attempt: int = 0
    raw_error: Optional[Exception] = None

    def __str__(self):
        return f"[{self.category.value}] {self.message}"


RETRYABLE_EXCEPTIONS = (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)
NON_RETRYABLE_EXCEPTIONS = (BadRequestError,)  # Schema violations, invalid params


def categorize_error(exc: Exception, node: str = "") -> PipelineError:
    """Classify exception into category with recovery hint."""
    msg = str(exc).lower()
    
    # Transient network/LLM issues
    if isinstance(exc, RETRYABLE_EXCEPTIONS):
        return PipelineError(
            category=ErrorCategory.TRANSIENT,
            message=f"Transient {type(exc).__name__}: {exc}",
            recoverable=True,
            hint="Retry with exponential backoff",
            node=node,
        )
    
    # Non-retryable API errors
    if isinstance(exc, BadRequestError):
        if "max_tokens" in msg or "length" in msg or "truncat" in msg:
            return PipelineError(
                category=ErrorCategory.TRUNCATION,
                message=f"Token limit exceeded: {exc}",
                recoverable=True,
                hint="Reduce prompt size or increase max_tokens",
                node=node,
            )
        return PipelineError(
            category=ErrorCategory.SYNTAX,
            message=f"Invalid request: {exc}",
            recoverable=False,
            hint="Fix prompt structure or schema",
            node=node,
        )
    
    # Static validation errors
    if "static validation" in msg or "asset" in msg or "deltaTime" in msg or "doctype" in msg:
        return PipelineError(
            category=ErrorCategory.VALIDATION,
            message=f"Static validation failed: {exc}",
            recoverable=True,
            hint="Fix code generation output",
            node=node,
        )
    
    # MRAID errors
    if "mraid" in msg:
        return PipelineError(
            category=ErrorCategory.MRAID,
            message=f"MRAID validation failed: {exc}",
            recoverable=True,
            hint="Fix MRAID integration (ready event, CTA button, open handler)",
            node=node,
        )
    
    # Semantic/runtime errors
    if "semantic" in msg or "gameover" in msg or "score" in msg or "scene" in msg or "cta" in msg:
        return PipelineError(
            category=ErrorCategory.SEMANTIC,
            message=f"Semantic validation failed: {exc}",
            recoverable=True,
            hint="Fix game logic / MRAID integration",
            node=node,
        )
    
    return PipelineError(
        category=ErrorCategory.UNKNOWN,
        message=f"Unclassified error: {exc}",
        recoverable=True,
        hint="Inspect logs and retry",
        node=node,
        raw_error=exc,
    )


async def invoke_with_timeout(
    fn: Callable[[], T],
    timeout_seconds: float,
    node: str = ""
) -> T:
    """Execute function with timeout."""
    try:
        if asyncio.iscoroutinefunction(fn):
            return await asyncio.wait_for(fn(), timeout=timeout_seconds)
        else:
            # Run sync function in thread pool
            return await asyncio.wait_for(
                asyncio.to_thread(fn),
                timeout=timeout_seconds
            )
    except asyncio.TimeoutError:
        raise PipelineError(
            category=ErrorCategory.UNKNOWN,
            message=f"Node '{node}' timed out after {timeout_seconds}s",
            recoverable=True,
            hint=f"Increase timeout or optimize {node} logic",
            node=node,
        )


def invoke_with_retry(
    fn: Callable[[], T],
    node: str = "",
    timeout_seconds: float = 120.0,
    max_attempts: int = RETRY_MAX_ATTEMPTS,
) -> T:
    """
    Execute function with retry logic, timeout, and error categorization.
    
    Args:
        fn: Function to execute
        node: Pipeline node name for error context
        timeout_seconds: Per-attempt timeout
        max_attempts: Maximum retry attempts
    
    Returns:
        Function result
    
    Raises:
        PipelineError: Categorized error with recovery info
    """
    last_error: Optional[PipelineError] = None
    
    for attempt in range(max_attempts):
        try:
            # Run with timeout
            if asyncio.iscoroutinefunction(fn):
                result = asyncio.run(invoke_with_timeout(fn, timeout_seconds, node))
            else:
                result = asyncio.run(invoke_with_timeout(lambda: fn(), timeout_seconds, node))
            return result
            
        except PipelineError as pe:
            pe.attempt = attempt + 1
            pe.node = node
            last_error = pe
            
            if not pe.recoverable or attempt == max_attempts - 1:
                raise
            
            # Exponential backoff
            delay = RETRY_BASE_DELAY_SECONDS * (2 ** attempt)
            time.sleep(delay)
            
        except Exception as exc:
            pe = categorize_error(exc, node)
            pe.attempt = attempt + 1
            last_error = pe
            
            if not pe.recoverable or attempt == max_attempts - 1:
                raise pe
            
            delay = RETRY_BASE_DELAY_SECONDS * (2 ** attempt)
            time.sleep(delay)
    
    # Should not reach here, but safety net
    raise last_error or PipelineError(
        category=ErrorCategory.UNKNOWN,
        message=f"All {max_attempts} attempts failed for node '{node}'",
        recoverable=False,
        node=node,
    )


# Per-node timeout configuration
NODE_TIMEOUTS = {
    "research": 60,
    "design": 60,
    "spec": 120,
    "codegen": 180,
    "validate_execute": 120,
    "review": 60,
    "variant_gen": 180,
}

# Per-node max attempts
NODE_MAX_ATTEMPTS = {
    "research": 2,
    "design": 3,
    "spec": 2,
    "codegen": 3,
    "validate_execute": 2,
    "review": 2,
    "variant_gen": 1,  # Variants don't retry
}