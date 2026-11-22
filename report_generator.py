"""PDF evaluation report built with ReportLab (pure Python, works on macOS)."""
from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from config import CRITERIA_LABELS, CRITERIA_WEIGHTS
from evaluator import format_number

NAVY = colors.HexColor("#1F3A5F")
GREEN = colors.HexColor("#2E7D32")
ORANGE = colors.HexColor("#E65100")
RED = colors.HexColor("#C62828")
LIGHT = colors.HexColor("#F3F5F8")


def _safe(text):
    """Escape XML and make the text printable with the built-in Helvetica font.

    Characters outside Windows-1252 (e.g. Hindi/Chinese) cannot be drawn by the
    built-in fonts, so they are replaced by '?' instead of crashing.
    """
    text = str(text).encode("cp1252", errors="replace").decode("cp1252")
    return escape(text).replace("\n", "<br/>")


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], textColor=NAVY, fontSize=20, spaceAfter=2),
        "sub": ParagraphStyle("s", parent=base["Normal"], textColor=colors.grey, alignment=1, fontSize=9),
        "h": ParagraphStyle("h", parent=base["Heading2"], textColor=NAVY, fontSize=12,
                            spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("b", parent=base["Normal"], fontSize=10, leading=14),
    }


def _bullets(items, color, empty_text, st):
    if not items:
        return [Paragraph(f"<i>{_safe(empty_text)}</i>", st["body"])]
    hexcol = color.hexval()[2:]
    return [Paragraph(f'<font color="#{hexcol}">&bull;</font> {_safe(i)}', st["body"]) for i in items]


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)
    canvas.drawString(20 * mm, 10 * mm, "AI Answer Sheet Evaluator - AI-suggested marks; teacher review recommended.")
    canvas.drawRightString(A4[0] - 20 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def generate_pdf_report(result, question, model_answer, student_answer):
    """Return the evaluation report as PDF bytes."""
    st = _styles()
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            title="AI Answer Sheet Evaluation Report", author="AI Answer Sheet Evaluator")
    story = [
        Paragraph("AI Answer Sheet Evaluator", st["title"]),
        Paragraph(f"Evaluation Report &nbsp;|&nbsp; Generated {datetime.now():%d %b %Y, %H:%M}", st["sub"]),
        Spacer(1, 6), HRFlowable(width="100%", color=NAVY, thickness=1.2),
    ]

    # Score summary
    marks, mx = format_number(result["marks_awarded"]), format_number(result["maximum_marks"])
    summary = Table(
        [["Marks Obtained", "Maximum Marks", "Percentage", "Remark"],
         [f"{marks} / {mx}", mx, f"{format_number(result['percentage'])}%", result["remark"]]],
        colWidths=[42 * mm] * 4)
    summary.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, 1), 14), ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("BACKGROUND", (0, 1), (-1, 1), LIGHT), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7), ("BOX", (0, 0), (-1, -1), 0.5, colors.lightgrey),
    ]))
    story += [Spacer(1, 10), summary]

    for title, text in (("Question", question), ("Model Answer", model_answer),
                        ("Student Answer", student_answer.strip() or "(blank)")):
        story += [Paragraph(title, st["h"]), Paragraph(_safe(text), st["body"])]

    # Criteria breakdown
    rows = [["Criterion", "Weight", "Marks Awarded", "Out of"]]
    for key, weight in CRITERIA_WEIGHTS.items():
        rows.append([CRITERIA_LABELS[key], f"{int(weight * 100)}%",
                     format_number(result["criteria_breakdown"][key]),
                     format_number(result["criteria_max"][key])])
    rows.append(["Total", "100%", marks, mx])
    table = Table(rows, colWidths=[70 * mm, 25 * mm, 38 * mm, 25 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5), ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, LIGHT]),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E3E8EF")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [Paragraph("Criteria-wise Marking Breakdown", st["h"]), table]

    for title, items, color, empty in (
        ("Correct Points", result["correct_points"], GREEN, "None identified."),
        ("Missing Points", result["missing_points"], ORANGE, "None - all key points covered."),
        ("Incorrect Points", result["incorrect_points"], RED, "No incorrect statements found."),
    ):
        story.append(Paragraph(f'<font color="#{color.hexval()[2:]}">{title}</font>', st["h"]))
        story += _bullets(items, color, empty, st)

    story += [Paragraph("Improvement Feedback", st["h"]), Paragraph(_safe(result["feedback"]), st["body"])]
    if result.get("teacher_review_notes"):
        story.append(Paragraph("Notes for Teacher Review", st["h"]))
        story += _bullets(result["teacher_review_notes"], NAVY, "", st)

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
