#!/usr/bin/env python3
"""
Test selection script for CI fast workflow.

Reads newline-separated changed file paths from stdin, outputs either:
- "ALL" (run full test suite)
- space-separated list of test file paths to pass to pytest
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# Always-run test files (confirmed fast/mocked, no Playwright Chromium needed)
ALWAYS_RUN = [
    "tests/test_spec_adversarial.py",
    "tests/test_visual_spec_adversarial.py",
    "tests/test_research_design_fallbacks.py",
    "tests/test_reskin_noop_adversarial.py",
    "tests/test_adversarial_gate.py",
    "tests/test_graph_failure_routing_adversarial.py",
    "tests/test_validate.py",
    "tests/test_validate_execute_gzip_gate.py",
]

# Files that trigger Chromium install (launch real browser)
CHROMIUM_TRIGGERS = [
    "harness/",
    "pipeline/execute.py",
    "pipeline/reskin.py",
    "pipeline/nodes/validate_execute.py",
]

# Known harness names (those with dedicated test files)
HARNESS_TEST_FILES = {
    "idle_clicker": "tests/test_idle_clicker_harness.py",
    "ball_sort": "tests/test_ball_sort_harness.py",
    "match_3": "tests/test_match3_harness.py",
    "pull_the_pin": "tests/test_pull_the_pin_harness.py",
    "stack_tower": "tests/test_stack_tower_harness.py",
    "tower_defense": "tests/test_tower_defense_harness.py",
    # endless_runner and bullet_hell_shmup have no dedicated harness test files
}

# Reskin e2e test mapping
RESKIN_E2E_TESTS = {
    "match_3": "tests/test_reskin_e2e.py",
    "endless_runner": "tests/test_reskin_e2e.py",
    "idle_clicker": "tests/test_reskin_e2e.py",
    "ball_sort": "tests/test_reskin_e2e_remaining.py",
    "bullet_hell_shmup": "tests/test_reskin_e2e_remaining.py",
    "pull_the_pin": "tests/test_reskin_e2e_remaining.py",
    "stack_tower": "tests/test_reskin_e2e_remaining.py",
    "tower_defense": "tests/test_reskin_e2e_remaining.py",
}


def read_changed_files() -> list[str]:
    """Read changed file paths from stdin."""
    return [line.strip() for line in sys.stdin if line.strip()]


def file_exists(path: str) -> bool:
    """Check if file exists in repo."""
    return (REPO_ROOT / path).exists()


def get_harness_name(filepath: str) -> str | None:
    """Extract harness name from harness/ filepath."""
    if not filepath.startswith("harness/"):
        return None
    # Get filename without extension, before first dot
    filename = Path(filepath).name
    return filename.split(".")[0] if "." in filename else filename


def get_pipeline_basename(filepath: str) -> str | None:
    """Extract basename from pipeline/ or pipeline/nodes/ filepath."""
    if filepath.startswith("pipeline/"):
        filename = Path(filepath).name
        if filename.endswith(".py"):
            return filename[:-3]  # strip .py
    return None


def find_test_files_for_pipeline(basename: str) -> list[str]:
    """Find test files whose names contain the pipeline basename."""
    test_dir = REPO_ROOT / "tests"
    matches = []
    for test_file in test_dir.glob("test_*.py"):
        test_name = test_file.stem  # e.g., "test_execute"
        # Remove "test_" prefix
        test_stem = test_name[5:] if test_name.startswith("test_") else test_name
        if basename in test_stem:
            matches.append(str(test_file.relative_to(REPO_ROOT)))
    return matches


def classify_file(filepath: str) -> tuple[str, list[str]]:
    """
    Classify a changed file and return the test files it maps to.
    Returns (classification, test_files) where classification is one of:
    - "test_file"
    - "harness"
    - "pipeline"
    - "docs"
    - "unmapped"
    """
    # Rule 1: File is itself a test file
    if filepath.startswith("tests/") and filepath.startswith("tests/test_") and filepath.endswith(".py"):
        return ("test_file", [filepath]) if file_exists(filepath) else ("unmapped", [])
    
    # Rule 2: File is under harness/
    if filepath.startswith("harness/"):
        harness_name = get_harness_name(filepath)
        if not harness_name:
            return ("unmapped", [])
        
        test_files = ["tests/test_all_harnesses.py"]
        
        # Dedicated harness test file (if exists)
        if harness_name in HARNESS_TEST_FILES:
            test_files.append(HARNESS_TEST_FILES[harness_name])
        
        # Reskin e2e test
        if harness_name in RESKIN_E2E_TESTS:
            reskin_test = RESKIN_E2E_TESTS[harness_name]
            if file_exists(reskin_test):
                test_files.append(reskin_test)
        
        return ("harness", test_files)
    
    # Rule 3: File is under pipeline/ or pipeline/nodes/
    if filepath.startswith("pipeline/"):
        basename = get_pipeline_basename(filepath)
        if basename:
            matches = find_test_files_for_pipeline(basename)
            if not matches:
                return ("unmapped", [])  # UNMAPPED -> triggers ALL
            return ("pipeline", matches)
        return ("unmapped", [])
    
    # Rule 4: Documentation files
    if filepath.endswith(".md") or filepath.startswith("memory/"):
        return ("docs", [])
    
    # Rule 5: Anything else is unmapped
    return ("unmapped", [])


def needs_chromium(changed_files: list[str]) -> bool:
    """Check if any changed file requires Chromium install."""
    for f in changed_files:
        for trigger in CHROMIUM_TRIGGERS:
            if f.startswith(trigger):
                return True
    return False


def select_tests(changed_files: list[str]) -> tuple[str, bool]:
    """
    Select tests based on changed files.
    Returns (selection_string, needs_chromium) where selection_string is either
    "ALL" or space-separated test file paths.
    """
    # Check for unmapped files that trigger ALL
    for f in changed_files:
        classification, _ = classify_file(f)
        if classification == "unmapped":
            return ("ALL", True)
    
    # Collect all test files
    selected = set(ALWAYS_RUN)
    
    for f in changed_files:
        classification, test_files = classify_file(f)
        for tf in test_files:
            if file_exists(tf):
                selected.add(tf)
    
    # Sort and join
    return (" ".join(sorted(selected)), needs_chromium(changed_files))


def main():
    changed_files = read_changed_files()
    selection, chromium_needed = select_tests(changed_files)
    print(selection)
    print("true" if chromium_needed else "false")
    sys.exit(0)


if __name__ == "__main__":
    main()