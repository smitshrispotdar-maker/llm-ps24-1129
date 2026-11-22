"""Central configuration: API key, model name, rubric weights and limits."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")  # silently does nothing if .env is absent

DEFAULT_MODEL = "gemini-2.5-flash"
PLACEHOLDER_KEY = "your_api_key_here"

# Input limits (protect against accidental huge pastes)
MAX_MARKS_LIMIT = 100
MAX_TEXT_CHARS = 8000

# Rubric: criterion key -> weight (must sum to 1.0)
CRITERIA_WEIGHTS = {
    "conceptual_correctness": 0.40,
    "key_points_covered": 0.30,
    "completeness": 0.15,
    "relevance": 0.10,
    "clarity": 0.05,
}
CRITERIA_LABELS = {
    "conceptual_correctness": "Conceptual correctness",
    "key_points_covered": "Key points covered",
    "completeness": "Completeness",
    "relevance": "Relevance",
    "clarity": "Clarity",
}


def get_api_key():
    """Return the Gemini API key from the environment, or None if missing.

    Read at call time (not import time) so tests and users can change it.
    """
    key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not key or key == PLACEHOLDER_KEY:
        return None
    return key


def get_model_name():
    return (os.getenv("GEMINI_MODEL") or DEFAULT_MODEL).strip()
