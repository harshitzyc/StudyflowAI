import json
from collections import Counter
from pathlib import Path
from threading import Lock

from services.pdf_service import extract_text
from services.ai_service import extract_topics, extract_questions, map_questions_to_topics

CACHE_FILE = Path(__file__).resolve().parent.parent / "analysis_cache.json"

# Instant fallback so the UI never hangs or errors when no cache exists yet.
_SAMPLE_TOPICS = [
    {"name": "Normalization & ER Models", "unit": "Unit 1", "estimated_hours": 6, "difficulty": "hard"},
    {"name": "Relational Algebra & SQL", "unit": "Unit 2", "estimated_hours": 6, "difficulty": "medium"},
    {"name": "Transactions & Concurrency", "unit": "Unit 3", "estimated_hours": 4, "difficulty": "easy"},
    {"name": "Indexing & Query Optimization", "unit": "Unit 4", "estimated_hours": 4, "difficulty": "medium"},
]
_SAMPLE_QUESTIONS = [
    {"question_text": "Explain 3NF with an example.", "year": 2023, "marks": 5},
    {"question_text": "Draw an ER diagram for a library system.", "year": 2022, "marks": 5},
    {"question_text": "Write SQL joins with examples.", "year": 2023, "marks": 5},
    {"question_text": "Relational algebra operations.", "year": 2021, "marks": 5},
    {"question_text": "GROUP BY and HAVING clauses.", "year": 2022, "marks": 5},
    {"question_text": "ACID properties.", "year": 2023, "marks": 5},
    {"question_text": "B+ tree indexing.", "year": 2022, "marks": 5},
    {"question_text": "BCNF decomposition.", "year": 2021, "marks": 5},
]
_SAMPLE_MAPPING = {0: 0, 1: 0, 2: 1, 3: 1, 4: 1, 5: 2, 6: 3, 7: 0}


class PYQService:
    def __init__(self, syllabus_pdf_path, pyq_pdf_path):
        self.syllabus_pdf_path = str(syllabus_pdf_path)
        self.pyq_pdf_path = str(pyq_pdf_path)
        self._cache = None
        self._lock = Lock()
        self._load_disk()

    # ---- web path: instant, never calls Gemini, never blocks ----
    def _analyse(self):
        if self._cache is not None:
            return self._cache
        return (_SAMPLE_TOPICS, _SAMPLE_QUESTIONS, _SAMPLE_MAPPING)

    @property
    def source(self):
        return "cache" if self._cache is not None else "sample"

    # ---- offline path: real Gemini, run via prewarm.py ----
    def analyse_live(self):
        with self._lock:
            print("[1/3] Extracting topics from syllabus...")
            topics = extract_topics(extract_text(self.syllabus_pdf_path))
            print(f"      {len(topics)} topics")
            print("[2/3] Extracting questions from PYQ...")
            questions = extract_questions(extract_text(self.pyq_pdf_path))
            print(f"      {len(questions)} questions")
            print("[3/3] Mapping questions to topics...")
            mapping = map_questions_to_topics(questions, topics)
            self._cache = (topics, questions, mapping)
            self._save_disk()
            print("Saved analysis_cache.json")

    def invalidate(self):
        self._cache = None
        try:
            CACHE_FILE.unlink(missing_ok=True)
        except Exception:
            pass

    def _load_disk(self):
        try:
            if CACHE_FILE.exists():
                d = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
                self._cache = (d["topics"], d["questions"],
                               {int(k): v for k, v in d["mapping"].items()})
        except Exception:
            pass

    def _save_disk(self):
        try:
            t, q, m = self._cache
            CACHE_FILE.write_text(json.dumps({"topics": t, "questions": q, "mapping": m}),
                                  encoding="utf-8")
        except Exception:
            pass

    def get_topic_frequencies(self) -> dict:
        topics, questions, mapping = self._analyse()
        mapped = []
        for qi, ti in mapping.items():
            if 0 <= ti < len(topics):
                name = topics[ti].get("name") or topics[ti].get("topic")
                if name:
                    mapped.append(name)
        return dict(Counter(mapped))

    def get_unit_weightage(self) -> dict:
        topics, questions, mapping = self._analyse()
        units = Counter()
        for qi, ti in mapping.items():
            if 0 <= ti < len(topics):
                u = topics[ti].get("unit")
                if u:
                    units[u] += 1
        return dict(units)