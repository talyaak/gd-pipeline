#!/usr/bin/env python3
import pytest
from pathlib import Path
from pipeline.execute import run_execution_report
import tempfile

@pytest.mark.slow
def test_pull_the_pin_harness_execution(tmp_path):
    """Test that the pull_the_pin harness loads and runs correctly."""
    html = Path('/workspace/harness/pull_the_pin.html').read_text()
    out_dir = Path(tempfile.mkdtemp())
    report = run_execution_report(html, out_dir)
    
    print(f'loaded={report.loaded}, canvas={report.canvas_rendered}, input={report.input_response_detected}, engagement={report.engagement_duration_ms}, completion={report.completion_rate}')
    print('Errors:', report.console_errors)
    
    assert report.loaded is True
    assert report.canvas_rendered is True
    assert report.input_response_detected is True
    assert report.engagement_duration_ms and report.engagement_duration_ms > 0