"""Evaluator logic with a mocked Gemini (no API key / no network needed)."""
import json
import os
from unittest.mock import patch

import pytest

from evaluator import (
    APIError, ConfigError, ResponseFormatError, ValidationError,
    blank_answer_result, evaluate_answer, normalize_result, remark_for, translate_exception,
)

Q, M, S = "What is DROP?", "DROP removes a table.", "It deletes a table."


def fake_response(**overrides):
    data = {
        "marks_awarded": 4, "maximum_marks": 5, "percentage": 80,
        "criteria_breakdown": {"conceptual_correctness": 1.8, "key_points_covered": 1.2,
                               "completeness": 0.6, "relevance": 0.3, "clarity": 0.1},
        "correct_points": ["Core idea"], "missing_points": ["Detail"], "incorrect_points": [],
        "feedback": "Good.", "remark": "Good", "teacher_review_notes": [],
    }
    data.update(overrides)
    return json.dumps(data)


def test_happy_path_with_mocked_gemini():
    result = evaluate_answer(Q, M, S, 5, generate_fn=lambda p: fake_response())
    assert result["marks_awarded"] == 4.0
    assert result["percentage"] == 80.0
    assert result["remark"] == "Good"
    assert result["correct_points"] == ["Core idea"]


def test_prompt_contains_inputs_and_scaled_rubric():
    seen = {}
    evaluate_answer(Q, M, S, 10, generate_fn=lambda p: seen.setdefault("p", p) and fake_response())
    prompt = seen["p"]
    assert Q in prompt and M in prompt and S in prompt
    assert "maximum 4 marks" in prompt  # 40% of 10


@pytest.mark.parametrize("max_marks", [2, 5, 10, 15])
def test_scores_scale_to_max_marks(max_marks):
    caps = {"conceptual_correctness": .4, "key_points_covered": .3, "completeness": .15,
            "relevance": .1, "clarity": .05}
    crit = {k: v * max_marks for k, v in caps.items()}  # a perfect answer
    result = evaluate_answer(Q, M, S, max_marks,
                             generate_fn=lambda p: fake_response(criteria_breakdown=crit))
    assert result["marks_awarded"] == pytest.approx(max_marks)
    assert result["percentage"] == 100.0


def test_marks_never_exceed_maximum_even_if_model_overshoots():
    crit = {k: 99 for k in ["conceptual_correctness", "key_points_covered",
                            "completeness", "relevance", "clarity"]}
    result = evaluate_answer(Q, M, S, 5, generate_fn=lambda p: fake_response(criteria_breakdown=crit))
    assert result["marks_awarded"] <= 5
    assert all(result["criteria_breakdown"][k] <= result["criteria_max"][k] for k in crit)


def test_negative_scores_clamped_to_zero():
    crit = {k: -3 for k in ["conceptual_correctness", "key_points_covered",
                            "completeness", "relevance", "clarity"]}
    result = evaluate_answer(Q, M, S, 5, generate_fn=lambda p: fake_response(criteria_breakdown=crit))
    assert result["marks_awarded"] == 0 and result["percentage"] == 0


def test_total_is_recomputed_from_criteria_not_trusted():
    result = evaluate_answer(Q, M, S, 5, generate_fn=lambda p: fake_response(marks_awarded=5, percentage=100))
    assert result["marks_awarded"] == 4.0  # 1.8+1.2+0.6+0.3+0.1


def test_blank_answer_gets_zero_without_calling_the_model():
    def must_not_be_called(prompt):
        raise AssertionError("Gemini should not be called for a blank answer")
    result = evaluate_answer(Q, M, "   ", 5, generate_fn=must_not_be_called)
    assert result == blank_answer_result(5)
    assert result["marks_awarded"] == 0


def test_blank_answer_works_even_without_api_key():
    with patch.dict(os.environ, {}, clear=True):
        assert evaluate_answer(Q, M, "", 5)["marks_awarded"] == 0


def test_irrelevant_answer_low_marks_accepted():
    zero = {k: 0 for k in ["conceptual_correctness", "key_points_covered",
                           "completeness", "relevance", "clarity"]}
    result = evaluate_answer(Q, M, "I like cricket", 5,
                             generate_fn=lambda p: fake_response(criteria_breakdown=zero))
    assert result["marks_awarded"] == 0 and result["remark"] == "Poor"


def test_very_short_and_very_long_answers_are_accepted():
    for answer in ("a", "word " * 1000):
        assert evaluate_answer(Q, M, answer, 5, generate_fn=lambda p: fake_response())


def test_missing_api_key_raises_config_error():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ConfigError, match="GEMINI_API_KEY"):
            evaluate_answer(Q, M, S, 5)


def test_placeholder_api_key_treated_as_missing():
    with patch.dict(os.environ, {"GEMINI_API_KEY": "your_api_key_here"}, clear=True):
        with pytest.raises(ConfigError):
            evaluate_answer(Q, M, S, 5)


def test_invalid_inputs_raise_validation_error():
    with pytest.raises(ValidationError) as info:
        evaluate_answer("", M, S, 0, generate_fn=lambda p: fake_response())
    assert len(info.value.errors) == 2


def test_api_connection_failure_becomes_api_error():
    def boom(prompt):
        raise ConnectionError("network down")
    with pytest.raises(APIError, match="internet"):
        evaluate_answer(Q, M, S, 5, generate_fn=boom)


def test_malformed_response_retries_then_fails_cleanly():
    calls = []
    def bad(prompt):
        calls.append(1)
        return "this is not json"
    with pytest.raises(ResponseFormatError):
        evaluate_answer(Q, M, S, 5, generate_fn=bad)
    assert len(calls) == 2


def test_malformed_then_valid_response_recovers():
    replies = iter(["garbage", fake_response()])
    result = evaluate_answer(Q, M, S, 5, generate_fn=lambda p: next(replies))
    assert result["marks_awarded"] == 4.0


def test_missing_criteria_key_is_rejected():
    bad = fake_response(criteria_breakdown={"conceptual_correctness": 1})
    with pytest.raises(ResponseFormatError):
        evaluate_answer(Q, M, S, 5, generate_fn=lambda p: bad)


def test_non_numeric_score_is_rejected():
    with pytest.raises(ResponseFormatError):
        normalize_result({"criteria_breakdown": {k: "lots" for k in
            ["conceptual_correctness", "key_points_covered", "completeness", "relevance", "clarity"]}}, 5)


class _Err(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


def test_exception_translation_never_leaks_key():
    secret = "AIza-SECRET-KEY"
    err = translate_exception(RuntimeError(f"weird failure with {secret}"), secret)
    assert secret not in str(err)
    assert isinstance(translate_exception(_Err(400, "API key not valid"), secret), ConfigError)
    assert isinstance(translate_exception(_Err(429, "quota"), secret), APIError)
    assert isinstance(translate_exception(_Err(503, "overloaded"), secret), APIError)


@pytest.mark.parametrize("pct,remark", [(100, "Excellent"), (80, "Good"), (60, "Satisfactory"),
                                        (30, "Needs Improvement"), (0, "Poor")])
def test_remark_bands(pct, remark):
    assert remark_for(pct) == remark
