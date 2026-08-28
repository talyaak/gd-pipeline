import os

from pipeline.cost_tracker import CostTrackingCallback

from config import (
    ANTHROPIC_API_KEY,
    GENERATION_MODEL_ANTHROPIC,
    GENERATION_MODEL_OPENROUTER,
    LLM_PROVIDER,
    REVIEW_MODEL_ANTHROPIC,
    REVIEW_MODEL_OPENROUTER,
)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", ANTHROPIC_API_KEY)


def _generation_llm_openrouter(temperature: float, max_tokens: int, node: str):
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=GENERATION_MODEL_OPENROUTER,
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        temperature=temperature,
        max_tokens=max_tokens,
        callbacks=[CostTrackingCallback(node)],
    )


def _review_llm_openrouter(temperature: float, node: str):
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=REVIEW_MODEL_OPENROUTER,
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        temperature=temperature,
        max_tokens=2048,
        callbacks=[CostTrackingCallback(node)],
    )


def _generation_llm_anthropic(temperature: float, max_tokens: int, node: str):
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=GENERATION_MODEL_ANTHROPIC,
        api_key=ANTHROPIC_API_KEY,
        temperature=temperature,
        max_tokens=max_tokens,
        callbacks=[CostTrackingCallback(node)],
    )


def _review_llm_anthropic(temperature: float, node: str):
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=REVIEW_MODEL_ANTHROPIC,
        api_key=ANTHROPIC_API_KEY,
        temperature=temperature,
        max_tokens=2048,
        callbacks=[CostTrackingCallback(node)],
    )


_PROVIDERS = {
    "anthropic": (_generation_llm_anthropic, _review_llm_anthropic),
    "openrouter": (_generation_llm_openrouter, _review_llm_openrouter),
}


def get_generation_llm(temperature: float = 0.7, max_tokens: int = 8192, node: str = "generation"):
    try:
        generation_fn, _ = _PROVIDERS[LLM_PROVIDER]
    except KeyError:
        raise ValueError(f"Unknown LLM_PROVIDER {LLM_PROVIDER!r}; must be one of {list(_PROVIDERS)}")
    return generation_fn(temperature, max_tokens, node)


def get_review_llm(temperature: float = 0.0, node: str = "review"):
    try:
        _, review_fn = _PROVIDERS[LLM_PROVIDER]
    except KeyError:
        raise ValueError(f"Unknown LLM_PROVIDER {LLM_PROVIDER!r}; must be one of {list(_PROVIDERS)}")
    return review_fn(temperature, node)
