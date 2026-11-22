"""PDF report generation."""
from io import BytesIO

from pypdf import PdfReader

from evaluator import blank_answer_result, normalize_result
from report_generator import generate_pdf_report

CRIT = {"conceptual_correctness": 1.8, "key_points_covered": 1.2, "completeness": 0.6,
        "relevance": 0.3, "clarity": 0.1}


def _result(**extra):
    data = {"criteria_breakdown": CRIT, "correct_points": ["Explained the idea"],
            "missing_points": ["Memory persistence"], "incorrect_points": ["Wrong claim"],
            "feedback": "Add the missing concept.", **extra}
    return normalize_result(data, 5)


def _text(pdf_bytes):
    return "\n".join(p.extract_text() for p in PdfReader(BytesIO(pdf_bytes)).pages)


def test_pdf_is_valid_and_contains_key_sections():
    pdf = generate_pdf_report(_result(), "Why X?", "Because Y.", "Because Z.")
    assert pdf.startswith(b"%PDF")
    text = _text(pdf)
    for expected in ("AI Answer Sheet Evaluator", "Why X?", "Because Y.", "Because Z.",
                     "4 / 5", "80%", "Conceptual correctness", "Correct Points",
                     "Missing Points", "Incorrect Points", "Add the missing concept."):
        assert expected in text


def test_pdf_handles_blank_answer_result():
    pdf = generate_pdf_report(blank_answer_result(10), "Q", "M", "")
    assert pdf.startswith(b"%PDF") and "(blank)" in _text(pdf)


def test_pdf_survives_markup_unicode_and_long_text():
    nasty = "<b>bold</b> & <unclosed ₹ नमस्ते \u201cquotes\u201d " + "long " * 3000
    pdf = generate_pdf_report(_result(), nasty, nasty, nasty)
    assert pdf.startswith(b"%PDF") and len(PdfReader(BytesIO(pdf)).pages) >= 2


def test_pdf_with_empty_point_lists():
    res = _result(correct_points=[], missing_points=[], incorrect_points=[])
    assert generate_pdf_report(res, "Q", "M", "S").startswith(b"%PDF")
