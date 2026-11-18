from collections import Counter
from threading import Lock

from services.pdf_service import extract_text
from services.ai_service import extract_topics, extract_questions, map_questions_to_topics


class PYQService:
    def __init__(self, syllabus_pdf_path, pyq_pdf_path):
        self.syllabus_pdf_path = str(syllabus_pdf_path)
        self.pyq_pdf_path = str(pyq_pdf_path)
        self._cache = None   # (topics, questions, mapping) after first analysis
        self._lock = Lock()  # stops 3 parallel requests each paying the Gemini cost

    def _analyse(self):
        """DEMO MODE: Returns hardcoded data when Gemini API is unavailable."""
        # TODO: Uncomment the real analysis block below once Google API recovers
        # with self._lock:
        #     if self._cache is None:
        #         topics = extract_topics(extract_text(self.syllabus_pdf_path))
        #         questions = extract_questions(extract_text(self.pyq_pdf_path))
        #         mapping = map_questions_to_topics(questions, topics)
        #         self._cache = (topics, questions, mapping)
        #     return self._cache
        
        # Hardcoded fallback data matching the exact structure Gemini returns
        if self._cache is None:
            demo_topics = [
                {"name": "Normalization & ER Models", "unit": "Unit 1", "difficulty": "hard"},
                {"name": "Relational Algebra & SQL", "unit": "Unit 2", "difficulty": "medium"},
                {"name": "Transactions & Concurrency", "unit": "Unit 3", "difficulty": "easy"},
                {"name": "Indexing & Query Optimization", "unit": "Unit 4", "difficulty": "medium"}
            ]
            # Maps question indices to topic indices (-1 means no match)
            demo_mapping = {0: 0, 1: 0, 2: 1, 3: 1, 4: 2, 5: 3} 
            self._cache = (demo_topics, [], demo_mapping)
        return self._cache

    def invalidate(self):
        """Drop the cached analysis (call after replacing the PDFs)."""
        with self._lock:
            self._cache = None

    def get_topic_frequencies(self) -> dict:
        topics, questions, mapping = self._analyse()

        mapped_topics = []
        for qi, ti in mapping.items():
            if 0 <= ti < len(topics):
                t_obj = topics[ti]
                t_name = t_obj.get("name") or t_obj.get("topic")
                if t_name:
                    mapped_topics.append(t_name)

        return dict(Counter(mapped_topics))

    def get_unit_weightage(self) -> dict:
        topics, questions, mapping = self._analyse()

        unit_counts = Counter()
        for qi, ti in mapping.items():
            if 0 <= ti < len(topics):
                t_obj = topics[ti]
                unit = t_obj.get("unit")
                if unit:
                    unit_counts[unit] += 1

        return dict(unit_counts)