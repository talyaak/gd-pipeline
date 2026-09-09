"""Agentic playability check.

Every other execution check is a technical proxy a genuinely broken game can
still satisfy (canvas has pixels, a screenshot diff registered, a registry
number ticked up) -- confirmed by hand on a run that passed all of them and
never left its own start screen after 25+ seconds of real input. A
vision-on-two-screenshots check (pipeline/playability.py) closes some of that
gap, but it's still a single judgment call on two static frames, not genuine
interaction.

This module goes further: it hands the served game to a real headless Claude
Code agent (`claude -p`) with actual Playwright browser tool access (via
@playwright/mcp, not just vision), and asks it to open the game and play with
it like a person would -- multiple actions, watching what happens between
them -- then give a verdict. This is the same kind of check a human glancing
at (and clicking around in) the game would make, automated.
"""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from pipeline.execute import _serve_dir
from pipeline.schemas import PlayabilityReport

MCP_CONFIG_PATH = Path(__file__).parent / "vendor" / "mcp-playwright.json"

ALLOWED_TOOLS = ",".join([
    "mcp__playwright__browser_navigate",
    "mcp__playwright__browser_click",
    "mcp__playwright__browser_press_key",
    "mcp__playwright__browser_take_screenshot",
    "mcp__playwright__browser_snapshot",
    "mcp__playwright__browser_wait_for",
    "mcp__playwright__browser_drag",
])

PLAYABILITY_AGENT_PROMPT = """Open {url} in the browser using the playwright tools. This is an automated test of an HTML5 game meant to run as a mobile ad playable.

Actually play it like a real person would for about 15-20 seconds: press arrow keys and space, click/tap the canvas a few times, try a drag if it looks relevant to the game, and watch what happens between actions -- take more than one screenshot/snapshot over time, don't judge from a single glance.

Then judge ONE thing: is this a genuinely playable game -- did it visibly leave its start/menu/tutorial screen, is there a responsive player-controlled element, does anything change in response to your input? Not whether it's pretty, not whether it matches a design spec.

Be skeptical and literal. If it's still sitting on start-screen instructions after you've tried to interact with it, or you can't tell whether anything actually happened, that is NOT playable -- a false pass here ships a broken game to a real ad placement; a false fail just costs one retry.

Give your final verdict as playable true/false with reasoning specific to what you actually saw happen (or didn't) during your interaction."""

RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "playable": {"type": "boolean"},
        "reasoning": {"type": "string"},
    },
    "required": ["playable", "reasoning"],
}

DEFAULT_TIMEOUT_SECONDS = 180
DEFAULT_MAX_BUDGET_USD = 0.50


class PlayabilitySkipped(Exception):
    """Raised when the playability check cannot run because the `claude` CLI is not available.

    This is distinct from a failure -- it means the check was SKIPPED, not that it ran and failed.
    """
    pass


def check_playability_agentic(
    html: str,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    max_budget_usd: float = DEFAULT_MAX_BUDGET_USD,
) -> PlayabilityReport:
    """Serves `html` locally and has a real headless Claude Code agent (with
    genuine Playwright browser tool access, not just vision-on-screenshots)
    open it and interact with it, returning its verdict.

    Raises on any failure (subprocess error, timeout, unparseable output,
    non-zero exit) -- never silently treated as a pass. This matches how a
    missing `node` binary is handled in validate.py's syntax check: an
    unavailable check is not the same as a passed one.

    Raises PlayabilitySkipped if the `claude` CLI binary is not found.
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="playability_agent_"))
    (tmp_dir / "game.html").write_text(html, encoding="utf-8")
    httpd, port = _serve_dir(tmp_dir)
    try:
        url = f"http://127.0.0.1:{port}/game.html"
        cmd = [
            "claude", "-p", PLAYABILITY_AGENT_PROMPT.format(url=url),
            "--mcp-config", str(MCP_CONFIG_PATH),
            "--strict-mcp-config",
            "--allowedTools", ALLOWED_TOOLS,
            "--dangerously-skip-permissions",
            "--output-format", "json",
            "--json-schema", json.dumps(RESULT_SCHEMA),
            "--max-budget-usd", str(max_budget_usd),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds)
        except FileNotFoundError:
            raise PlayabilitySkipped("claude CLI not found in PATH; playability check skipped") from None
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"playability agent timed out after {timeout_seconds}s") from exc
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()[:500]
            raise RuntimeError(f"playability agent invocation failed (exit {proc.returncode}): {detail}")
        report = _parse_agent_output(proc.stdout)
        # Log cost if available in the response envelope
        _log_playability_cost_from_envelope(proc.stdout)
        return report
    finally:
        httpd.shutdown()
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _parse_agent_output(stdout: str) -> PlayabilityReport:
    """`--output-format json` wraps the final answer in a result envelope; the
    actual (schema-validated) content lives in its "result" field, which may
    already be a parsed object or still a JSON-encoded string depending on
    CLI version -- this has not been observed live yet (blocked on funding),
    so it deliberately handles both shapes rather than assuming one."""
    envelope = json.loads(stdout)
    result = envelope.get("result", envelope) if isinstance(envelope, dict) else envelope
    if isinstance(result, str):
        result = json.loads(result)
    return PlayabilityReport(**result)


def _log_playability_cost(model: str, cost_usd: float) -> None:
    """Write a cost log entry for the playability agent, mirroring CostTrackingCallback format."""
    import time
    from pipeline.cost_tracker import LOG_PATH
    entry = {
        "ts": time.time(),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "node": "playability_agent",
        "model": model,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": round(cost_usd, 6),
        "anomaly": False,
        "anomaly_reason": None,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _log_playability_cost_from_envelope(stdout: str) -> None:
    """Extract cost info from claude CLI JSON output envelope and log it."""
    try:
        envelope = json.loads(stdout)
        # The claude CLI with --output-format json returns an envelope with
        # cost info at top level: {"type": "result", "result": {...}, "cost_usd": 0.123, "duration_ms": 456, ...}
        cost = envelope.get("cost_usd")
        if cost is not None:
            model = envelope.get("model", "claude-code-playability")
            _log_playability_cost(model, float(cost))
    except Exception:
        # Cost logging must never break the pipeline
        pass
