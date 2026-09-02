"""Regression test for a real bug: get_review_llm unpacked the wrong element of
the _PROVIDERS tuple (generation fn instead of review fn), so under
LLM_PROVIDER=openrouter every review-tier call crashed instantly with
TypeError: _generation_llm_openrouter() missing 1 required positional
argument: 'node' — before ever making a network call. Caught live via a
free-tier generation test that died on the very first node (research, which
uses get_review_llm)."""
import pipeline.llm as llm


def test_get_review_llm_calls_the_review_function_not_generation(monkeypatch):
    calls = []

    def fake_review_openrouter(temperature, node):
        calls.append(("review_openrouter", temperature, node))
        return "review-llm"

    def fake_generation_openrouter(temperature, max_tokens, node):
        calls.append(("generation_openrouter", temperature, max_tokens, node))
        return "generation-llm"

    monkeypatch.setattr(llm, "_review_llm_openrouter", fake_review_openrouter)
    monkeypatch.setattr(llm, "_generation_llm_openrouter", fake_generation_openrouter)
    monkeypatch.setattr(
        llm, "_PROVIDERS",
        {
            "anthropic": (llm._generation_llm_anthropic, llm._review_llm_anthropic),
            "openrouter": (fake_generation_openrouter, fake_review_openrouter),
        },
    )
    monkeypatch.setattr(llm, "LLM_PROVIDER", "openrouter")

    result = llm.get_review_llm(temperature=0.2, node="research")

    assert result == "review-llm"
    assert calls == [("review_openrouter", 0.2, "research")]


def test_get_generation_llm_calls_the_generation_function(monkeypatch):
    calls = []

    def fake_generation_openrouter(temperature, max_tokens, node):
        calls.append((temperature, max_tokens, node))
        return "generation-llm"

    monkeypatch.setattr(
        llm, "_PROVIDERS",
        {
            "anthropic": (llm._generation_llm_anthropic, llm._review_llm_anthropic),
            "openrouter": (fake_generation_openrouter, llm._review_llm_openrouter),
        },
    )
    monkeypatch.setattr(llm, "LLM_PROVIDER", "openrouter")

    result = llm.get_generation_llm(temperature=0.5, max_tokens=1234, node="codegen")

    assert result == "generation-llm"
    assert calls == [(0.5, 1234, "codegen")]
