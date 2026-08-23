from langchain_openai import ChatOpenAI

from config import ANTHROPIC_API_KEY, GENERATION_MODEL, REVIEW_MODEL
import os

# OpenRouter configuration
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", ANTHROPIC_API_KEY)


def get_generation_llm(temperature: float = 0.7, max_tokens: int = 8192) -> ChatOpenAI:
    return ChatOpenAI(
        model=GENERATION_MODEL,
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def get_review_llm(temperature: float = 0.0) -> ChatOpenAI:
    return ChatOpenAI(
        model=REVIEW_MODEL,
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        temperature=temperature,
        max_tokens=2048,
    )
