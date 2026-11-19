import os
import json
import time


def _load_credentials():
    try:
        import streamlit as st
        k = st.secrets.get("GEMINI_API_KEY", "")
        if k:
            return k
    except Exception:
        pass
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    return os.getenv("GEMINI_API_KEY", "")


api_key = _load_credentials()
if not api_key:
    raise RuntimeError("GEMINI_API_KEY missing. Set it in .env / Render env / Streamlit Secrets.")

from google import genai
from google.genai import types

client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=60000))

# Try these in order; 404 skips to the next, 503/429 retries with backoff.
_default = "gemini-flash-latest,gemini-3.8-flash,gemini-3.7-flash,gemini-3.6-flash,gemini-3.5-flash"
_models = os.getenv("GEMINI_MODELS", _default)
_single = os.getenv("GEMINI_MODEL", "")
CANDIDATE_MODELS = list(dict.fromkeys(([ _single ] if _single else []) + [m.strip() for m in _models.split(",") if m.strip()]))


def _generate_json(prompt):
    last_err = None
    for model in CANDIDATE_MODELS:
        for attempt in range(3):
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json"),
                )
                return resp.text
            except Exception as e:
                msg = str(e)
                last_err = e
                if "404" in msg or "NOT_FOUND" in msg:
                    break                      # model unavailable -> next model
                if any(s in msg for s in ("429", "503", "504", "UNAVAILABLE", "DEADLINE", "RESOURCE_EXHAUSTED")):
                    time.sleep(2 ** attempt * 2)   # 2s, 4s, 8s backoff
                    continue
                raise RuntimeError(f"Gemini call failed: {type(e).__name__}: {e}")
    raise RuntimeError(f"All models failed after retries: {last_err}")


def extract_topics(syllabus_text):
    prompt = f"""Extract the study topics from this syllabus.
Return ONLY JSON in this format:
{{"topics": [{{"name": "...", "unit": "...", "estimated_hours": 2, "difficulty": "easy"}}]}}
Rules: difficulty must be easy, medium or hard. Do not invent topics.

SYLLABUS:
{syllabus_text}
"""
    return _validate_topics(_generate_json(prompt))


def _validate_topics(raw_text):
    try:
        topics = json.loads(raw_text)["topics"]
        for t in topics:
            assert isinstance(t["name"], str) and t["name"].strip()
            assert t["difficulty"] in ("easy", "medium", "hard")
            assert isinstance(t["estimated_hours"], (int, float))
    except Exception as e:
        raise ValueError(f"Bad AI output: {e}")
    return topics


def extract_questions(pyq_text):
    prompt = f"""Extract every exam question from this question paper.
Return ONLY JSON in this format:
{{"questions": [{{"question_text": "...", "year": 2023, "marks": 5}}]}}
Rules: year is the exam year as a number. marks is a number.
Copy the question text exactly. Do not invent questions.

QUESTION PAPER:
{pyq_text}
"""
    raw = _generate_json(prompt)
    try:
        questions = json.loads(raw)["questions"]
        for q in questions:
            assert isinstance(q["question_text"], str) and q["question_text"].strip()
            assert isinstance(q["year"], int)
            assert isinstance(q["marks"], (int, float))
    except Exception as e:
        raise ValueError(f"Bad AI output: {e}")
    return questions


def map_questions_to_topics(questions, topics):
    topic_list = "\n".join(f"{i}: {t['name']}" for i, t in enumerate(topics))
    question_list = "\n".join(f"{i}: {q['question_text']}" for i, q in enumerate(questions))
    prompt = f"""Match each exam question to the syllabus topic it belongs to.
Return ONLY JSON in this format:
{{"mappings": [{{"question_index": 0, "topic_index": 0}}]}}
Rules: use only the numbers given below. Give one topic per question.
If no topic fits, use -1. Do not invent numbers.

TOPICS:
{topic_list}

QUESTIONS:
{question_list}
"""
    raw = _generate_json(prompt)
    try:
        mappings = json.loads(raw)["mappings"]
        result = {}
        for m in mappings:
            qi, ti = m["question_index"], m["topic_index"]
            assert isinstance(qi, int) and 0 <= qi < len(questions)
            assert isinstance(ti, int) and -1 <= ti < len(topics)
            result[qi] = ti
    except Exception as e:
        raise ValueError(f"Bad AI output: {e}")
    for qi in range(len(questions)):
        result.setdefault(qi, -1)
    return result