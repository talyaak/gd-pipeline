#!/usr/bin/env python3
import asyncio
from pathlib import Path
from pipeline.execute import run_execution_report

html = Path('harness/match_3.html').read_text()
import tempfile
out_dir = Path(tempfile.mkdtemp())
report = run_execution_report(html, out_dir)
print(f'loaded={report.loaded}, canvas={report.canvas_rendered}, input={report.input_response_detected}, engagement={report.engagement_duration_ms}, completion={report.completion_rate}')
print('Errors:', report.console_errors)