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
# verify against console.anthropic.com/settings/billing or openrouter.ai/models if these look stale;
# pricing can change and this is a local estimate, not a billing source of truth.
# OpenRouter pricing (per million tokens) for models used by this pipeline:
# - anthropic/claude-sonnet-4: input $3.00, output $15.00
# - anthropic/claude-3-haiku: input $0.25, output $1.25
# Direct Anthropic API pricing:
# - claude-sonnet-4-5-20250929: input $3.00, output $15.00
# - claude-haiku-4-5-20251001: input $1.00, output $5.00
PRICING_PER_MTOK = {
    # OpenRouter models (provider/model format)
    "anthropic/claude-sonnet-4": {"input": 3.00, "output": 15.00},
    "anthropic/claude-3-haiku": {"input": 0.25, "output": 1.25},
    # Direct Anthropic API models (dated IDs)
    "claude-sonnet-4-5-20250929": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
}

# A call costing more than this many multiples of the recent median is flagged
# as an anomaly. Tune if it's too noisy or too quiet.
ANOMALY_MULTIPLIER = 4.0
ANOMALY_MIN_HISTORY = 5


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Estimate cost in USD for a given model and token counts."""
    if not model:
        return None
    # Normalize model name for OpenRouter slugs (they use provider/model format)
    rates = PRICING_PER_MTOK.get(model)
    if rates is None:
        return None
    return (input_tokens / 1_000_000) * rates["input"] + (output_tokens / 1_000_000) * rates["output"]


def compute_repair_metrics(final_state: dict) -> dict:
    """Compute repair-loop metrics from final pipeline state.
    
    Metrics computed from existing attempt/status data (no new state tracking):
    - first_pass_success_rate: stages that passed on attempt 1 / total stages that ran
    - repair_success_rate: stages that eventually passed after repairs / total stages that needed repair
    - avg_repair_count: average number of repair attempts per stage that ran
    """
    # Stages that have attempt/status data (the repair loop stages)
    repair_stages = ["code", "execution", "review"]
    
    total_stages = 0
    first_pass_success = 0
    repair_needed = 0
    repair_succeeded = 0
    total_repair_attempts = 0
    
    for stage in repair_stages:
        stage_data = final_state.get(stage, {})
        if not stage_data:
            continue
        attempt = stage_data.get("attempt", 1)
        status = stage_data.get("status")
        
        total_stages += 1
        total_repair_attempts += attempt
        
        if attempt == 1 and status == "passed":
            first_pass_success += 1
        elif attempt > 1:
            repair_needed += 1
            if status == "passed":
                repair_succeeded += 1
    
    first_pass_rate = first_pass_success / total_stages if total_stages > 0 else 0.0
    repair_rate = repair_succeeded / repair_needed if repair_needed > 0 else 1.0
    avg_repairs = (total_repair_attempts - total_stages) / total_stages if total_stages > 0 else 0.0
    
    return {
        "first_pass_success_rate": round(first_pass_rate, 4),
        "repair_success_rate": round(repair_rate, 4),
        "avg_repair_count_per_stage": round(avg_repairs, 4),
        "stages_analyzed": total_stages,
        "first_pass_successes": first_pass_success,
        "repairs_needed": repair_needed,
        "repairs_succeeded": repair_succeeded,
    }


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
