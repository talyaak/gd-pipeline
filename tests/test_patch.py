from pipeline.patch import apply_edits


def test_single_unambiguous_edit_applies():
    text = "const x = 1;\nconst y = 2;\n"
    new_text, errors = apply_edits(text, [{"old_string": "const x = 1;", "new_string": "const x = 100;"}])
    assert new_text == "const x = 100;\nconst y = 2;\n"
    assert errors == []


def test_edit_not_found_is_reported_and_skipped():
    text = "const x = 1;\n"
    new_text, errors = apply_edits(text, [{"old_string": "const z = 9;", "new_string": "const z = 10;"}])
    assert new_text == text
    assert len(errors) == 1
    assert "not found" in errors[0]


def test_ambiguous_edit_is_reported_and_skipped():
    text = "foo();\nfoo();\n"
    new_text, errors = apply_edits(text, [{"old_string": "foo();", "new_string": "bar();"}])
    assert new_text == text
    assert len(errors) == 1
    assert "not unique" in errors[0]


def test_sequential_edits_see_prior_patches():
    text = "let a = 1;\n"
    edits = [
        {"old_string": "let a = 1;", "new_string": "let a = 2;"},
        {"old_string": "let a = 2;", "new_string": "let a = 3;"},
    ]
    new_text, errors = apply_edits(text, edits)
    assert new_text == "let a = 3;\n"
    assert errors == []


def test_malformed_edit_is_reported_and_skipped():
    text = "let a = 1;\n"
    new_text, errors = apply_edits(text, [{"old_string": "", "new_string": "x"}, {"new_string": "y"}])
    assert new_text == text
    assert len(errors) == 2
