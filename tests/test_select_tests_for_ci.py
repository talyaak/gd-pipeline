#!/usr/bin/env python3
"""Unit tests for scripts/select_tests_for_ci.py"""

import sys
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.select_tests_for_ci import (
    ALWAYS_RUN,
    CHROMIUM_TRIGGERS,
    HARNESS_TEST_FILES,
    RESKIN_E2E_TESTS,
    classify_file,
    find_test_files_for_pipeline,
    get_harness_name,
    get_pipeline_basename,
    needs_chromium,
    select_tests,
)


def test_pipeline_execute_maps_to_test_execute_and_validate():
    """Test 1: pipeline/execute.py maps to test_execute.py, test_validate_execute.py, test_validate_execute_gzip_gate.py"""
    changed = ["pipeline/execute.py"]
    selection, _ = select_tests(changed)
    
    assert selection != "ALL", f"Expected selection, got ALL"
    assert "tests/test_execute.py" in selection, f"Missing test_execute.py in {selection}"
    assert "tests/test_validate_execute.py" in selection, f"Missing test_validate_execute.py in {selection}"
    assert "tests/test_validate_execute_gzip_gate.py" in selection, f"Missing test_validate_execute_gzip_gate.py in {selection}"


def test_pipeline_nodes_research_maps_to_test_research_design_fallbacks():
    """Test 2: pipeline/nodes/research.py maps to test_research_design_fallbacks.py"""
    changed = ["pipeline/nodes/research.py"]
    selection, _ = select_tests(changed)
    
    assert selection != "ALL", f"Expected selection, got ALL"
    assert "tests/test_research_design_fallbacks.py" in selection, f"Missing test_research_design_fallbacks.py in {selection}"


def test_unmapped_pipeline_file_produces_all():
    """Test 3: pipeline/retry.py (no matching test) produces ALL"""
    # First confirm no test file matches "retry"
    matches = find_test_files_for_pipeline("retry")
    assert matches == [], f"Expected no matches for 'retry', got {matches}"
    
    # Same for schemas
    matches = find_test_files_for_pipeline("schemas")
    assert matches == [], f"Expected no matches for 'schemas', got {matches}"
    
    # Now test the selection
    changed = ["pipeline/retry.py"]
    selection, _ = select_tests(changed)
    assert selection == "ALL", f"Expected ALL for unmapped pipeline file, got {selection}"
    
    changed = ["pipeline/schemas.py"]
    selection, _ = select_tests(changed)
    assert selection == "ALL", f"Expected ALL for unmapped pipeline file, got {selection}"


def test_harness_idle_clicker_maps_correctly():
    """Test 4: harness/idle_clicker.game.js maps to test_idle_clicker_harness.py, test_all_harnesses.py, test_reskin_e2e.py"""
    changed = ["harness/idle_clicker.game.js"]
    selection, _ = select_tests(changed)
    
    assert selection != "ALL", f"Expected selection, got ALL"
    assert "tests/test_idle_clicker_harness.py" in selection, f"Missing test_idle_clicker_harness.py in {selection}"
    assert "tests/test_all_harnesses.py" in selection, f"Missing test_all_harnesses.py in {selection}"
    assert "tests/test_reskin_e2e.py" in selection, f"Missing test_reskin_e2e.py in {selection}"


def test_harness_endless_runner_no_dedicated_test_file():
    """Test 5: harness/endless_runner.game.js has no dedicated harness test file but still maps to all_harnesses and reskin e2e"""
    # First confirm no dedicated test file exists
    assert "endless_runner" not in HARNESS_TEST_FILES, "endless_runner should not have dedicated test file"
    
    changed = ["harness/endless_runner.game.js"]
    selection, _ = select_tests(changed)
    
    assert selection != "ALL", f"Expected selection, got ALL"
    assert "tests/test_all_harnesses.py" in selection, f"Missing test_all_harnesses.py in {selection}"
    assert "tests/test_reskin_e2e.py" in selection, f"Missing test_reskin_e2e.py in {selection}"
    # Should NOT have test_endless_runner_harness.py
    assert "tests/test_endless_runner_harness.py" not in selection, f"Should not have test_endless_runner_harness.py"


def test_docs_only_returns_always_run():
    """Test 6: empty list or docs-only returns ALWAYS_RUN set"""
    # Empty list
    changed = []
    selection, _ = select_tests(changed)
    for f in ALWAYS_RUN:
        assert f in selection, f"Missing ALWAYS_RUN file {f} in {selection}"
    
    # Docs only
    changed = ["HANDOVER.md"]
    selection, _ = select_tests(changed)
    for f in ALWAYS_RUN:
        assert f in selection, f"Missing ALWAYS_RUN file {f} in {selection}"
    
    # Memory file
    changed = ["memory/some_note.md"]
    selection, _ = select_tests(changed)
    for f in ALWAYS_RUN:
        assert f in selection, f"Missing ALWAYS_RUN file {f} in {selection}"


def test_pyproject_toml_produces_all():
    """Test 7: pyproject.toml (unmapped) produces ALL"""
    changed = ["pyproject.toml"]
    selection, _ = select_tests(changed)
    assert selection == "ALL", f"Expected ALL for pyproject.toml, got {selection}"
    
    # Also test other unmapped files
    changed = [".github/workflows/ci.yml"]
    selection, _ = select_tests(changed)
    assert selection == "ALL", f"Expected ALL for .github/workflows/ci.yml, got {selection}"
    
    changed = ["scripts/publish_to_github.sh"]
    selection, _ = select_tests(changed)
    assert selection == "ALL", f"Expected ALL for scripts/publish_to_github.sh, got {selection}"


def test_always_run_present_in_every_non_all_selection():
    """Test 8: ALWAYS_RUN 8 files present in every non-ALL selection"""
    test_cases = [
        ["pipeline/execute.py"],
        ["pipeline/nodes/research.py"],
        ["harness/idle_clicker.game.js"],
        ["harness/ball_sort.game.js"],
        ["tests/test_spec_adversarial.py"],
        ["tests/test_execute.py"],
    ]
    
    for changed in test_cases:
        selection, _ = select_tests(changed)
        assert selection != "ALL", f"Test case {changed} unexpectedly produced ALL"
        for f in ALWAYS_RUN:
            assert f in selection, f"Missing ALWAYS_RUN file {f} in selection for {changed}: {selection}"


def test_unrecognized_path_produces_all():
    """Test 9: Unrecognized/nonexistent path produces ALL"""
    changed = ["pipeline/nodes/totally_made_up.py"]
    selection, _ = select_tests(changed)
    assert selection == "ALL", f"Expected ALL for unrecognized path, got {selection}"
    
    changed = ["some/random/path.txt"]
    selection, _ = select_tests(changed)
    assert selection == "ALL", f"Expected ALL for random path, got {selection}"


def test_classify_file_helpers():
    """Test helper functions"""
    # get_harness_name
    assert get_harness_name("harness/idle_clicker.game.js") == "idle_clicker"
    assert get_harness_name("harness/idle_clicker.manifest.json") == "idle_clicker"
    assert get_harness_name("harness/endless_runner.html") == "endless_runner"
    assert get_harness_name("pipeline/execute.py") is None
    
    # get_pipeline_basename
    assert get_pipeline_basename("pipeline/execute.py") == "execute"
    assert get_pipeline_basename("pipeline/nodes/research.py") == "research"
    assert get_pipeline_basename("pipeline/nodes/validate_execute.py") == "validate_execute"
    assert get_pipeline_basename("pipeline/nodes/spec_prompt.txt") is None  # not .py
    assert get_pipeline_basename("harness/idle_clicker.game.js") is None
    
    # find_test_files_for_pipeline
    matches = find_test_files_for_pipeline("execute")
    assert "tests/test_execute.py" in matches
    assert "tests/test_validate_execute.py" in matches
    assert "tests/test_validate_execute_gzip_gate.py" in matches
    
    matches = find_test_files_for_pipeline("research")
    assert "tests/test_research_design_fallbacks.py" in matches
    
    matches = find_test_files_for_pipeline("spec")
    assert "tests/test_spec_adversarial.py" in matches
    assert "tests/test_visual_spec_adversarial.py" in matches
    
    # classify_file
    assert classify_file("tests/test_execute.py") == ("test_file", ["tests/test_execute.py"])
    assert classify_file("harness/idle_clicker.game.js")[0] == "harness"
    assert classify_file("pipeline/execute.py")[0] == "pipeline"
    assert classify_file("HANDOVER.md")[0] == "docs"
    assert classify_file("memory/note.md")[0] == "docs"
    assert classify_file("pyproject.toml")[0] == "unmapped"


def test_needs_chromium():
    """Test chromium trigger detection"""
    assert needs_chromium(["harness/idle_clicker.game.js"]) is True
    assert needs_chromium(["pipeline/execute.py"]) is True
    assert needs_chromium(["pipeline/reskin.py"]) is True
    assert needs_chromium(["pipeline/nodes/validate_execute.py"]) is True
    assert needs_chromium(["pipeline/nodes/research.py"]) is False
    assert needs_chromium(["tests/test_execute.py"]) is False
    assert needs_chromium(["HANDOVER.md"]) is False
    assert needs_chromium([]) is False


if __name__ == "__main__":
    pytest = __import__("pytest")
    pytest.main([__file__, "-v"])