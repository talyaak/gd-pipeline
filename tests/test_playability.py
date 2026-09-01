import json
from types import SimpleNamespace

import pytest

from pipeline.playability import check_playability

FAKE_PNG = b"\x89PNG\r\n\x1a\nfake-bytes-for-testing"


class _FakeVisionLLM:
    def __init__(self, content):
        self._content = content

    def invoke(self, _messages):
        return SimpleNamespace(content=self._content)


def test_playable_verdict_parses(monkeypatch):
    monkeypatch.setattr(
        "pipeline.playability.get_review_llm",
        lambda **kw: _FakeVisionLLM(json.dumps({"playable": True, "reasoning": "game visibly progressed"})),
    )
    result = check_playability(FAKE_PNG, FAKE_PNG)
    assert result.playable is True
    assert "progressed" in result.reasoning


def test_unplayable_verdict_parses(monkeypatch):
    monkeypatch.setattr(
        "pipeline.playability.get_review_llm",
        lambda **kw: _FakeVisionLLM('{"playable": false, "reasoning": "still on start screen"}'),
    )
    result = check_playability(FAKE_PNG, FAKE_PNG)
    assert result.playable is False
    assert "start screen" in result.reasoning


def test_handles_list_style_content_blocks(monkeypatch):
    # Some Anthropic responses come back as a list of content blocks rather than
    # a plain string; the parser must handle both.
    monkeypatch.setattr(
        "pipeline.playability.get_review_llm",
        lambda **kw: _FakeVisionLLM([{"type": "text", "text": '{"playable": true, "reasoning": "ok"}'}]),
    )
    result = check_playability(FAKE_PNG, FAKE_PNG)
    assert result.playable is True


def test_unparseable_response_raises_not_silently_passes(monkeypatch):
    monkeypatch.setattr(
        "pipeline.playability.get_review_llm",
        lambda **kw: _FakeVisionLLM("I'm not sure, this is ambiguous."),
    )
    with pytest.raises(ValueError):
        check_playability(FAKE_PNG, FAKE_PNG)
