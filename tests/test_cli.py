#!/usr/bin/env python3
"""
Adversarial test for cli.py fix: "game.html written to..." should only print
when the file was actually written (code status == "passed" AND final_html exists).
"""
import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add pipeline to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.cli import main


class MockSqliteSaver:
    @classmethod
    def from_conn_string(cls, *args, **kwargs):
        instance = cls()
        return instance

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class MockGraph:
    def invoke(self, *args, **kwargs):
        return self.final_state

    def __init__(self, final_state):
        self.final_state = final_state


def run_cli_with_state(final_state, brief="test game"):
    """Run main() with a mocked graph returning final_state, capture stdout/stderr."""
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    old_argv = sys.argv
    sys.stdout = io.StringIO()
    sys.stderr = io.StringIO()
    sys.argv = ["pipeline", brief]

    try:
        with patch("pipeline.cli.SqliteSaver", MockSqliteSaver):
            with patch("pipeline.cli.build_graph", lambda checkpointer: MockGraph(final_state)):
                with patch("pipeline.cli.new_run_dir", lambda b: Path("/tmp/test_run")):
                    with patch("pipeline.cli.stage_dir", lambda *a, **k: Path("/tmp/test_stage")):
                        with patch("pipeline.cli.write_json"):
                            with patch("pipeline.cli.write_text"):
                                try:
                                    main()
                                except SystemExit as e:
                                    return sys.stdout.getvalue(), sys.stderr.getvalue(), e.code
    finally:
        out = sys.stdout.getvalue()
        err = sys.stderr.getvalue()
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        sys.argv = old_argv

    return out, err, 0


def test_cli_does_not_print_written_when_code_failed():
    """Adversarial: before fix, this would incorrectly print 'game.html written to...'"""
    final_state = {
        "code": {"status": "failed_needs_rework", "attempt": 1},
        "execution": {"status": "failed_needs_rework", "attempt": 1, "artifact": {}},
        "research": {"status": "passed", "attempt": 1},
        "design": {"status": "passed", "attempt": 1},
        "spec": {"status": "passed", "attempt": 1},
        "variants": {"status": "skipped", "attempt": 1},
    }

    out, err, code = run_cli_with_state(final_state)

    # Should NOT print the "written to" message when code status != passed
    assert "game.html written to" not in out, f"FAIL: Printed 'game.html written to' when code failed:\n{out}"
    # Should print failure message
    assert "Pipeline did not produce a passing game.html" in err


def test_cli_does_not_print_written_when_no_final_html():
    """Adversarial: before fix, this would incorrectly print 'game.html written to...'"""
    final_state = {
        "code": {"status": "passed", "attempt": 1},
        "execution": {"status": "passed", "attempt": 1, "artifact": {"final_html": None}},
        "research": {"status": "passed", "attempt": 1},
        "design": {"status": "passed", "attempt": 1},
        "spec": {"status": "passed", "attempt": 1},
        "variants": {"status": "skipped", "attempt": 1},
    }

    out, err, code = run_cli_with_state(final_state)

    # Should NOT print the "written to" message when final_html is None
    assert "game.html written to" not in out, f"FAIL: Printed 'game.html written to' when final_html=None:\n{out}"
    # Note: current CLI behavior - when code passed but no final_html, it doesn't print
    # the failure message either (only prints when code.status != "passed").
    # This test verifies the fix: "written to" message is NOT printed.


def test_cli_prints_written_when_both_conditions_met():
    """Positive case: should print when code passed AND final_html exists"""
    final_state = {
        "code": {"status": "passed", "attempt": 1},
        "execution": {"status": "passed", "attempt": 1, "artifact": {"final_html": "<html>test</html>"}},
        "research": {"status": "passed", "attempt": 1},
        "design": {"status": "passed", "attempt": 1},
        "spec": {"status": "passed", "attempt": 1},
        "variants": {"status": "skipped", "attempt": 1},
    }

    out, err, code = run_cli_with_state(final_state)

    # Should print the "written to" message
    assert "game.html written to" in out, f"FAIL: Did NOT print 'game.html written to' when it should have:\n{out}"
    # Should NOT print failure message
    assert "Pipeline did not produce a passing game.html" not in err


if __name__ == "__main__":
    # Run tests manually for quick verification
    print("Running test_cli_does_not_print_written_when_code_failed...")
    test_cli_does_not_print_written_when_code_failed()
    print("PASS")

    print("Running test_cli_does_not_print_written_when_no_final_html...")
    test_cli_does_not_print_written_when_no_final_html()
    print("PASS")

    print("Running test_cli_prints_written_when_both_conditions_met...")
    test_cli_prints_written_when_both_conditions_met()
    print("PASS")

    print("\nAll tests passed!")