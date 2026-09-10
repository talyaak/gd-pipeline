#!/usr/bin/env python3
import pytest
from pathlib import Path
from pipeline.execute import run_execution_report
import tempfile

HARNESS_DIR = Path(__file__).parent.parent / "harness"

@pytest.mark.slow
def test_harness_execution(tmp_path):
    """Test that all harnesses load and run correctly."""
    harnesses = [
        'endless_runner.html',
        'match_3.html',
        'idle_clicker.html',
        'pull_the_pin.html',
        'ball_sort.html',
        'stack_tower.html',
        'tower_defense.html',
        'bullet_hell_shmup.html',
        'farm_idle.html',
    ]

    for harness_name in harnesses:
        html_path = HARNESS_DIR / harness_name
        if not html_path.exists():
            raise FileNotFoundError(f"Harness file not found: {html_path}")

        html = html_path.read_text()
        out_dir = Path(tempfile.mkdtemp())
        report = run_execution_report(html, out_dir)

        print(f'{harness_name}: loaded={report.loaded}, canvas={report.canvas_rendered}, input={report.input_response_detected}, engagement={report.engagement_duration_ms}, completion={report.completion_rate}')

        assert report.loaded is True, f"{harness_name}: failed to load"
        assert report.canvas_rendered is True, f"{harness_name}: canvas not rendered"
        assert report.input_response_detected is True, f"{harness_name}: no input response"
        assert report.engagement_duration_ms and report.engagement_duration_ms > 0, f"{harness_name}: no engagement"