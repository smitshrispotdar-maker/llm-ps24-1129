# 📝 AI Answer Sheet Evaluator

Intelligent descriptive answer evaluation using Generative AI (Google Gemini 3.8 Flash).

## Problem Statement (PS 24)
Checking descriptive answers manually is time-consuming. This application compares a student's
answer with a model answer and suggests marks along with detailed feedback.

## Features
- Inputs: question, model answer, student answer, maximum marks
- Examiner-style prompt with a weighted rubric (40 / 30 / 15 / 10 / 5) scaled to any maximum marks
- Judges **meaning**, not exact wording; partial marks; missing and incorrect points; flags doubtful model answers for teacher review
- Structured JSON output, validated and score-clamped in code (marks can never exceed the maximum)
- Dashboard: marks, percentage, remark, progress bar, criteria breakdown, green/orange/red point lists, feedback
- PDF report download, Clear All, demo mode (7 sample cases), loading spinner, friendly error messages
- Blank answers score zero locally (no API call)

## Technology Stack
Python 3.10+ · Streamlit · Google Gemini 2.5 Flash via `google-genai` · python-dotenv · ReportLab · pytest

## Workflow
```
Inputs -> validate -> build prompt -> Gemini (JSON) -> parse + validate + clamp -> dashboard -> PDF
```
| File | Role |
|---|---|
| `app.py` | Streamlit UI |
| `evaluator.py` | validation, Gemini call, JSON parsing, score boundaries |
| `prompts.py` | examiner prompt |
| `config.py` | API key, model, rubric weights |
| `report_generator.py` | PDF report |

## Installation (macOS)
```bash
cd answer-sheet-evaluator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
open -e .env        # replace your_api_key_here with your real key, then save
```

## Gemini API Key
1. Open <https://aistudio.google.com/apikey> and sign in with a Google account.
2. Click **Create API key** and copy it.
3. Paste it into `.env` as `GEMINI_API_KEY=...`. Never commit `.env` (it is in `.gitignore`).
4. The model is configurable: set `GEMINI_MODEL` in `.env` (default `gemini-2.5-flash`).

## Run
```bash
source .venv/bin/activate
streamlit run app.py
```
Opens at <http://localhost:8501>.

## Sample Demonstration
Pick a case under **Demo mode**, click **Load sample**, then **Evaluate Answer**. The three
assignment examples (AI agent hallucination, SQL DELETE vs DROP, supervised vs unsupervised) are
cases 1-3. Cases 4-7 cover: fully correct, reworded, completely incorrect, irrelevant. For a blank
answer, empty the student box. Marks are never hardcoded; Gemini evaluates each case live.

## Screenshots
Add your own after running the app (see `screenshots/`):
`screenshots/input.png`, `screenshots/dashboard.png`, `screenshots/pdf_report.png`

## Testing
```bash
source .venv/bin/activate
pytest -v
```
Tests mock Gemini, so they need no API key and make no paid calls. They cover input validation,
JSON parsing, score boundaries (max marks 2, 5, 10, 15), blank/irrelevant/short/long answers,
missing key, connection failure, malformed responses and PDF generation.
Live checks needing your key are done manually via the demo cases.

## Future Enhancements
Batch evaluation from CSV, OCR for handwritten sheets, multi-question exams, teacher override of
marks, rubric editor, support for Indian-language answers and PDF fonts, result history.
