"""StudyFlow Tutor — grounded, streaming chat with an offline fallback."""
import json
import os
from pathlib import Path

import requests

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM = (
    "You are StudyFlow Tutor, a concise exam-preparation tutor. "
    "Ground every answer in the ANALYSIS context below. Use short paragraphs or bullet lists, "
    "plain language, and concrete numbers from the context. If a question is outside the subject, "
    "steer the student back to exam preparation. Never invent marks, years or topics not present in the context."
)


def _secret(name, default=""):
    """Universal secret loader: works locally (.env) AND on Streamlit Cloud."""
    try:
        import streamlit as st
        v = st.secrets.get(name, "")
        if v:
            return v
    except Exception:
        pass
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    return os.getenv(name, default)


def _services():
    import main as app_module
    return app_module.pyq_service


def _context():
    try:
        svc = _services()
        w = svc.get_unit_weightage() or {}
        f = svc.get_topic_frequencies() or {}
        total = sum(w.values()) or 1
        lines = ["ANALYSIS (real data from the student's documents):"]
        lines.append("Units (mapped PYQ count, share, hours in a 20h plan):")
        for u, c in sorted(w.items(), key=lambda x: -x[1]):
            lines.append(f"- {u}: {c} questions ({c / total * 100:.0f}%), ~{20 * c / total:.1f} h")
        lines.append("Top topics by appearance count:")
        for t, c in sorted(f.items(), key=lambda x: -x[1])[:8]:
            lines.append(f"- {t}: asked {c}x")
        lines.append(f"Source documents: {Path(svc.syllabus_pdf_path).name}, {Path(svc.pyq_pdf_path).name}")
        return "\n".join(lines)
    except Exception:
        return "ANALYSIS: not available yet."


def _sanitize(messages):
    out = []
    for m in (messages or [])[-12:]:
        if isinstance(m, dict) and m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str):
            out.append({"role": m["role"], "content": m["content"][:4000]})
    return out


def _build_prompt(msgs):
    transcript = "\n".join(
        ("Student: " if m["role"] == "user" else "Tutor: ") + m["content"] for m in msgs
    )
    return f"{SYSTEM}\n\n{_context()}\n\nCONVERSATION:\n{transcript}\n\nTutor:"


def _stream_groq(prompt):
    r = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
        json={
            "model": "llama-3.1-8b-instant",  # HARDCODED: Current active Groq model
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.4,
            "stream": True,
        },
        stream=True,
        timeout=60,
    )
    r.raise_for_status()
    for line in r.iter_lines():
        if not line:
            continue
        text = line.decode("utf-8")
        if not text.startswith("data:"):
            continue
        payload = text[5:].strip()
        if payload == "[DONE]":
            break
        try:
            obj = json.loads(payload)
        except Exception:
            continue
        delta = (obj.get("choices") or [{}])[0].get("delta") or {}
        tok = delta.get("content")
        if tok:
            yield tok


def _stream_gemini(prompt):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.getenv("AQ.GEMINI_API_KEY"),
                          http_options=types.HttpOptions(timeout=60000))
    for chunk in client.models.generate_content_stream(
        model="gemini-3.8-flash",  # HARDCODED: Exact model Google told us to use
        contents=prompt,
    ):
        if getattr(chunk, "text", None):
            yield chunk.text


def _offline_tutor(msgs):
    q = (msgs[-1]["content"].lower() if msgs else "")
    try:
        svc = _services()
        w = svc.get_unit_weightage() or {}
        f = svc.get_topic_frequencies() or {}
    except Exception:
        w, f = {}, {}
    total = sum(w.values()) or 1
    units = sorted(w.items(), key=lambda x: -x[1])
    topics = sorted(f.items(), key=lambda x: -x[1])

    if any(k in q for k in ("hour", "plan", "schedule", "time", "split")):
        body = ["Here's a weightage-based split (20 h example):"]
        body += [f"- {u}: {c} questions → ~{20 * c / total:.1f} h" for u, c in units]
        body.append("Change the total hours on the dashboard and the plan rebuilds instantly.")
    elif any(k in q for k in ("weight", "important", "which unit", "dominat")):
        body = ["Unit importance, counted from mapped previous-year questions:"]
        body += [f"- {u}: {c} questions ({c / total * 100:.0f}% of the paper)" for u, c in units]
    elif any(k in q for k in ("topic", "repeat", "often", "frequen")):
        body = ["Most-repeated topics in your PYQs:"]
        body += [f"- {t}: asked {c}x" for t, c in topics[:6]]
    elif any(k in q for k in ("start", "begin", "first", "order")):
        top = units[0][0] if units else "the heaviest unit"
        body = [f"Start with {top} — it carries the largest share of mapped questions.",
                "Secure its high-mark questions first, then move down the weightage list."]
    elif any(k in q for k in ("pdf", "report", "export", "print")):
        body = ["Use the Export PDF button on the dashboard — it generates a printable ReportLab report",
                "with the unit table, weightage and recommended hours for your chosen total."]
    elif any(k in q for k in ("upload", "syllabus", "paper", "document", "source")):
        body = ["Open the Sources page and drag your syllabus and PYQ PDFs into the drop zones.",
                "The AI re-reads them and every chart updates automatically."]
    else:
        body = ["I'm answering offline right now (no live model reachable), using your real analysis:",
                f"- Heaviest unit: {units[0][0] if units else 'n/a'}",
                f"- Most-repeated topic: {topics[0][0] if topics else 'n/a'}",
                "Ask me about hours, weightage, repeated topics, study order, the PDF report, or uploading PDFs."]
    answer = " ".join(body)
    for sentence in answer.split(". "):
        yield sentence + ". "


def stream_reply(messages):
    msgs = _sanitize(messages)
    if not msgs:
        yield "Ask me anything about your syllabus, PYQs or study plan."
        return
    prompt = _build_prompt(msgs)

    if _secret("GROQ_API_KEY"):
        try:
            seen = False
            for tok in _stream_groq(prompt):
                seen = True
                yield tok
            if seen:
                return
        except Exception as e:
            print("chat groq failed:", e)

    if _secret("GEMINI_API_KEY"):
        try:
            seen = False
            for tok in _stream_gemini(prompt):
                seen = True
                yield tok
            if seen:
                return
        except Exception as e:
            print("chat gemini failed:", e)

    for chunk in _offline_tutor(msgs):
        yield chunk