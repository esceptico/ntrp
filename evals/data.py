import json
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class Question:
    question_id: str
    question_type: str
    question: str
    answer: str
    question_date: str
    haystack_session_ids: list[str]
    haystack_dates: list[str]
    haystack_sessions: list[list[dict]]
    answer_session_ids: list[str]


def load_questions(path: Path) -> list[Question]:
    raw = json.loads(path.read_text())
    return [
        Question(
            question_id=entry["question_id"],
            question_type=entry["question_type"],
            question=entry["question"],
            answer=entry["answer"],
            question_date=entry.get("question_date", ""),
            haystack_session_ids=entry["haystack_session_ids"],
            haystack_dates=entry.get("haystack_dates", []),
            haystack_sessions=entry["haystack_sessions"],
            answer_session_ids=entry["answer_session_ids"],
        )
        for entry in raw
    ]


def sample_questions(
    questions: list[Question], n_per_type: int = 10, seed: int = 42
) -> list[Question]:
    rng = random.Random(seed)
    by_type: dict[str, list[Question]] = defaultdict(list)
    for q in questions:
        by_type[q.question_type].append(q)

    sampled = []
    for qtype in sorted(by_type):
        qs = by_type[qtype]
        if len(qs) <= n_per_type:
            sampled.extend(qs)
        else:
            sampled.extend(rng.sample(qs, n_per_type))
    return sampled


def parse_date(date_str: str) -> datetime | None:
    if not date_str:
        return None
    try:
        cleaned = date_str
        for day in ("(Mon)", "(Tue)", "(Wed)", "(Thu)", "(Fri)", "(Sat)", "(Sun)"):
            cleaned = cleaned.replace(day, "").strip()
        # Collapse multiple spaces from removal
        while "  " in cleaned:
            cleaned = cleaned.replace("  ", " ")
        return datetime.strptime(cleaned, "%Y/%m/%d %H:%M").replace(tzinfo=UTC)
    except ValueError:
        return None
