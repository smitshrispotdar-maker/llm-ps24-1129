"""Streamlit dashboard for the AI Answer Sheet Evaluator.  Run: streamlit run app.py"""
import html
import json

import streamlit as st

from config import BASE_DIR, CRITERIA_LABELS, CRITERIA_WEIGHTS, get_api_key, get_model_name
from evaluator import (
    APIError, ConfigError, EvaluatorError, ResponseFormatError, ValidationError,
    evaluate_answer, format_number, validate_inputs,
)
from report_generator import generate_pdf_report

st.set_page_config(page_title="AI Answer Sheet Evaluator", page_icon="📝", layout="wide")

GREEN, ORANGE, RED, NAVY = "#2E7D32", "#E65100", "#C62828", "#1F3A5F"

st.markdown(f"""
<style>
.hero {{background: linear-gradient(135deg, {NAVY}, #3B6EA5); padding: 1.6rem 2rem;
        border-radius: 14px; color: white; margin-bottom: 1.2rem;}}
.hero h1 {{color: white; margin: 0; font-size: 2.1rem;}}
.hero h4 {{color: #DCE8F5; margin: .2rem 0 .6rem 0; font-weight: 400;}}
.hero p  {{color: #EAF1F9; margin: 0; font-size: .95rem;}}
.pt {{padding: .55rem .8rem; margin-bottom: .45rem; border-radius: 6px; font-size: .93rem;}}
.pt-empty {{opacity: .6; font-style: italic; font-size: .9rem;}}
.pt-head {{font-weight: 700; font-size: 1.05rem; margin-bottom: .4rem;}}
.note {{border-left: 4px solid #F9A825; background: rgba(249,168,37,.12);
        padding: .6rem .8rem; border-radius: 6px; margin-bottom: .4rem;}}
</style>
""", unsafe_allow_html=True)


# ------------------------------------------------------------------ state
@st.cache_data
def load_samples():
    path = BASE_DIR / "sample_data" / "sample_answers.json"
    return json.loads(path.read_text(encoding="utf-8"))


SAMPLES = load_samples()
DEFAULTS = {"q_text": "", "model_text": "", "student_text": "", "max_marks": 5, "outcome": None}
for _k, _v in DEFAULTS.items():
    st.session_state.setdefault(_k, _v)


def load_sample():
    sample = next(s for s in SAMPLES if s["title"] == st.session_state["sample_choice"])
    st.session_state.update(q_text=sample["question"], model_text=sample["model_answer"],
                            student_text=sample["student_answer"],
                            max_marks=int(sample["max_marks"]), outcome=None)


def clear_all():
    st.session_state.update(DEFAULTS)


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("⚙️ Status")
    if get_api_key():
        st.success("Gemini API key detected")
    else:
        st.error("GEMINI_API_KEY missing. Copy .env.example to .env and add your key.")
    st.caption(f"Model: `{get_model_name()}`")
    st.divider()
    st.subheader("Marking rubric")
    for key, weight in CRITERIA_WEIGHTS.items():
        st.write(f"- {CRITERIA_LABELS[key]}: **{int(weight * 100)}%**")
    st.caption("AI-suggested marks are advisory. A teacher should review the final marks.")

# ----------------------------------------------------------------- header
st.markdown("""
<div class="hero">
  <h1>📝 AI Answer Sheet Evaluator</h1>
  <h4>Intelligent descriptive answer evaluation using Generative AI</h4>
  <p>Enter the question, the model answer and the student's answer. Gemini acts as an
  examiner, scores the answer against a weighted rubric on <em>meaning</em> (not exact words),
  and returns marks with detailed feedback.</p>
</div>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------ inputs
st.subheader("1. Enter answer details")
demo_col, demo_btn = st.columns([4, 1], vertical_alignment="bottom")
demo_col.selectbox("🎓 Demo mode: choose a sample case", [s["title"] for s in SAMPLES],
                   key="sample_choice")
demo_btn.button("Load sample", on_click=load_sample)

st.text_area("Examination question", key="q_text", height=90,
             placeholder="e.g. What is the difference between DELETE and DROP in SQL?")
left, right = st.columns(2)
left.text_area("Model answer (expected correct answer)", key="model_text", height=220)
right.text_area("Student answer", key="student_text", height=220)
st.number_input("Maximum marks", min_value=1, max_value=100, step=1, key="max_marks")

b1, b2, _ = st.columns([1.3, 1, 5])
evaluate_clicked = b1.button("✅ Evaluate Answer", type="primary")
b2.button("🗑️ Clear All", on_click=clear_all)

# -------------------------------------------------------------- evaluation
if evaluate_clicked:
    inputs = {"question": st.session_state["q_text"], "model_answer": st.session_state["model_text"],
              "student_answer": st.session_state["student_text"],
              "max_marks": st.session_state["max_marks"]}
    st.session_state["outcome"] = None
    problems = validate_inputs(**inputs)
    if problems:
        for p in problems:
            st.error(p)
    else:
        try:
            with st.spinner("Gemini is evaluating the answer..."):
                result = evaluate_answer(**inputs)
            st.session_state["outcome"] = {"result": result, "inputs": inputs}
        except ValidationError as exc:
            for p in exc.errors:
                st.error(p)
        except ConfigError as exc:
            st.error(f"⚠️ Configuration problem: {exc}")
        except APIError as exc:
            st.error(f"🌐 API error: {exc}")
        except ResponseFormatError as exc:
            st.error(f"🧩 The AI response could not be understood. Please try again. ({exc})")
        except EvaluatorError as exc:
            st.error(str(exc))
        except Exception:  # last-resort guard so the app never shows a raw traceback
            st.error("Unexpected error while evaluating. Please try again.")


# --------------------------------------------------------------- dashboard
def point_list(title, items, color, empty_text, icon):
    st.markdown(f'<div class="pt-head" style="color:{color}">{icon} {title}</div>', unsafe_allow_html=True)
    if not items:
        st.markdown(f'<div class="pt-empty">{html.escape(empty_text)}</div>', unsafe_allow_html=True)
    for item in items:
        st.markdown(f'<div class="pt" style="border-left:4px solid {color};'
                    f'background:{color}1A">{html.escape(item)}</div>', unsafe_allow_html=True)


outcome = st.session_state.get("outcome")
if outcome:
    res, inp = outcome["result"], outcome["inputs"]
    st.divider()
    st.subheader("2. Evaluation dashboard")
    if not inp["student_answer"].strip():
        st.info("The student answer was blank, so zero marks were awarded without calling the AI.")

    m1, m2, m3 = st.columns(3)
    m1.metric("Marks obtained", f"{format_number(res['marks_awarded'])} / {format_number(res['maximum_marks'])}")
    m2.metric("Percentage", f"{format_number(res['percentage'])}%")
    m3.metric("Performance remark", res["remark"])
    st.progress(min(max(res["percentage"] / 100, 0.0), 1.0))

    st.markdown("#### Criteria-wise marking breakdown")
    cols = st.columns(len(CRITERIA_WEIGHTS))
    for col, key in zip(cols, CRITERIA_WEIGHTS):
        got, cap = res["criteria_breakdown"][key], res["criteria_max"][key]
        col.markdown(f"**{CRITERIA_LABELS[key]}**  \n{int(CRITERIA_WEIGHTS[key] * 100)}% weight")
        col.progress(min(got / cap, 1.0) if cap else 0.0)
        col.caption(f"{format_number(got)} / {format_number(cap)}")

    st.markdown("")
    c1, c2, c3 = st.columns(3)
    with c1:
        point_list("Correct points", res["correct_points"], GREEN, "None identified.", "✅")
    with c2:
        point_list("Missing points", res["missing_points"], ORANGE, "Nothing important missing.", "⚠️")
    with c3:
        point_list("Incorrect points", res["incorrect_points"], RED, "No incorrect statements.", "❌")

    st.markdown("#### 💬 Improvement feedback")
    st.info(res["feedback"])
    for note in res.get("teacher_review_notes", []):
        st.markdown(f'<div class="note">🔎 <b>Teacher review:</b> {html.escape(note)}</div>',
                    unsafe_allow_html=True)

    try:
        pdf = generate_pdf_report(res, inp["question"], inp["model_answer"], inp["student_answer"])
        st.download_button("📄 Download PDF report", data=pdf,
                           file_name="evaluation_report.pdf", mime="application/pdf")
    except Exception:
        st.error("Could not generate the PDF report.")

st.caption("AI Answer Sheet Evaluator · PS 24 · Built with Streamlit and Google Gemini")
