"""Local cost tracking for pipeline LLM calls.

Every generation/review call through pipeline/llm.py gets instrumented with
CostTrackingCallback, which logs one JSON line per call to pipeline_cost_log.jsonl
(gitignored - this is local telemetry, not project history) with token counts,
an estimated cost, and a cheap anomaly flag. Nothing here makes network calls or
talks to Anthropic's billing API - it's a local estimate from token counts, meant
to catch abnormalities (a run using 50x the normal tokens) between the times
someone actually checks the real Console usage page.
"""

from __future__ import annotations

import json
import os
import statistics
import time
from pathlib import Path

from langchain_core.callbacks import BaseCallbackHandler

LOG_PATH = Path(os.environ.get("PIPELINE_COST_LOG", "pipeline_cost_log.jsonl"))

# USD per million tokens. Best-known published rates as of this code's writing -
# verify against console.anthropic.com/settings/billing if these look stale;
# pricing can change and this is a local estimate, not a billing source of truth.
PRICING_PER_MTOK = {
    "claude-sonnet-4-5-20250929": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
}

# A call costing more than this many multiples of the recent median is flagged
# as an anomaly. Tune if it's too noisy or too quiet.
ANOMALY_MULTIPLIER = 4.0
ANOMALY_MIN_HISTORY = 5


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    rates = PRICING_PER_MTOK.get(model)
    if rates is None:
        return None
    return (input_tokens / 1_000_000) * rates["input"] + (output_tokens / 1_000_000) * rates["output"]


def _recent_costs(node: str, limit: int = 20) -> list[float]:
    if not LOG_PATH.exists():
        return []
    costs = []
    with LOG_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("node") == node and entry.get("cost_usd") is not None:
                costs.append(entry["cost_usd"])
    return costs[-limit:]


class CostTrackingCallback(BaseCallbackHandler):
    """Attach to a langchain LLM instance to log token usage + estimated cost per call."""

    def __init__(self, node: str):
        self.node = node

    def on_llm_end(self, response, **kwargs):
        try:
            self._log(response)
        except Exception as e:  # noqa: BLE001 - tracking must never break the pipeline
            try:
                with LOG_PATH.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"ts": time.time(), "node": self.node, "tracker_error": str(e)}) + "\n")
            except Exception:
                pass

    def _log(self, response):
        model = None
        input_tokens = 0
        output_tokens = 0

        for gen_list in getattr(response, "generations", []) or []:
            for gen in gen_list:
                msg = getattr(gen, "message", None)
                usage = getattr(msg, "usage_metadata", None) if msg else None
                if usage:
                    input_tokens += usage.get("input_tokens", 0) or 0
                    output_tokens += usage.get("output_tokens", 0) or 0
                if msg is not None:
                    rm = getattr(msg, "response_metadata", None) or {}
                    model = model or rm.get("model") or rm.get("model_name")

        llm_output = getattr(response, "llm_output", None) or {}
        model = model or llm_output.get("model_name") or llm_output.get("model")
        if not model:
            usage2 = llm_output.get("usage") or llm_output.get("token_usage") or {}
            input_tokens = input_tokens or usage2.get("input_tokens") or usage2.get("prompt_tokens") or 0
            output_tokens = output_tokens or usage2.get("output_tokens") or usage2.get("completion_tokens") or 0

        cost = _estimate_cost(model, input_tokens, output_tokens) if model else None

        history = _recent_costs(self.node)
        anomaly = False
        anomaly_reason = None
        if cost is not None and len(history) >= ANOMALY_MIN_HISTORY:
            median = statistics.median(history)
            if median > 0 and cost > median * ANOMALY_MULTIPLIER:
                anomaly = True
                anomaly_reason = f"cost ${cost:.4f} is {cost / median:.1f}x the recent median (${median:.4f}) for node '{self.node}'"

        entry = {
            "ts": time.time(),
            "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "node": self.node,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost, 6) if cost is not None else None,
            "anomaly": anomaly,
            "anomaly_reason": anomaly_reason,
        }

        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")


def summarize(hours: float | None = 24) -> dict:
    """Quick digest for the judge / Hermes agent: spend, call count, any anomalies."""
    if not LOG_PATH.exists():
        return {"total_calls": 0, "total_cost_usd": 0.0, "anomalies": [], "note": "no cost log yet"}

    cutoff = time.time() - hours * 3600 if hours else 0
    total_cost = 0.0
    total_calls = 0
    anomalies = []
    by_node: dict[str, float] = {}

    with LOG_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("ts", 0) < cutoff:
                continue
            if "tracker_error" in entry:
                continue
            total_calls += 1
            cost = entry.get("cost_usd") or 0.0
            total_cost += cost
            by_node[entry.get("node", "?")] = by_node.get(entry.get("node", "?"), 0.0) + cost
            if entry.get("anomaly"):
                anomalies.append({"iso": entry.get("iso"), "node": entry.get("node"), "reason": entry.get("anomaly_reason")})

    return {
        "window_hours": hours,
        "total_calls": total_calls,
        "total_cost_usd": round(total_cost, 4),
        "cost_by_node": {k: round(v, 4) for k, v in by_node.items()},
        "anomalies": anomalies,
    }


if __name__ == "__main__":
    import sys

    hours = float(sys.argv[1]) if len(sys.argv) > 1 else 24
    print(json.dumps(summarize(hours), indent=2))
