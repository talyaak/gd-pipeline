import subprocess
from types import SimpleNamespace

import pytest

from pipeline.playability_agent import PlayabilitySkipped, check_playability_agentic

SIMPLE_HTML = "<!DOCTYPE html><html><body>test</body></html>"


def _fake_serve_dir(directory):
    return SimpleNamespace(shutdown=lambda: None), 12345


def test_result_envelope_with_object_result(monkeypatch):
    monkeypatch.setattr("pipeline.playability_agent._serve_dir", _fake_serve_dir)
    envelope = '{"type": "result", "result": {"playable": true, "reasoning": "moved past start screen"}}'
    monkeypatch.setattr(
        "pipeline.playability_agent.subprocess.run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout=envelope, stderr=""),
    )
    result = check_playability_agentic(SIMPLE_HTML)
    assert result.playable is True
    assert "start screen" in result.reasoning


def test_result_envelope_with_string_result(monkeypatch):
    # Some CLI versions may return the schema-validated content as a JSON string
    # inside the "result" field rather than an already-parsed object.
    monkeypatch.setattr("pipeline.playability_agent._serve_dir", _fake_serve_dir)
    envelope = '{"type": "result", "result": "{\\"playable\\": false, \\"reasoning\\": \\"still frozen\\"}"}'
    monkeypatch.setattr(
        "pipeline.playability_agent.subprocess.run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout=envelope, stderr=""),
    )
    result = check_playability_agentic(SIMPLE_HTML)
    assert result.playable is False
    assert "frozen" in result.reasoning


def test_nonzero_exit_raises(monkeypatch):
    monkeypatch.setattr("pipeline.playability_agent._serve_dir", _fake_serve_dir)
    monkeypatch.setattr(
        "pipeline.playability_agent.subprocess.run",
        lambda *a, **kw: SimpleNamespace(returncode=1, stdout="", stderr="Credit balance is too low"),
    )
    with pytest.raises(RuntimeError, match="Credit balance"):
        check_playability_agentic(SIMPLE_HTML)


def test_timeout_raises(monkeypatch):
    monkeypatch.setattr("pipeline.playability_agent._serve_dir", _fake_serve_dir)

    def _timeout(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=180)

    monkeypatch.setattr("pipeline.playability_agent.subprocess.run", _timeout)
    with pytest.raises(RuntimeError, match="timed out"):
        check_playability_agentic(SIMPLE_HTML)


def test_unparseable_stdout_raises(monkeypatch):
    monkeypatch.setattr("pipeline.playability_agent._serve_dir", _fake_serve_dir)
    monkeypatch.setattr(
        "pipeline.playability_agent.subprocess.run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout="not json at all", stderr=""),
    )
    with pytest.raises(Exception):
        check_playability_agentic(SIMPLE_HTML)


def test_server_always_shut_down_even_on_failure(monkeypatch):
    shutdown_calls = []
    monkeypatch.setattr(
        "pipeline.playability_agent._serve_dir",
        lambda directory: (SimpleNamespace(shutdown=lambda: shutdown_calls.append(True)), 12345),
    )
    monkeypatch.setattr(
        "pipeline.playability_agent.subprocess.run",
        lambda *a, **kw: SimpleNamespace(returncode=1, stdout="", stderr="boom"),
    )
    with pytest.raises(RuntimeError):
        check_playability_agentic(SIMPLE_HTML)
    assert shutdown_calls == [True]


def test_claude_cli_missing_raises_playability_skipped(monkeypatch):
    """When `claude` CLI is not found, PlayabilitySkipped is raised (not a generic failure)."""
    monkeypatch.setattr("pipeline.playability_agent._serve_dir", _fake_serve_dir)

    def _file_not_found(*a, **kw):
        raise FileNotFoundError("[Errno 2] No such file or directory: 'claude'")

    monkeypatch.setattr("pipeline.playability_agent.subprocess.run", _file_not_found)
    with pytest.raises(PlayabilitySkipped, match="claude CLI not found"):
        check_playability_agentic(SIMPLE_HTML)
