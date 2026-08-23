from langchain_anthropic import ChatAnthropic

from config import ANTHROPIC_API_KEY, GENERATION_MODEL, REVIEW_MODEL


def get_generation_llm(temperature: float = 0.7, max_tokens: int = 8192) -> ChatAnthropic:
    return ChatAnthropic(model=GENERATION_MODEL, api_key=ANTHROPIC_API_KEY, temperature=temperature, max_tokens=max_tokens)


def get_review_llm(temperature: float = 0.0) -> ChatAnthropic:
    return ChatAnthropic(model=REVIEW_MODEL, api_key=ANTHROPIC_API_KEY, temperature=temperature, max_tokens=2048)
