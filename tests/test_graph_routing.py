from config import MAX_CODE_ATTEMPTS
from pipeline.graph import _after_review, _after_validate_execute, _after_research, _after_design, _after_spec, _after_visual_spec, _give_up

UNDER_LIMIT = MAX_CODE_ATTEMPTS - 1
AT_LIMIT = MAX_CODE_ATTEMPTS


def _state(execution_status, execution_attempt, code_status=None, code_attempt=None):
    return {
        "execution": {"status": execution_status, "attempt": execution_attempt},
        "code": {"status": code_status or "passed", "attempt": code_attempt or execution_attempt},
    }


def test_validate_execute_passed_routes_to_review():
    assert _after_validate_execute(_state("passed", 1)) == "review"


def test_validate_execute_failed_under_limit_routes_to_codegen():
    assert _after_validate_execute(_state("failed_needs_rework", UNDER_LIMIT)) == "codegen"


def test_validate_execute_failed_at_limit_routes_to_give_up():
    assert _after_validate_execute(_state("failed_needs_rework", AT_LIMIT)) == "give_up"


def test_review_passed_routes_to_done():
    state = _state("passed", 1, code_status="passed", code_attempt=1)
    assert _after_review(state) == "variant_gen"


def test_review_failed_under_limit_routes_to_codegen():
    state = _state("passed", UNDER_LIMIT, code_status="failed_needs_rework", code_attempt=UNDER_LIMIT)
    assert _after_review(state) == "codegen"


def test_review_failed_at_limit_routes_to_give_up():
    state = _state("passed", AT_LIMIT, code_status="failed_needs_rework", code_attempt=AT_LIMIT)
    assert _after_review(state) == "give_up"


def test_give_up_marks_code_failed_max_attempts():
    state = _state("failed_needs_rework", AT_LIMIT, code_status="failed_needs_rework", code_attempt=AT_LIMIT)
    result = _give_up(state)
    assert result["code"]["status"] == "failed_max_attempts"


def test_after_research_failed_routes_to_give_up():
    state = {"research": {"status": "failed_needs_rework"}}
    assert _after_research(state) == "give_up"


def test_after_research_passed_routes_to_continue():
    state = {"research": {"status": "passed"}}
    assert _after_research(state) == "continue"


def test_after_design_failed_routes_to_give_up():
    state = {"design": {"status": "failed_needs_rework"}}
    assert _after_design(state) == "give_up"


def test_after_design_passed_routes_to_continue():
    state = {"design": {"status": "passed"}}
    assert _after_design(state) == "continue"


def test_after_spec_failed_routes_to_give_up():
    state = {"spec": {"status": "failed_needs_rework"}}
    assert _after_spec(state) == "give_up"


def test_after_spec_passed_routes_to_continue():
    state = {"spec": {"status": "passed"}}
    assert _after_spec(state) == "continue"


def test_after_visual_spec_failed_routes_to_give_up():
    state = {"visual_spec": {"status": "failed_needs_rework"}}
    assert _after_visual_spec(state) == "give_up"


def test_after_visual_spec_passed_routes_to_continue():
    state = {"visual_spec": {"status": "passed"}}
    assert _after_visual_spec(state) == "continue"


def test_give_up_from_front_half_does_not_crash_on_missing_execution_and_code():
    state = {"research": {"status": "failed_needs_rework", "attempt": 1, "artifact": None, "error": "boom"}}
    result = _give_up(state)
    assert result["code"]["status"] == "failed_max_attempts"
