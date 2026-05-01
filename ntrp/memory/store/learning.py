import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import aiosqlite

from ntrp.memory.models import LearningCandidate, LearningEvent

LEARNING_CANDIDATE_STATUSES = frozenset({"proposed", "approved", "applied", "rejected", "reverted"})

_SQL_INSERT_LEARNING_EVENT = """
    INSERT INTO learning_events (
        created_at, source_type, source_id, scope, signal, evidence_ids, outcome, details
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""

_SQL_LIST_LEARNING_EVENTS = """
    SELECT * FROM learning_events
    {where}
    ORDER BY created_at DESC, id DESC
    LIMIT ? OFFSET ?
"""

_SQL_LIST_UNPROCESSED_LEARNING_EVENTS = """
    SELECT * FROM learning_events
    {where}
    AND NOT EXISTS (
        SELECT 1 FROM learning_event_processing processing
        WHERE processing.scanner = ?
          AND processing.event_id = learning_events.id
    )
    ORDER BY id ASC
    LIMIT ?
"""

_SQL_RECORD_LEARNING_EVENT_PROCESSING = """
    INSERT OR REPLACE INTO learning_event_processing (
        scanner, event_id, candidate_id, decision, processed_at
    )
    VALUES (?, ?, ?, ?, ?)
"""

_SQL_INSERT_LEARNING_CANDIDATE = """
    INSERT INTO learning_candidates (
        created_at, updated_at, status, change_type, target_key, proposal, rationale,
        evidence_event_ids, expected_metric, policy_version, details
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SQL_LIST_LEARNING_CANDIDATES = """
    SELECT * FROM learning_candidates
    {where}
    ORDER BY created_at DESC, id DESC
    LIMIT ? OFFSET ?
"""

_SQL_GET_LEARNING_CANDIDATE = "SELECT * FROM learning_candidates WHERE id = ?"

_SQL_FIND_OPEN_LEARNING_CANDIDATE = """
    SELECT * FROM learning_candidates
    WHERE change_type = ?
      AND target_key = ?
      AND status IN ({statuses})
    ORDER BY updated_at DESC, id DESC
    LIMIT 1
"""

OPEN_LEARNING_CANDIDATE_STATUSES = ("proposed", "approved")


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _json_list(values: list[int] | list[str] | None) -> str:
    return json.dumps(values or [], sort_keys=True)


def _json_details(value: dict[str, Any] | None) -> str:
    return json.dumps(value or {}, default=_json_default, sort_keys=True)


def _row_dict(row: aiosqlite.Row) -> dict:
    return dict(row)


def _validate_status(status: str) -> None:
    if status not in LEARNING_CANDIDATE_STATUSES:
        allowed = ", ".join(sorted(LEARNING_CANDIDATE_STATUSES))
        raise ValueError(f"unsupported learning candidate status: {status}; expected one of {allowed}")


class LearningRepository:
    def __init__(self, conn: aiosqlite.Connection, read_conn: aiosqlite.Connection | None = None):
        self.conn = conn
        self.read_conn = read_conn or conn

    async def create_event(
        self,
        *,
        source_type: str,
        scope: str,
        signal: str,
        source_id: str | None = None,
        evidence_ids: list[str] | None = None,
        outcome: str = "unknown",
        details: dict[str, Any] | None = None,
    ) -> LearningEvent:
        now = datetime.now(UTC)
        cursor = await self.conn.execute(
            _SQL_INSERT_LEARNING_EVENT,
            (
                now.isoformat(),
                source_type,
                source_id,
                scope,
                signal,
                _json_list(evidence_ids),
                outcome,
                _json_details(details),
            ),
        )
        return LearningEvent(
            id=cursor.lastrowid,
            created_at=now,
            source_type=source_type,
            source_id=source_id,
            scope=scope,
            signal=signal,
            evidence_ids=evidence_ids or [],
            outcome=outcome,
            details=details or {},
        )

    async def list_events(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        scope: str | None = None,
        source_type: str | None = None,
    ) -> list[LearningEvent]:
        where = []
        params: list[object] = []
        if scope is not None:
            where.append("scope = ?")
            params.append(scope)
        if source_type is not None:
            where.append("source_type = ?")
            params.append(source_type)

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        rows = await self.read_conn.execute_fetchall(
            _SQL_LIST_LEARNING_EVENTS.format(where=where_sql),
            (*params, limit, offset),
        )
        return [LearningEvent.model_validate(_row_dict(row)) for row in rows]

    async def list_unprocessed_events(
        self,
        *,
        scanner: str,
        limit: int = 100,
        scope: str | None = None,
        source_type: str | None = None,
    ) -> list[LearningEvent]:
        where = []
        params: list[object] = []
        if scope is not None:
            where.append("scope = ?")
            params.append(scope)
        if source_type is not None:
            where.append("source_type = ?")
            params.append(source_type)

        where_sql = f"WHERE {' AND '.join(where)}" if where else "WHERE 1 = 1"
        rows = await self.read_conn.execute_fetchall(
            _SQL_LIST_UNPROCESSED_LEARNING_EVENTS.format(where=where_sql),
            (*params, scanner, limit),
        )
        return [LearningEvent.model_validate(_row_dict(row)) for row in rows]

    async def record_event_processing(
        self,
        *,
        scanner: str,
        event_id: int,
        decision: str,
        candidate_id: int | None = None,
    ) -> None:
        await self.conn.execute(
            _SQL_RECORD_LEARNING_EVENT_PROCESSING,
            (scanner, event_id, candidate_id, decision, datetime.now(UTC).isoformat()),
        )

    async def create_candidate(
        self,
        *,
        change_type: str,
        target_key: str,
        proposal: str,
        rationale: str,
        evidence_event_ids: list[int] | None = None,
        expected_metric: str | None = None,
        policy_version: str,
        status: str = "proposed",
        details: dict[str, Any] | None = None,
    ) -> LearningCandidate:
        _validate_status(status)
        now = datetime.now(UTC)
        cursor = await self.conn.execute(
            _SQL_INSERT_LEARNING_CANDIDATE,
            (
                now.isoformat(),
                now.isoformat(),
                status,
                change_type,
                target_key,
                proposal,
                rationale,
                _json_list(evidence_event_ids),
                expected_metric,
                policy_version,
                _json_details(details),
            ),
        )
        return LearningCandidate(
            id=cursor.lastrowid,
            created_at=now,
            updated_at=now,
            status=status,
            change_type=change_type,
            target_key=target_key,
            proposal=proposal,
            rationale=rationale,
            evidence_event_ids=evidence_event_ids or [],
            expected_metric=expected_metric,
            policy_version=policy_version,
            details=details or {},
        )

    async def list_candidates(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        status: str | None = None,
        change_type: str | None = None,
    ) -> list[LearningCandidate]:
        where = []
        params: list[object] = []
        if status is not None:
            _validate_status(status)
            where.append("status = ?")
            params.append(status)
        if change_type is not None:
            where.append("change_type = ?")
            params.append(change_type)

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        rows = await self.read_conn.execute_fetchall(
            _SQL_LIST_LEARNING_CANDIDATES.format(where=where_sql),
            (*params, limit, offset),
        )
        return [LearningCandidate.model_validate(_row_dict(row)) for row in rows]

    async def find_open_candidate(
        self,
        *,
        change_type: str,
        target_key: str,
        statuses: tuple[str, ...] = OPEN_LEARNING_CANDIDATE_STATUSES,
    ) -> LearningCandidate | None:
        for status in statuses:
            _validate_status(status)
        placeholders = ", ".join("?" for _ in statuses)
        rows = await self.read_conn.execute_fetchall(
            _SQL_FIND_OPEN_LEARNING_CANDIDATE.format(statuses=placeholders),
            (change_type, target_key, *statuses),
        )
        if not rows:
            return None
        return LearningCandidate.model_validate(_row_dict(rows[0]))

    async def update_candidate_status(self, candidate_id: int, status: str) -> LearningCandidate | None:
        _validate_status(status)
        now = datetime.now(UTC)
        updates = ["status = ?", "updated_at = ?"]
        params: list[object] = [status, now.isoformat()]
        if status == "applied":
            updates.append("applied_at = ?")
            params.append(now.isoformat())
        if status == "reverted":
            updates.append("reverted_at = ?")
            params.append(now.isoformat())

        await self.conn.execute(
            f"UPDATE learning_candidates SET {', '.join(updates)} WHERE id = ?",
            (*params, candidate_id),
        )
        rows = await self.conn.execute_fetchall(_SQL_GET_LEARNING_CANDIDATE, (candidate_id,))
        if not rows:
            return None
        return LearningCandidate.model_validate(_row_dict(rows[0]))
