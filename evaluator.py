"""Core evaluation logic: validation, Gemini call, JSON parsing and score checks.

Everything except `call_gemini` is deterministic and unit-testable without an API key.
"""
import json
import math
import re

from config import (
    CRITERIA_WEIGHTS,
    MAX_MARKS_LIMIT,
    MAX_TEXT_CHARS,
    get_api_key,
    get_model_name,
)
from prompts import SYSTEM_INSTRUCTION, build_prompt, criteria_max_marks

MAX_ATTEMPTS = 2  # one retry if Gemini returns malformed JSON


# ---------------------------------------------------------------- exceptions
class EvaluatorError(Exception):
    """Base class for all expected application errors."""


class ValidationError(EvaluatorError):
    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


class ConfigError(EvaluatorError):
    """Missing/invalid API key or missing SDK."""


class APIError(EvaluatorError):
    """Gemini request failed (network, quota, server...)."""


class ResponseFormatError(EvaluatorError):
    """Gemini replied, but not with usable JSON."""


# ------------------------------------------------------------------ helpers
def format_number(x):
    """4.0 -> '4', 1.8 -> '1.8', 0.125 -> '0.13'."""
    return f"{x:.2f}".rstrip("0").rstrip(".")


def remark_for(percentage):
    if percentage >= 90:
        return "Excellent"
    if percentage >= 75:
        return "Good"
    if percentage >= 50:
        return "Satisfactory"
    if percentage >= 25:
        return "Needs Improvement"
    return "Poor"


# --------------------------------------------------------------- validation
def validate_inputs(question, model_answer, student_answer, max_marks):
    """Return a list of error messages (empty list = valid).

    A blank student answer is NOT an input error: the rubric says it must
    score zero, so `evaluate_answer` handles it locally.
    """
    errors = []
    if not isinstance(question, str) or not question.strip():
        errors.append("Question is required.")
    if not isinstance(model_answer, str) or not model_answer.strip():
        errors.append("Model answer is required.")
    if student_answer is not None and not isinstance(student_answer, str):
        errors.append("Student answer must be text.")

    for name, text in (("Question", question), ("Model answer", model_answer),
                       ("Student answer", student_answer)):
        if isinstance(text, str) and len(text) > MAX_TEXT_CHARS:
            errors.append(f"{name} is too long (limit {MAX_TEXT_CHARS} characters).")

    if isinstance(max_marks, bool) or not isinstance(max_marks, (int, float)) \
            or math.isnan(max_marks) or math.isinf(max_marks):
        errors.append("Maximum marks must be a number.")
    elif max_marks <= 0:
        errors.append("Maximum marks must be greater than zero.")
    elif max_marks > MAX_MARKS_LIMIT:
        errors.append(f"Maximum marks cannot exceed {MAX_MARKS_LIMIT}.")
    return errors


# ------------------------------------------------------------ JSON handling
def parse_json_response(text):
    """Turn raw model text into a dict. Tolerates ```json fences and extra prose."""
    if not isinstance(text, str) or not text.strip():
        raise ResponseFormatError("Gemini returned an empty response.")
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise ResponseFormatError("Gemini's response did not contain JSON.")
        try:
            data = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError as exc:
            raise ResponseFormatError("Gemini returned malformed JSON.") from exc
    if not isinstance(data, dict):
        raise ResponseFormatError("Gemini's JSON was not an object.")
    return data


def _to_float(value, field):
    if isinstance(value, bool):
        raise ResponseFormatError(f"'{field}' must be a number.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ResponseFormatError(f"'{field}' must be a number.") from None
    if math.isnan(number) or math.isinf(number):
        raise ResponseFormatError(f"'{field}' must be a finite number.")
    return number


def _to_list(value, field):
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    raise ResponseFormatError(f"'{field}' must be a list.")


def normalize_result(data, max_marks):
    """Validate the LLM JSON and enforce score boundaries.

    The five criterion scores are the source of truth: each is clamped to its
    allowed maximum, and the total/percentage/remark are recomputed from them.
    This guarantees 0 <= marks <= max_marks even if the model miscalculates.
    """
    raw = data.get("criteria_breakdown")
    if not isinstance(raw, dict):
        raise ResponseFormatError("Missing 'criteria_breakdown' in response.")
    caps = criteria_max_marks(max_marks)
    breakdown = {}
    for key in CRITERIA_WEIGHTS:
        if key not in raw:
            raise ResponseFormatError(f"Missing criterion '{key}' in response.")
        value = _to_float(raw[key], key)
        breakdown[key] = round(min(max(value, 0.0), caps[key]), 2)

    marks = round(min(max(sum(breakdown.values()), 0.0), float(max_marks)), 2)
    percentage = round(marks / max_marks * 100, 1)
    feedback = data.get("feedback")
    feedback = feedback.strip() if isinstance(feedback, str) else ""

    return {
        "marks_awarded": marks,
        "maximum_marks": max_marks,
        "percentage": percentage,
        "criteria_breakdown": breakdown,
        "criteria_max": {k: round(v, 2) for k, v in caps.items()},
        "correct_points": _to_list(data.get("correct_points"), "correct_points"),
        "missing_points": _to_list(data.get("missing_points"), "missing_points"),
        "incorrect_points": _to_list(data.get("incorrect_points"), "incorrect_points"),
        "feedback": feedback or "No feedback was provided by the evaluator.",
        "remark": remark_for(percentage),  # derived, so it always matches the score
        "teacher_review_notes": _to_list(data.get("teacher_review_notes"),
                                         "teacher_review_notes"),
    }


def blank_answer_result(max_marks):
    """Zero-mark result for an empty student answer (no API call needed)."""
    caps = criteria_max_marks(max_marks)
    return {
        "marks_awarded": 0.0,
        "maximum_marks": max_marks,
        "percentage": 0.0,
        "criteria_breakdown": {k: 0.0 for k in CRITERIA_WEIGHTS},
        "criteria_max": {k: round(v, 2) for k, v in caps.items()},
        "correct_points": [],
        "missing_points": ["No answer was provided."],
        "incorrect_points": [],
        "feedback": "The answer was left blank, so no marks can be awarded. "
                    "Attempt the question using the key concepts from the syllabus.",
        "remark": "Poor",
        "teacher_review_notes": [],
    }


# ------------------------------------------------------------- Gemini call
def _redact(text, api_key):
    text = str(text)
    return text.replace(api_key, "[REDACTED]") if api_key else text


def translate_exception(exc, api_key=None):
    """Convert any SDK/network exception into a friendly APIError/ConfigError."""
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    message = str(exc).lower()
    name = type(exc).__name__
    if code in (401, 403) or "api key" in message or "api_key" in message:
        return ConfigError("Gemini rejected the API key. Check GEMINI_API_KEY in your .env file.")
    if code == 429 or "quota" in message or "resource_exhausted" in message:
        return APIError("Gemini rate limit or quota reached. Wait a minute and try again.")
    if code == 404:
        return APIError("Model not found. Check GEMINI_MODEL in your .env file.")
    if isinstance(code, int) and code >= 500:
        return APIError("Gemini is temporarily unavailable. Please try again shortly.")
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)) or any(
            s in name for s in ("Connect", "Timeout", "Network")):
        return APIError("Could not reach Gemini. Check your internet connection and try again.")
    return APIError(f"Gemini request failed ({name}): {_redact(exc, api_key)[:200]}")


def call_gemini(prompt, api_key, model_name):
    """Send the prompt to Gemini and return the raw JSON text."""
    try:
        from google import genai
        from google.genai import types
        from pydantic import BaseModel
    except ImportError as exc:
        raise ConfigError(
            "The 'google-genai' package is not installed. Run: pip install -r requirements.txt"
        ) from exc

    class Criteria(BaseModel):
        conceptual_correctness: float
        key_points_covered: float
        completeness: float
        relevance: float
        clarity: float

    class Evaluation(BaseModel):
        marks_awarded: float
        maximum_marks: float
        percentage: float
        criteria_breakdown: Criteria
        correct_points: list[str]
        missing_points: list[str]
        incorrect_points: list[str]
        feedback: str
        remark: str
        teacher_review_notes: list[str]

    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=60_000))
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.2,
            response_mime_type="application/json",
            response_schema=Evaluation,
        ),
    )
    text = response.text
    if not text:
        raise ResponseFormatError("Gemini returned no text (the response may have been blocked).")
    return text


# -------------------------------------------------------------- public API
def evaluate_answer(question, model_answer, student_answer, max_marks,
                    *, generate_fn=None, api_key=None, model_name=None):
    """Evaluate one answer and return a validated result dict.

    `generate_fn(prompt) -> str` can be injected to mock Gemini in tests.
    """
    student_answer = student_answer or ""
    errors = validate_inputs(question, model_answer, student_answer, max_marks)
    if errors:
        raise ValidationError(errors)

    if not student_answer.strip():
        return blank_answer_result(max_marks)

    key = api_key or get_api_key()
    if generate_fn is None:
        if not key:
            raise ConfigError(
                "GEMINI_API_KEY is missing. Copy .env.example to .env and add your key."
            )
        model = model_name or get_model_name()
        generate_fn = lambda p: call_gemini(p, key, model)  # noqa: E731

    prompt = build_prompt(question.strip(), model_answer.strip(), student_answer.strip(), max_marks)
    last_error = None
    for _ in range(MAX_ATTEMPTS):
        try:
            raw = generate_fn(prompt)
        except EvaluatorError:
            raise
        except Exception as exc:  # network / SDK errors
            raise translate_exception(exc, key) from exc
        try:
            return normalize_result(parse_json_response(raw), max_marks)
        except ResponseFormatError as exc:
            last_error = exc
    raise ResponseFormatError(
        f"Gemini returned an unusable response after {MAX_ATTEMPTS} attempts: {last_error}"
    )
