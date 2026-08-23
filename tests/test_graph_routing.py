from pipeline.graph import _after_review, _after_validate_execute, _give_up


def _state(execution_status, execution_attempt, code_status=None, code_attempt=None):
    return {
        "execution": {"status": execution_status, "attempt": execution_attempt},
        "code": {"status": code_status or "passed", "attempt": code_attempt or execution_attempt},
    }


def test_validate_execute_passed_routes_to_review():
    assert _after_validate_execute(_state("passed", 1)) == "review"


def test_validate_execute_failed_under_limit_routes_to_codegen():
    assert _after_validate_execute(_state("failed_needs_rework", 1)) == "codegen"


def test_validate_execute_failed_at_limit_routes_to_give_up():
    assert _after_validate_execute(_state("failed_needs_rework", 2)) == "give_up"


def test_review_passed_routes_to_done():
    state = _state("passed", 1, code_status="passed", code_attempt=1)
    assert _after_review(state) == "variant_gen"


def test_review_failed_under_limit_routes_to_codegen():
    state = _state("passed", 1, code_status="failed_needs_rework", code_attempt=1)
    assert _after_review(state) == "codegen"


def test_review_failed_at_limit_routes_to_give_up():
    state = _state("passed", 2, code_status="failed_needs_rework", code_attempt=2)
    assert _after_review(state) == "give_up"


def test_give_up_marks_code_failed_max_attempts():
    state = _state("failed_needs_rework", 2, code_status="failed_needs_rework", code_attempt=2)
    result = _give_up(state)
    assert result["code"]["status"] == "failed_max_attempts"
