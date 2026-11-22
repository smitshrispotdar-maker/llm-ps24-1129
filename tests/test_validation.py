"""Input validation and JSON parsing (no API needed)."""
import pytest

from evaluator import ResponseFormatError, parse_json_response, validate_inputs

Q, M, S = "What is DROP?", "DROP removes a table.", "It deletes a table."


def test_valid_inputs_have_no_errors():
    assert validate_inputs(Q, M, S, 5) == []


@pytest.mark.parametrize("q,m", [("", M), ("   ", M), (Q, ""), (Q, "  \n")])
def test_empty_question_or_model_answer_rejected(q, m):
    assert validate_inputs(q, m, S, 5)


def test_blank_student_answer_is_not_an_input_error():
    assert validate_inputs(Q, M, "", 5) == []


@pytest.mark.parametrize("marks", [0, -1, 101, float("nan"), float("inf"), "5", None, True])
def test_invalid_max_marks_rejected(marks):
    assert validate_inputs(Q, M, S, marks)


@pytest.mark.parametrize("marks", [1, 2, 5, 10, 15, 2.5, 100])
def test_valid_max_marks_accepted(marks):
    assert validate_inputs(Q, M, S, marks) == []


def test_overlong_text_rejected():
    assert validate_inputs(Q, M, "x" * 9000, 5)


def test_parse_plain_json():
    assert parse_json_response('{"a": 1}') == {"a": 1}


def test_parse_json_inside_code_fence():
    assert parse_json_response('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_with_surrounding_prose():
    assert parse_json_response('Here you go: {"a": 1} Hope it helps') == {"a": 1}


@pytest.mark.parametrize("bad", ["", "   ", None, "not json", "{broken", "[1, 2]", '"text"'])
def test_parse_malformed_json_raises(bad):
    with pytest.raises(ResponseFormatError):
        parse_json_response(bad)
