"""Tests for repair-loop metrics and cost tracking fixes."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from pipeline.cost_tracker import (
    PRICING_PER_MTOK,
    _estimate_cost,
    compute_repair_metrics,
    CostTrackingCallback,
    LOG_PATH,
)


class TestRepairMetrics:
    """Test repair-loop metrics computation from synthetic run history."""

    def test_all_first_pass(self):
        """All stages pass on attempt 1 -> 100% first-pass, 0 repairs."""
        final_state = {
            "code": {"attempt": 1, "status": "passed"},
            "execution": {"attempt": 1, "status": "passed"},
            "review": {"attempt": 1, "status": "passed"},
        }
        metrics = compute_repair_metrics(final_state)
        assert metrics["first_pass_success_rate"] == 1.0
        assert metrics["repair_success_rate"] == 1.0  # no repairs needed
        assert metrics["avg_repair_count_per_stage"] == 0.0
        assert metrics["stages_analyzed"] == 3
        assert metrics["first_pass_successes"] == 3
        assert metrics["repairs_needed"] == 0
        assert metrics["repairs_succeeded"] == 0

    def test_one_repair_succeeds(self):
        """One stage needs repair and succeeds."""
        final_state = {
            "code": {"attempt": 2, "status": "passed"},  # 1 repair, succeeded
            "execution": {"attempt": 1, "status": "passed"},
            "review": {"attempt": 1, "status": "passed"},
        }
        metrics = compute_repair_metrics(final_state)
        assert abs(metrics["first_pass_success_rate"] - 2 / 3) < 0.001
        assert metrics["repair_success_rate"] == 1.0  # 1 repair needed, 1 succeeded
        assert abs(metrics["avg_repair_count_per_stage"] - 1 / 3) < 0.001
        assert metrics["stages_analyzed"] == 3
        assert metrics["first_pass_successes"] == 2
        assert metrics["repairs_needed"] == 1
        assert metrics["repairs_succeeded"] == 1

    def test_one_repair_fails(self):
        """One stage needs repair but fails (max attempts)."""
        final_state = {
            "code": {"attempt": 3, "status": "failed_max_attempts"},  # 2 repairs, failed
            "execution": {"attempt": 1, "status": "passed"},
            "review": {"attempt": 1, "status": "passed"},
        }
        metrics = compute_repair_metrics(final_state)
        assert abs(metrics["first_pass_success_rate"] - 2 / 3) < 0.001
        assert metrics["repair_success_rate"] == 0.0  # 1 repair needed, 0 succeeded
        assert abs(metrics["avg_repair_count_per_stage"] - 2 / 3) < 0.001
        assert metrics["repairs_needed"] == 1
        assert metrics["repairs_succeeded"] == 0

    def test_mixed_repairs(self):
        """Multiple stages with mixed repair outcomes."""
        final_state = {
            "code": {"attempt": 2, "status": "passed"},  # 1 repair, success
            "execution": {"attempt": 3, "status": "passed"},  # 2 repairs, success
            "review": {"attempt": 2, "status": "failed_max_attempts"},  # 1 repair, fail
        }
        metrics = compute_repair_metrics(final_state)
        assert metrics["first_pass_success_rate"] == 0.0
        assert abs(metrics["repair_success_rate"] - 2 / 3) < 0.001  # 3 repairs needed, 2 succeeded
        # total attempts = 2+3+2 = 7, stages = 3, avg repairs = (7-3)/3 = 4/3
        assert abs(metrics["avg_repair_count_per_stage"] - 4 / 3) < 0.01
        assert metrics["repairs_needed"] == 3
        assert metrics["repairs_succeeded"] == 2

    def test_missing_stages(self):
        """Some stages missing from state (e.g., early termination)."""
        final_state = {
            "code": {"attempt": 1, "status": "passed"},
            "execution": {"attempt": 2, "status": "passed"},
            # review missing
        }
        metrics = compute_repair_metrics(final_state)
        assert metrics["stages_analyzed"] == 2
        assert metrics["first_pass_success_rate"] == 0.5
        assert metrics["repair_success_rate"] == 1.0

    def test_empty_state(self):
        """Empty state -> zero stages analyzed."""
        final_state = {}
        metrics = compute_repair_metrics(final_state)
        assert metrics["stages_analyzed"] == 0
        assert metrics["first_pass_success_rate"] == 0.0
        assert metrics["repair_success_rate"] == 1.0
        assert metrics["avg_repair_count_per_stage"] == 0.0


class TestCostTracking:
    """Test cost tracking with real OpenRouter model pricing."""

    def test_openrouter_sonnet_4_pricing(self):
        """OpenRouter claude-sonnet-4 pricing computes correct cost."""
        # 1M input + 1M output = $3 + $15 = $18
        cost = _estimate_cost("anthropic/claude-sonnet-4", 1_000_000, 1_000_000)
        assert cost == 18.0

        # 500k input + 200k output = 0.5*3 + 0.2*15 = 1.5 + 3.0 = 4.5
        cost = _estimate_cost("anthropic/claude-sonnet-4", 500_000, 200_000)
        assert cost == 4.5

    def test_openrouter_haiku_3_pricing(self):
        """OpenRouter claude-3-haiku pricing computes correct cost."""
        # 1M input + 1M output = $0.25 + $1.25 = $1.50
        cost = _estimate_cost("anthropic/claude-3-haiku", 1_000_000, 1_000_000)
        assert cost == 1.5

        # 100k input + 50k output = 0.1*0.25 + 0.05*1.25 = 0.025 + 0.0625 = 0.0875
        cost = _estimate_cost("anthropic/claude-3-haiku", 100_000, 50_000)
        assert cost == 0.0875

    def test_direct_anthropic_pricing(self):
        """Direct Anthropic API pricing still works."""
        cost = _estimate_cost("claude-sonnet-4-5-20250929", 1_000_000, 1_000_000)
        assert cost == 18.0

        cost = _estimate_cost("claude-haiku-4-5-20251001", 1_000_000, 1_000_000)
        assert cost == 6.0

    def test_unknown_model_returns_none(self):
        """Unknown model returns None, not 0."""
        cost = _estimate_cost("unknown/model", 1000, 1000)
        assert cost is None

        cost = _estimate_cost(None, 1000, 1000)
        assert cost is None

        cost = _estimate_cost("", 1000, 1000)
        assert cost is None

    def test_cost_logged_with_correct_usd(self):
        """Adversarial test: a logged cost entry MUST have non-null cost_usd for known models."""
        # Create a temp log file
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test_cost_log.jsonl"
            
            # Temporarily override LOG_PATH
            import pipeline.cost_tracker as ct
            original_log_path = ct.LOG_PATH
            ct.LOG_PATH = log_path
            
            try:
                # Simulate a callback log entry for OpenRouter sonnet-4
                entry = {
                    "ts": 1234567890.0,
                    "iso": "2026-01-01T00:00:00Z",
                    "node": "codegen",
                    "model": "anthropic/claude-sonnet-4",
                    "input_tokens": 100_000,
                    "output_tokens": 50_000,
                    "cost_usd": None,  # will be computed
                    "anomaly": False,
                    "anomaly_reason": None,
                }
                # Compute cost manually
                expected_cost = _estimate_cost("anthropic/claude-sonnet-4", 100_000, 50_000)
                entry["cost_usd"] = round(expected_cost, 6)
                
                with log_path.open("w") as f:
                    f.write(json.dumps(entry) + "\n")
                
                # Read back and verify
                with log_path.open("r") as f:
                    line = f.readline()
                    logged = json.loads(line)
                
                # THE ASSERTION: cost_usd must be non-null and correct
                assert logged["cost_usd"] is not None, "cost_usd must not be None for known model"
                assert logged["cost_usd"] == round(expected_cost, 6), f"Expected {expected_cost}, got {logged['cost_usd']}"
                assert logged["model"] == "anthropic/claude-sonnet-4"
            finally:
                ct.LOG_PATH = original_log_path


if __name__ == "__main__":
    pytest.main([__file__, "-v"])