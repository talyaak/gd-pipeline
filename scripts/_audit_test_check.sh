#!/usr/bin/env bash
set -e
cd /workspace
VENV=/tmp/venv_seed
PYTHONPATH=/workspace "$VENV/bin/python" -m pytest -q -m "not slow" 2>&1 | tail -15
