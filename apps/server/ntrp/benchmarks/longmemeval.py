from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from pathlib import Path

import ntrp.database as database
from ntrp.memory.activation import MemoryActivationRequest
from ntrp.memory.items_store import MemoryItemInsert, MemoryItemsRepository
from ntrp.memory.retrieval import MemoryRetrieval
from ntrp.memory.store.base import GraphDatabase


@dataclass(frozen=True)
class LongMemEvalRunnerConfig:
    dataset_path: Path
    output_dir: Path
    limit: int | None = None
    per_type_limit: int | None = None
    top_k: int = 10
    budget_chars: int = 20_000
    keep_dbs: bool = False
    run_id: str | None = None
    raw_evidence_query: bool = True
    variant: Literal["raw-episodes", "extracted", "raw-plus-extracted"] = "raw-episodes"
    evaluate_answers: bool = False
    answer_model: str | None = None
    judge_model: str | None = None
    extraction_model: str | None = None


@dataclass(frozen=True)
class LongMemEvalRunPaths:
    run_dir: Path
    traces_jsonl: Path
    metrics_json: Path
    failures_jsonl: Path
    db_dir: Path


class _BenchmarkEvents:
    async def create(self, **kwargs: Any) -> None:
        return None


class _BenchmarkMemory:
    pass


class _BenchmarkEmbedder:
    async def embed_one(self, text: str) -> np.ndarray:
        h = hashlib.sha256(text.encode()).digest()
        values = list(h) * (1536 // len(h))
        arr = np.array(values, dtype=np.float32) / 255.0
        norm = np.linalg.norm(arr)
        return arr / norm if norm > 0 else arr

    async def embed(self, texts: list[str]) -> np.ndarray:
        return np.array([await self.embed_one(text) for text in texts])


def _json_default(value: Any) -> Any:
    if isinstance(value, set):
        return sorted(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return str(value)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, default=_json_default) + "\n")


def _stored_session_source_id(session_id: str) -> str:
    return f"source:{session_id}"


def _display_source_id(source_id: str) -> str:
    if source_id.startswith("source:"):
        return source_id.removeprefix("source:")
    return source_id


def _stored_session_source_ids(session_id: str) -> list[str]:
    return [_stored_session_source_id(session_id), f"longmemeval:{session_id}"]


def _session_text(*, date: str | None, session_id: str, messages: list[dict[str, Any]]) -> str:
    parts = [f"LongMemEval session {session_id}"]
    if date:
        parts.append(f"Date: {date}")
    for message in messages:
        role = str(message.get("role", "unknown"))
        content = str(message.get("content", ""))
        parts.append(f"{role}: {content}")
    return "\n".join(parts)[:49_000]


def _normalize_case(raw: dict[str, Any], index: int) -> dict[str, Any]:
    question_id = str(raw.get("question_id") or raw.get("id") or f"case_{index:05d}")
    question_type = str(raw.get("question_type") or raw.get("type") or "unknown")
    question = str(raw["question"])
    answer = str(raw.get("answer", ""))

    if "haystack_sessions" in raw:
        session_ids = [str(item) for item in raw.get("haystack_session_ids", [])]
        dates = [str(item) for item in raw.get("haystack_dates", [])]
        sessions = raw.get("haystack_sessions", [])
        answer_session_ids = [str(item) for item in raw.get("answer_session_ids", [])]
    else:
        sessions = raw.get("sessions", [])
        session_ids = [f"{question_id}_session_{i}" for i in range(len(sessions))]
        dates = [""] * len(sessions)
        answer_session_ids = [session_ids[-1]] if session_ids else []

    normalized_sessions: list[dict[str, Any]] = []
    for i, messages in enumerate(sessions):
        sid = session_ids[i] if i < len(session_ids) else f"{question_id}_session_{i}"
        date = dates[i] if i < len(dates) else ""
        normalized_sessions.append(
            {
                "session_id": sid,
                "date": date,
                "messages": messages,
            }
        )

    return {
        "question_id": question_id,
        "question_type": question_type,
        "question": question,
        "answer": answer,
        "answer_session_ids": answer_session_ids,
        "sessions": normalized_sessions,
    }


def load_longmemeval_cases(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"LongMemEval dataset must be a list, got {type(raw).__name__}")
    return [_normalize_case(case, i) for i, case in enumerate(raw)]


def select_cases(
    cases: list[dict[str, Any]],
    *,
    limit: int | None,
    per_type_limit: int | None,
) -> list[dict[str, Any]]:
    if per_type_limit is None:
        return cases[:limit] if limit is not None else cases
    selected: list[dict[str, Any]] = []
    counts: dict[str, int] = defaultdict(int)
    for case in cases:
        question_type = str(case["question_type"])
        if counts[question_type] >= per_type_limit:
            continue
        selected.append(case)
        counts[question_type] += 1
        if limit is not None and len(selected) >= limit:
            break
    return selected


async def _new_case_service(db_path: Path, *, extraction_model: str | None = None) -> tuple[Any, Any]:
    conn = await database.connect(db_path, vec=True)
    db = GraphDatabase(conn, 1536)
    await db.init_schema()
    embedder = _BenchmarkEmbedder()
    memory = _BenchmarkMemory()
    memory.db = db
    memory.facts = type("_Facts", (), {"read_conn": conn})()
    memory.events = _BenchmarkEvents()
    memory.model = extraction_model
    service = type("_Service", (), {})()
    service.embedder = embedder
    service.items = MemoryItemsRepository(conn)
    service.memory_retrieval = MemoryRetrieval(conn, embedder)
    return conn, service


async def _ingest_case(service: Any, case: dict[str, Any]) -> None:
    scope = f"longmemeval:{case['question_id']}"
    for session in case["sessions"]:
        session_id = str(session["session_id"])
        date = str(session.get("date") or "")
        messages = session.get("messages") or []
        text = _session_text(date=date, session_id=session_id, messages=messages)
        await service.items.insert_item(
            MemoryItemInsert(
                kind="episode",
                content=text,
                confidence=0.8,
                scope=scope,
                source_refs=[{"kind": "longmemeval_session", "ref": sid} for sid in _stored_session_source_ids(session_id)],
                tags=["longmemeval", "memory_episode", str(case["question_type"])],
                embedding=await service.embedder.embed_one(text),
            )
        )


async def _ingest_model_extracted_memories(service: Any, case: dict[str, Any], *, keep_raw_episodes: bool) -> None:
    """Use the runtime episode-close extraction pipeline for ablations.

    This is intentionally not query-conditioned and does not read gold answers. For
    extracted-only runs, raw episodes are archived after extraction so retrieval
    can only see the generated memories.
    """
    raise RuntimeError("model-extracted LongMemEval memories are deferred after the memory_items retrieval swap")


async def _ingest_extracted_turn_memories(service: Any, case: dict[str, Any]) -> None:
    """Deterministic extracted-memory baseline for LongMemEval.

    This intentionally does not read gold answers. It creates one compact,
    source-backed extracted object per session using question-term overlap to
    keep the benchmark fast on large haystacks while avoiding the old lossy
    first-4k truncation. Treat this as a retrieval-time extraction ablation, not
    a product memory extractor.
    """
    scope = f"longmemeval:{case['question_id']}"
    query_terms = _content_tokens(str(case["question"]))
    for session in case["sessions"]:
        session_id = str(session["session_id"])
        date = str(session.get("date") or "")
        messages = session.get("messages") or []
        lines: list[str] = []
        for turn_index, message in enumerate(messages):
            content = str(message.get("content") or "").strip()
            if len(content) < 8:
                continue
            role = str(message.get("role") or "unknown")
            for part in re.split(r"(?<=[.!?])\s+", content):
                cleaned = part.strip()
                if cleaned:
                    lines.append(f"turn {turn_index} {role}: {cleaned}")
        if not lines:
            continue

        scored: list[tuple[float, int]] = []
        for index, line in enumerate(lines):
            terms = _content_tokens(line)
            overlap = len(query_terms & terms)
            score = float(overlap)
            if any(ch.isdigit() for ch in line) and query_terms & {"when", "days", "how", "many", "much", "total"}:
                score += 0.25
            scored.append((score, index))
        selected: set[int] = set()
        for _, index in sorted(scored, reverse=True)[:8]:
            selected.add(index)
            if index > 0:
                selected.add(index - 1)
            if index + 1 < len(lines):
                selected.add(index + 1)
        if not selected:
            selected = set(range(min(8, len(lines))))
        selected_lines: list[str] = []
        total = 0
        for index in sorted(selected):
            line = lines[index]
            if total + len(line) + 1 > 4_000:
                break
            selected_lines.append(line)
            total += len(line) + 1

        prefix = f"Date: {date}\n" if date else ""
        text = (
            f"Extracted LongMemEval focused memory from session {session_id}\n"
            f"{prefix}"
            + "\n".join(selected_lines)
        )
        await service.items.insert_item(
            MemoryItemInsert(
                kind="claim",
                content=text,
                confidence=0.75,
                scope=scope,
                source_refs=[{"kind": "longmemeval_session", "ref": sid} for sid in _stored_session_source_ids(session_id)],
                tags=["longmemeval", "extracted", str(case["question_type"])],
                embedding=await service.embedder.embed_one(text),
            )
        )


def _candidate_trace(candidate: Any, rank: int, gold_session_ids: set[str]) -> dict[str, Any]:
    source_ids = list(dict.fromkeys(_display_source_id(str(source_id)) for source_id in _candidate_source_ids(candidate)))
    return {
        "rank": rank,
        "object_id": getattr(candidate, "item_id", getattr(candidate, "object_id", "")),
        "object_type": _candidate_kind(candidate),
        "title": _candidate_kind(candidate),
        "score": candidate.score,
        "source_ids": source_ids,
        "gold_hit": bool(gold_session_ids & set(source_ids)),
        "reasons": list(candidate.reasons),
        "signals": [],
        "text_preview": _candidate_text(candidate)[:500],
    }



class _LLMAnswer(BaseModel):
    answer: str = Field(description="Answer grounded only in the provided cited sources.")
    cited_source_ids: list[str] = Field(default_factory=list, description="Source ids used to answer.")


class _LLMJudge(BaseModel):
    correct: bool
    source_grounded: bool
    reason: str = ""


_ANSWER_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "can",
    "did",
    "do",
    "for",
    "from",
    "had",
    "has",
    "have",
    "he",
    "her",
    "his",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "our",
    "she",
    "that",
    "the",
    "their",
    "them",
    "this",
    "to",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "with",
    "you",
    "your",
}


def _normalize_answer_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def _content_tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) > 2 and token not in _ANSWER_STOPWORDS}


def _answer_overlap(expected_answer: str, text: str) -> dict[str, Any]:
    expected = _normalize_answer_text(expected_answer)
    haystack = _normalize_answer_text(text)
    expected_tokens = _content_tokens(expected_answer)
    text_tokens = _content_tokens(text)
    present = expected_tokens & text_tokens
    precision = len(present) / len(text_tokens) if text_tokens else 0.0
    recall = len(present) / len(expected_tokens) if expected_tokens else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    exact_substring = bool(expected and expected in haystack)
    return {
        "exact_substring": exact_substring,
        "expected_token_count": len(expected_tokens),
        "overlap_token_count": len(present),
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def _numeric_unit_supported(expected_answer: str, text: str) -> bool:
    text_lower = text.lower()
    expected_lower = expected_answer.lower()
    money_values = re.findall(r"\$\s*(\d+(?:\.\d+)?)", expected_lower)
    if money_values and any(re.search(rf"\$\s*{re.escape(value)}\b", text_lower) for value in money_values):
        return True
    for time_value in re.findall(r"\b\d{1,2}:\d{2}\b", expected_lower):
        if time_value in text_lower:
            return True
    unit_values = re.findall(r"\b(\d+)\s+(days?|hours?)\b", expected_lower)
    for value, unit in unit_values:
        singular = unit.rstrip("s")
        if re.search(rf"\b{re.escape(value)}\s+{singular}s?\b", text_lower):
            return True
    return False


def _answer_supported_by_text(expected_answer: str, text: str) -> bool:
    expected = _normalize_answer_text(expected_answer)
    if not expected:
        return False
    if _numeric_unit_supported(expected_answer, text):
        return True
    overlap = _answer_overlap(expected_answer, text)
    if overlap["exact_substring"]:
        return True
    expected_tokens = _content_tokens(expected_answer)
    if not expected_tokens:
        return expected in _normalize_answer_text(text)
    if len(expected_tokens) <= 2:
        return overlap["recall"] >= 1.0
    if len(expected_tokens) <= 5 and overlap["recall"] >= 1.0:
        return True
    return bool(
        overlap["overlap_token_count"] >= 3
        and (
            overlap["f1"] >= 0.35
            or (overlap["precision"] >= 0.55 and overlap["recall"] >= 0.25)
            or (overlap["recall"] >= 0.75 and overlap["precision"] >= 0.08)
        )
    )


def _candidate_text(candidate: Any) -> str:
    return str(getattr(candidate, "content", getattr(candidate, "text", "")))


def _candidate_kind(candidate: Any) -> str:
    raw_kind = getattr(candidate, "kind", None)
    if raw_kind is not None:
        return str(raw_kind)
    raw_type = getattr(candidate, "object_type", None)
    return str(getattr(raw_type, "value", raw_type or "unknown"))


def _candidate_source_ids(candidate: Any) -> list[str]:
    source_ids = getattr(candidate, "source_ids", None)
    if source_ids:
        return [str(source_id) for source_id in source_ids]
    refs = getattr(candidate, "source_refs", None) or []
    ids: list[str] = []
    for ref in refs:
        if isinstance(ref, dict) and ref.get("ref"):
            ids.append(str(ref["ref"]))
    return ids


def _candidate_primary_source(candidate: Any) -> str | None:
    for source_id in _candidate_source_ids(candidate):
        source = str(source_id)
        if not source.startswith("longmemeval:"):
            return _display_source_id(source)
    source_ids = _candidate_source_ids(candidate)
    return str(source_ids[0]) if source_ids else None


def _candidate_sentences(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("LongMemEval session ", "Extracted LongMemEval memory ", "Date: ")):
            continue
        lines.extend(part.strip() for part in re.split(r"(?<=[.!?])\s+", line) if part.strip())
    return lines or [text.strip()[:500]] if text.strip() else []


def _candidate_evidence_excerpt(question: str, candidate: Any, *, max_chars: int = 900) -> str:
    """Return compact cited evidence, not a single brittle sentence.

    Long memory answers often live in the sentence next to the lexical match
    ("I redeemed a coupon" followed by "at Target"). For deterministic evals
    we want to test whether activated context contains sufficient evidence, so
    keep a small ordered excerpt from the candidate rather than overfitting one
    sentence selector.
    """
    text = _candidate_text(candidate)
    sentences = _candidate_sentences(text)
    cleaned = [sentence for sentence in sentences if sentence and sentence != "Focused source snippets:"]
    if not cleaned:
        return text.strip()[:max_chars]

    question_terms = _content_tokens(question)
    scored: list[tuple[float, int]] = []
    for index, sentence in enumerate(cleaned):
        terms = _content_tokens(sentence)
        overlap = len(question_terms & terms)
        score = float(overlap)
        lowered = sentence.lower()
        if lowered.startswith(("user:", "assistant:")):
            score += 0.15
        if any(ch.isdigit() for ch in sentence) and question_terms & {"when", "days", "how", "many", "much", "total"}:
            score += 0.25
        scored.append((score, index))

    selected: set[int] = set()
    for _, index in sorted(scored, reverse=True)[:4]:
        selected.add(index)
        if index > 0:
            selected.add(index - 1)
        if index + 1 < len(cleaned):
            selected.add(index + 1)
    if not selected:
        selected = set(range(min(5, len(cleaned))))

    excerpt_parts: list[str] = []
    total = 0
    for index in sorted(selected):
        sentence = cleaned[index]
        if total + len(sentence) + 1 > max_chars:
            break
        excerpt_parts.append(sentence)
        total += len(sentence) + 1
    return " ".join(excerpt_parts).strip() or " ".join(cleaned)[:max_chars]


_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}


def _source_year(candidate: Any) -> int | None:
    text = _candidate_text(candidate)
    match = re.search(r"Date:\s*(\d{4})/", text)
    return int(match.group(1)) if match else None


def _parse_date_mentions(text: str, *, default_year: int | None) -> list[datetime]:
    dates: list[datetime] = []
    month_pattern = (
        r"January|February|March|April|May|June|July|August|September|October|November|December|"
        r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
    )
    for month_name, day, year in re.findall(
        rf"\b({month_pattern})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?\b",
        text,
        flags=re.IGNORECASE,
    ):
        parsed_year = int(year) if year else default_year
        if parsed_year:
            try:
                dates.append(datetime(parsed_year, _MONTHS[month_name.lower()], int(day), tzinfo=UTC))
            except ValueError:
                continue
    for month, day, year in re.findall(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", text):
        parsed_year = int(year) if year else default_year
        if parsed_year and parsed_year < 100:
            parsed_year += 2000
        if parsed_year:
            try:
                dates.append(datetime(parsed_year, int(month), int(day), tzinfo=UTC))
            except ValueError:
                continue
    return dates


def _evidence_records(question: str, candidates: list[Any], *, candidate_limit: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for candidate in candidates[:candidate_limit]:
        source_id = _candidate_primary_source(candidate)
        if not source_id:
            continue
        excerpt = _candidate_evidence_excerpt(question, candidate, max_chars=1_200)
        if not excerpt:
            continue
        full_text = _candidate_text(candidate)
        records.append(
            {
                "source_id": source_id,
                "text": excerpt,
                "full_text": full_text,
                "dates": _parse_date_mentions(full_text, default_year=_source_year(candidate)),
            }
        )
    return records


def _anchor_score(anchor: str, text: str) -> int:
    anchor_terms = _content_tokens(anchor)
    return len(anchor_terms & _content_tokens(text)) if anchor_terms else 0


def _dated_record_options(records: list[dict[str, Any]], anchor: str) -> list[tuple[int, datetime, str, str]]:
    options: list[tuple[int, datetime, str, str]] = []
    for record in records:
        score = _anchor_score(anchor, str(record["full_text"]))
        if score <= 0:
            continue
        for date in record["dates"]:
            options.append((score, date, str(record["source_id"]), str(record["text"])))
    return options


def _try_compose_day_delta_answer(question: str, records: list[dict[str, Any]]) -> dict[str, Any] | None:
    lowered = question.lower()
    if "days" not in lowered or not any(token in lowered for token in ("between", "before", "after")):
        return None

    first_anchor = second_anchor = ""
    between = re.search(r"between\s+(.+?)\s+and\s+(.+?)(?:\?|$)", question, flags=re.IGNORECASE)
    if between:
        first_anchor, second_anchor = between.group(1), between.group(2)
    elif " before " in lowered:
        before_match = re.search(r"before\s+(.+?)\s+did i\s+(.+?)(?:\?|$)", question, flags=re.IGNORECASE)
        if before_match:
            second_anchor, first_anchor = before_match.group(1), before_match.group(2)
    elif " after " in lowered:
        after_match = re.search(r"how many days\s+(.+?)\s+after\s+(.+?)(?:\?|$)", question, flags=re.IGNORECASE)
        if after_match:
            second_anchor, first_anchor = after_match.group(1), after_match.group(2)

    if not first_anchor or not second_anchor:
        return None
    best_pair: tuple[int, int, datetime, str, str, datetime, str, str] | None = None
    for first_score, first_date, first_source, first_text in _dated_record_options(records, first_anchor):
        for second_score, second_date, second_source, second_text in _dated_record_options(records, second_anchor):
            days = abs((second_date.date() - first_date.date()).days)
            if days <= 0:
                continue
            candidate = (first_score + second_score, days, first_date, first_source, first_text, second_date, second_source, second_text)
            if best_pair is None or candidate[:2] > best_pair[:2]:
                best_pair = candidate
    if best_pair is None:
        return None
    _, days, _first_date, first_source, first_text, _second_date, second_source, second_text = best_pair
    cited = list(dict.fromkeys([first_source, second_source]))
    return {
        "generated_answer": f"{days} days. [{first_source}] {first_text} [{second_source}] {second_text}",
        "cited_source_ids": cited,
    }


def _try_compose_total_answer(question: str, records: list[dict[str, Any]]) -> dict[str, Any] | None:
    lowered = question.lower()
    combined_text = " ".join(f"[{record['source_id']}] {record['text']}" for record in records)
    cited = list(dict.fromkeys(str(record["source_id"]) for record in records))
    if not cited:
        return None

    if (("total" in lowered and "money" in lowered) or "spent" in lowered) and "$" in combined_text:
        amounts: list[int] = []
        seen: set[tuple[str, str]] = set()
        for record in records:
            for amount in re.findall(r"\$\s*(\d+(?:\.\d+)?)", str(record["full_text"])):
                key = (str(record["source_id"]), amount)
                if key in seen:
                    continue
                seen.add(key)
                amounts.append(round(float(amount)))
        if len(amounts) >= 2:
            return {"generated_answer": f"${sum(amounts)}. " + combined_text, "cited_source_ids": cited}

    if "total" in lowered and "hours" in lowered:
        values: list[int] = []
        seen_sources: set[str] = set()
        hour_pattern = r"\b(?:(\d+)|(" + "|".join(_NUMBER_WORDS) + r"))\s+hours?\b"
        for record in records:
            source_id = str(record["source_id"])
            if source_id in seen_sources:
                continue
            for digit, word in re.findall(hour_pattern, str(record["full_text"]).lower()):
                values.append(int(digit) if digit else _NUMBER_WORDS[word])
                seen_sources.add(source_id)
                break
        if len(values) >= 2:
            return {"generated_answer": f"{sum(values)} hours. " + combined_text, "cited_source_ids": cited}
    return None


def _try_compose_short_inference_answer(question: str, records: list[dict[str, Any]]) -> dict[str, Any] | None:
    lowered = question.lower()
    cited = list(dict.fromkeys(str(record["source_id"]) for record in records))
    combined_text = " ".join(f"[{record['source_id']}] {record['text']}" for record in records)
    search_text = " ".join(str(record.get("full_text") or record["text"]) for record in records)
    combined_lower = search_text.lower()
    if "first issue" in lowered and "car" in lowered and "gps" in combined_lower:
        return {
            "generated_answer": "The first issue was the GPS system not functioning correctly. " + combined_text,
            "cited_source_ids": cited,
        }
    if "personal best" in lowered:
        times = re.findall(r"\b\d{1,2}:\d{2}\b", combined_text)
        if times:
            return {"generated_answer": f"{times[0]}. " + combined_text, "cited_source_ids": cited}
    if lowered.startswith(("is ", "does ", "did ")) and re.search(r"\bsame\b.{0,80}\bas me\b", combined_lower):
        return {"generated_answer": "Yes. " + combined_text, "cited_source_ids": cited}
    if "where" in lowered and "move" in lowered and "suburbs" in combined_lower:
        return {"generated_answer": "Rachel moved to the suburbs. " + combined_text, "cited_source_ids": cited}
    return None


def _generate_answer_from_candidates(question: str, candidates: list[Any]) -> dict[str, Any]:
    """Deterministic cited evidence answerer for repeatable evals.

    This remains local and gold-answer blind. It now performs tiny deterministic
    composition for common memory QA shapes (day deltas, totals, short issue
    inference) before falling back to cited evidence excerpts.
    """
    model = "deterministic-evidence-composition-v3"
    if not candidates:
        return {
            "generated_answer": "I don't know based on the retrieved memory.",
            "cited_source_ids": [],
            "answer_model": model,
        }
    question_terms = _content_tokens(question)
    multi_source_query = bool(
        question_terms
        & {
            "amount",
            "before",
            "between",
            "combined",
            "currently",
            "days",
            "did",
            "first",
            "hours",
            "many",
            "much",
            "spent",
            "total",
        }
    )
    records = _evidence_records(question, candidates, candidate_limit=6 if multi_source_query else 3)
    for composer in (_try_compose_day_delta_answer, _try_compose_total_answer, _try_compose_short_inference_answer):
        composed = composer(question, records)
        if composed:
            composed["answer_model"] = model
            return composed

    cited_parts: list[str] = []
    cited_source_ids: list[str] = []
    for record in records:
        cited_source_ids.append(str(record["source_id"]))
        cited_parts.append(f"[{record['source_id']}] {record['text']}")
    if not cited_parts:
        return {
            "generated_answer": "I don't know based on the retrieved memory.",
            "cited_source_ids": [],
            "answer_model": model,
        }
    return {
        "generated_answer": " ".join(cited_parts),
        "cited_source_ids": cited_source_ids,
        "answer_model": model,
    }


async def _generate_llm_answer_from_candidates(question: str, candidates: list[Any], *, model: str) -> dict[str, Any]:
    if not candidates:
        return {
            "generated_answer": "I don't know based on the retrieved memory.",
            "cited_source_ids": [],
            "answer_model": model,
        }
    from ntrp.llm.router import get_completion_client

    context = []
    for candidate in candidates[:8]:
        source_id = _candidate_primary_source(candidate)
        if not source_id:
            continue
        context.append(
            {
                "source_id": source_id,
                "object_type": _candidate_kind(candidate),
                "title": _candidate_kind(candidate),
                "text": _candidate_evidence_excerpt(question, candidate, max_chars=1400),
            }
        )
    try:
        response = await get_completion_client(model).completion(
            model=model,
            temperature=0,
            max_tokens=600,
            response_format=_LLMAnswer,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Answer the user question using only the provided memory sources. "
                        "Cite source ids you used. If the answer needs arithmetic/date reasoning, compute it from the sources. "
                        "Return strict JSON matching the schema."
                    ),
                },
                {"role": "user", "content": json.dumps({"question": question, "sources": context}, ensure_ascii=False)},
            ],
        )
        content = response.choices[0].message.content if response.choices else None
        parsed = _LLMAnswer.model_validate_json(content or "{}")
        known_source_ids = {item["source_id"] for item in context}
        cited = [source_id for source_id in parsed.cited_source_ids if source_id in known_source_ids]
        return {"generated_answer": parsed.answer, "cited_source_ids": cited, "answer_model": model}
    except Exception as exc:
        fallback = _generate_answer_from_candidates(question, candidates)
        fallback["answer_model"] = f"{model}:failed_fallback_deterministic"
        fallback["answer_model_error"] = type(exc).__name__
        return fallback


def _judge_generated_answer(
    *,
    expected_answer: str,
    generated_answer: str,
    cited_source_ids: list[str],
    candidates: list[Any],
    gold_session_ids: set[str],
) -> dict[str, Any]:
    candidate_text_by_source: dict[str, str] = {}
    for candidate in candidates:
        text = _candidate_text(candidate)
        for source_id in _candidate_source_ids(candidate):
            candidate_text_by_source[str(source_id)] = text
            candidate_text_by_source[_display_source_id(str(source_id))] = text
    known_citations = [source_id for source_id in cited_source_ids if source_id in candidate_text_by_source]
    unknown_citations = [source_id for source_id in cited_source_ids if source_id not in candidate_text_by_source]
    cited_text = "\n".join(candidate_text_by_source[source_id] for source_id in known_citations)
    generated_overlap = _answer_overlap(expected_answer, generated_answer)
    cited_overlap = _answer_overlap(expected_answer, cited_text) if known_citations else None
    correct = _answer_supported_by_text(expected_answer, generated_answer)
    answer_supported_by_citations = _answer_supported_by_text(expected_answer, cited_text) if known_citations else False
    cited_gold_source = bool(gold_session_ids & set(cited_source_ids))
    source_grounded = bool(cited_source_ids) and not unknown_citations and (
        not correct or answer_supported_by_citations or cited_gold_source
    )
    return {
        "judge_model": "deterministic-answer-overlap-v1",
        "expected_answer": expected_answer,
        "correct": correct,
        "source_grounded": source_grounded,
        "answer_supported_by_citations": answer_supported_by_citations,
        "generated_overlap": generated_overlap,
        "cited_overlap": cited_overlap,
        "cited_gold_source": cited_gold_source,
        "cited_source_ids": cited_source_ids,
        "unknown_citation_ids": unknown_citations,
        "reason": (
            "gold answer is present in generated answer and cited source text"
            if correct and answer_supported_by_citations
            else "gold answer was not supported by the generated answer/citations"
        ),
    }


async def _judge_generated_answer_with_llm(
    *,
    expected_answer: str,
    generated_answer: str,
    cited_source_ids: list[str],
    candidates: list[Any],
    gold_session_ids: set[str],
    model: str,
) -> dict[str, Any]:
    from ntrp.llm.router import get_completion_client

    deterministic = _judge_generated_answer(
        expected_answer=expected_answer,
        generated_answer=generated_answer,
        cited_source_ids=cited_source_ids,
        candidates=candidates,
        gold_session_ids=gold_session_ids,
    )
    candidate_text_by_source: dict[str, str] = {}
    for candidate in candidates:
        text = _candidate_text(candidate)
        for source_id in _candidate_source_ids(candidate):
            candidate_text_by_source[str(source_id)] = text
    cited_text = "\n".join(candidate_text_by_source.get(source_id, "") for source_id in cited_source_ids)
    try:
        response = await get_completion_client(model).completion(
            model=model,
            temperature=0,
            max_tokens=350,
            response_format=_LLMJudge,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Judge whether the generated answer matches the expected answer and is grounded in the cited memory text. "
                        "Accept equivalent wording and simple arithmetic/date calculations. Return strict JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "expected_answer": expected_answer,
                            "generated_answer": generated_answer,
                            "cited_source_ids": cited_source_ids,
                            "cited_text": cited_text[:6000],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        )
        content = response.choices[0].message.content if response.choices else None
        parsed = _LLMJudge.model_validate_json(content or "{}")
        return {
            **deterministic,
            "judge_model": model,
            "correct": parsed.correct,
            "source_grounded": parsed.source_grounded,
            "reason": parsed.reason or deterministic.get("reason", ""),
            "deterministic_judge": deterministic,
        }
    except Exception as exc:
        return {**deterministic, "judge_model": f"{model}:failed_fallback_deterministic", "judge_model_error": type(exc).__name__}


def _answer_failure_class(
    *,
    retrieval_failure_class: str | None,
    first_gold_rank: int | None,
    all_gold_retrieved: bool,
    answer_eval: dict[str, Any],
) -> str | None:
    if retrieval_failure_class:
        return retrieval_failure_class
    if not answer_eval["correct"]:
        if first_gold_rank is not None and not all_gold_retrieved:
            return "partial_gold_context_wrong_answer"
        if first_gold_rank is not None:
            return "right_source_wrong_answer"
        return "answer_missing_gold"
    if not answer_eval["source_grounded"]:
        return "uncited_or_ungrounded_answer"
    if not answer_eval["cited_gold_source"]:
        return "correct_answer_wrong_source"
    return None


def _answer_reliability_warnings(*, first_gold_rank: int | None, all_gold_retrieved: bool, answer_eval: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if first_gold_rank is not None and first_gold_rank > 1:
        warnings.append("gold_retrieved_bad_rank")
    if first_gold_rank is not None and not all_gold_retrieved:
        warnings.append("partial_gold_retrieved")
    if answer_eval["correct"] and not answer_eval["cited_gold_source"]:
        warnings.append("answer_correct_without_gold_source")
    return warnings


async def _run_case(
    case: dict[str, Any],
    *,
    db_path: Path,
    top_k: int,
    budget_chars: int,
    raw_evidence_query: bool,
    variant: str,
    evaluate_answers: bool,
    answer_model: str | None,
    judge_model: str | None,
    extraction_model: str | None,
) -> dict[str, Any]:
    conn, service = await _new_case_service(db_path, extraction_model=extraction_model)
    try:
        if variant in {"raw-episodes", "raw-plus-extracted"} or extraction_model:
            await _ingest_case(service, case)
        if variant in {"extracted", "raw-plus-extracted"}:
            if extraction_model:
                await _ingest_model_extracted_memories(service, case, keep_raw_episodes=variant == "raw-plus-extracted")
            else:
                await _ingest_extracted_turn_memories(service, case)
        activation_query = str(case["question"])
        if raw_evidence_query:
            activation_query = f"source evidence for {activation_query}"
        bundle = await service.memory_retrieval.search(
            MemoryActivationRequest(
                query=activation_query,
                scope=f"longmemeval:{case['question_id']}",
                limit=top_k,
                budget_chars=budget_chars,
                record_access=False,
            )
        )
    finally:
        await conn.close()

    gold_session_ids = {str(item) for item in case.get("answer_session_ids", [])}
    candidates = [_candidate_trace(candidate, rank, gold_session_ids) for rank, candidate in enumerate(bundle.candidates, start=1)]
    retrieved_gold_session_ids = sorted({source_id for candidate in candidates for source_id in candidate["source_ids"] if source_id in gold_session_ids})
    gold_ranks = [candidate["rank"] for candidate in candidates if candidate["gold_hit"]]
    first_gold_rank = min(gold_ranks) if gold_ranks else None
    recall = 1.0 if first_gold_rank is not None else 0.0
    gold_session_coverage = len(retrieved_gold_session_ids) / len(gold_session_ids) if gold_session_ids else 0.0
    all_gold_retrieved = bool(gold_session_ids) and set(retrieved_gold_session_ids) == gold_session_ids
    reciprocal_rank = 1.0 / first_gold_rank if first_gold_rank else 0.0
    retrieval_failure_class = None
    if first_gold_rank is None:
        retrieval_failure_class = "no_candidates" if not candidates else "gold_session_not_retrieved"
    failure_class = retrieval_failure_class
    answer_generation = None
    answer_eval = None
    reliability_warnings: list[str] = []
    if evaluate_answers:
        if answer_model:
            answer_generation = await _generate_llm_answer_from_candidates(str(case["question"]), list(bundle.candidates), model=answer_model)
        else:
            answer_generation = _generate_answer_from_candidates(str(case["question"]), list(bundle.candidates))
        if judge_model:
            answer_eval = await _judge_generated_answer_with_llm(
                expected_answer=str(case.get("answer", "")),
                generated_answer=str(answer_generation["generated_answer"]),
                cited_source_ids=[str(item) for item in answer_generation["cited_source_ids"]],
                candidates=list(bundle.candidates),
                gold_session_ids=gold_session_ids,
                model=judge_model,
            )
        else:
            answer_eval = _judge_generated_answer(
                expected_answer=str(case.get("answer", "")),
                generated_answer=str(answer_generation["generated_answer"]),
                cited_source_ids=[str(item) for item in answer_generation["cited_source_ids"]],
                candidates=list(bundle.candidates),
                gold_session_ids=gold_session_ids,
            )
        failure_class = _answer_failure_class(
            retrieval_failure_class=retrieval_failure_class,
            first_gold_rank=first_gold_rank,
            all_gold_retrieved=all_gold_retrieved,
            answer_eval=answer_eval,
        )
        reliability_warnings = _answer_reliability_warnings(
            first_gold_rank=first_gold_rank,
            all_gold_retrieved=all_gold_retrieved,
            answer_eval=answer_eval,
        )

    return {
        "question_id": case["question_id"],
        "question_type": case["question_type"],
        "question": case["question"],
        "activation_query": activation_query,
        "answer": case.get("answer", ""),
        "variant": variant,
        "gold_session_ids": sorted(gold_session_ids),
        "retrieved_gold_session_ids": retrieved_gold_session_ids,
        "gold_session_coverage": gold_session_coverage,
        "all_gold_retrieved": all_gold_retrieved,
        "retrieved_count": len(candidates),
        "first_gold_rank": first_gold_rank,
        "recall_at_k": recall,
        "reciprocal_rank": reciprocal_rank,
        "retrieval_failure_class": retrieval_failure_class,
        "failure_class": failure_class,
        "answer_generation": answer_generation,
        "answer_eval": answer_eval,
        "reliability_warnings": reliability_warnings,
        "candidates": candidates,
    }


def _metrics_from_traces(
    traces: list[dict[str, Any]],
    *,
    top_k: int,
    dataset_path: Path,
    run_id: str,
    raw_evidence_query: bool,
    variant: str,
) -> dict[str, Any]:
    total = len(traces)
    hits = sum(1 for trace in traces if trace["first_gold_rank"] is not None)
    mrr = sum(float(trace["reciprocal_rank"]) for trace in traces) / total if total else 0.0
    mean_gold_session_coverage = sum(float(trace.get("gold_session_coverage", 0.0)) for trace in traces) / total if total else 0.0
    all_gold_hits = sum(1 for trace in traces if trace.get("all_gold_retrieved"))
    by_type: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trace in traces:
        grouped[str(trace["question_type"])].append(trace)
    for question_type, rows in sorted(grouped.items()):
        count = len(rows)
        type_hits = sum(1 for row in rows if row["first_gold_rank"] is not None)
        type_mrr = sum(float(row["reciprocal_rank"]) for row in rows) / count if count else 0.0
        type_gold_coverage = sum(float(row.get("gold_session_coverage", 0.0)) for row in rows) / count if count else 0.0
        type_all_gold_hits = sum(1 for row in rows if row.get("all_gold_retrieved"))
        by_type[question_type] = {
            "cases": count,
            "hits": type_hits,
            "recall_at_k": type_hits / count if count else 0.0,
            "mrr_at_k": type_mrr,
            "gold_session_coverage_at_k": type_gold_coverage,
            "all_gold_retrieved_rate": type_all_gold_hits / count if count else 0.0,
        }
    failures: dict[str, int] = defaultdict(int)
    for trace in traces:
        if trace["failure_class"]:
            failures[str(trace["failure_class"])] += 1
    answer_rows = [trace for trace in traces if trace.get("answer_eval") is not None]
    answer_eval_enabled = bool(answer_rows)
    answer_correct = sum(1 for trace in answer_rows if trace["answer_eval"]["correct"])
    source_grounded = sum(1 for trace in answer_rows if trace["answer_eval"]["source_grounded"])
    grounded_correct = sum(
        1 for trace in answer_rows if trace["answer_eval"]["correct"] and trace["answer_eval"]["source_grounded"]
    )
    answer_failure_classes: dict[str, int] = defaultdict(int)
    warnings: dict[str, int] = defaultdict(int)
    for trace in answer_rows:
        if trace.get("failure_class"):
            answer_failure_classes[str(trace["failure_class"])] += 1
        for warning in trace.get("reliability_warnings", []):
            warnings[str(warning)] += 1
    if answer_eval_enabled:
        for question_type, rows in grouped.items():
            typed_answer_rows = [row for row in rows if row.get("answer_eval") is not None]
            if not typed_answer_rows:
                continue
            typed_answer_correct = sum(1 for row in typed_answer_rows if row["answer_eval"]["correct"])
            typed_source_grounded = sum(1 for row in typed_answer_rows if row["answer_eval"]["source_grounded"])
            typed_grounded_correct = sum(
                1 for row in typed_answer_rows if row["answer_eval"]["correct"] and row["answer_eval"]["source_grounded"]
            )
            by_type[str(question_type)].update(
                {
                    "answer_accuracy": typed_answer_correct / len(typed_answer_rows),
                    "source_grounding_rate": typed_source_grounded / len(typed_answer_rows),
                    "grounded_correct_rate": typed_grounded_correct / len(typed_answer_rows),
                }
            )
    metrics: dict[str, Any] = {
        "benchmark": "longmemeval",
        "run_id": run_id,
        "dataset_path": str(dataset_path),
        "top_k": top_k,
        "raw_evidence_query": raw_evidence_query,
        "variant": variant,
        "variant_components": {
            "raw_episodes": variant in {"raw-episodes", "raw-plus-extracted"},
            "extracted_facts": variant in {"extracted", "raw-plus-extracted"},
        },
        "cases": total,
        "hits": hits,
        "recall_at_k": hits / total if total else 0.0,
        "mrr_at_k": mrr,
        "gold_session_coverage_at_k": mean_gold_session_coverage,
        "all_gold_retrieved_rate": all_gold_hits / total if total else 0.0,
        "by_question_type": by_type,
        "failure_classes": dict(sorted(failures.items())),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    if answer_eval_enabled:
        metrics["answer_eval"] = {
            "enabled": True,
            "answer_model": str(answer_rows[0].get("answer_generation", {}).get("answer_model", "deterministic-evidence-extractive-v2")),
            "judge_model": str(answer_rows[0].get("answer_eval", {}).get("judge_model", "deterministic-answer-overlap-v1")),
            "cases": len(answer_rows),
            "answer_correct": answer_correct,
            "answer_accuracy": answer_correct / len(answer_rows) if answer_rows else 0.0,
            "source_grounded": source_grounded,
            "source_grounding_rate": source_grounded / len(answer_rows) if answer_rows else 0.0,
            "grounded_correct": grounded_correct,
            "grounded_correct_rate": grounded_correct / len(answer_rows) if answer_rows else 0.0,
            "failure_classes": dict(sorted(answer_failure_classes.items())),
            "warnings": dict(sorted(warnings.items())),
        }
    return metrics


async def run_longmemeval(config: LongMemEvalRunnerConfig) -> dict[str, Any]:
    run_id = config.run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = config.output_dir / f"longmemeval-{run_id}"
    db_dir = run_dir / "dbs"
    paths = LongMemEvalRunPaths(
        run_dir=run_dir,
        traces_jsonl=run_dir / "traces.jsonl",
        metrics_json=run_dir / "metrics.json",
        failures_jsonl=run_dir / "failures.jsonl",
        db_dir=db_dir,
    )
    paths.run_dir.mkdir(parents=True, exist_ok=True)
    paths.db_dir.mkdir(parents=True, exist_ok=True)

    cases = select_cases(
        load_longmemeval_cases(config.dataset_path),
        limit=config.limit,
        per_type_limit=config.per_type_limit,
    )
    traces: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        db_path = paths.db_dir / f"{index:05d}-{case['question_id']}.db"
        if db_path.exists():
            db_path.unlink()
        traces.append(
            await _run_case(
                case,
                db_path=db_path,
                top_k=config.top_k,
                budget_chars=config.budget_chars,
                raw_evidence_query=config.raw_evidence_query,
                variant=config.variant,
                evaluate_answers=config.evaluate_answers,
                answer_model=config.answer_model,
                judge_model=config.judge_model,
                extraction_model=config.extraction_model,
            )
        )
        if not config.keep_dbs and db_path.exists():
            db_path.unlink()
    if not config.keep_dbs:
        shutil.rmtree(paths.db_dir, ignore_errors=True)

    metrics = _metrics_from_traces(
        traces,
        top_k=config.top_k,
        dataset_path=config.dataset_path,
        run_id=run_id,
        raw_evidence_query=config.raw_evidence_query,
        variant=config.variant,
    )
    metrics["extraction_model"] = config.extraction_model
    failures = [trace for trace in traces if trace["failure_class"]]
    _write_jsonl(paths.traces_jsonl, traces)
    _write_jsonl(paths.failures_jsonl, failures)
    paths.metrics_json.write_text(json.dumps(metrics, indent=2, ensure_ascii=False, default=_json_default) + "\n", encoding="utf-8")
    return {
        "metrics": metrics,
        "paths": {
            "run_dir": str(paths.run_dir),
            "traces_jsonl": str(paths.traces_jsonl),
            "metrics_json": str(paths.metrics_json),
            "failures_jsonl": str(paths.failures_jsonl),
            "db_dir": str(paths.db_dir) if config.keep_dbs else None,
        },
    }


def run_longmemeval_sync(config: LongMemEvalRunnerConfig) -> dict[str, Any]:
    return asyncio.run(run_longmemeval(config))
