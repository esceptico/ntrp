from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ntrp.memory.items_store import MemoryItem, MemoryItemsRepository, _row_to_item
from ntrp.memory.learnings import LearningsStore

CROSS_SCOPE_OVERRIDE_TAG = "cross-scope-override"
_PROMPT_PATH = Path(__file__).with_name("prompts") / "contradiction_judge.txt"
_VERDICTS = frozenset({"opposed", "compatible", "unclear"})

_NOT_SAME_GUARD = (
    "\nDo-not-merge guard: two claims that describe DIFFERENT attributes of the same "
    "subject (e.g. a deadline vs. a venue, a tool vs. a schedule) are NOT opposed — they "
    "coexist. Answer 'opposed' only when both claims make the SAME assertion and cannot both "
    "be true at once.\n"
)


@dataclass(slots=True)
class ContradictionCandidate:
    new_claim_id: str
    old_claim_id: str
    judge_verdict: str
    cross_scope: bool


class ContradictionWatcher:
    def __init__(
        self,
        *,
        repo: MemoryItemsRepository,
        embedder: Any,
        judge_client: Any | None = None,
        learnings: LearningsStore | None = None,
    ):
        self.repo = repo
        self.embedder = embedder
        self.judge_client = judge_client
        self.learnings = learnings

    async def scan_window(
        self,
        *,
        scope: str = "user",
        window_days: int = 30,
        limit: int = 500,
    ) -> list[ContradictionCandidate]:
        claims = await self.repo.list_recent_items(kind="claim", window_days=window_days, limit=limit, scope=scope)
        results: list[ContradictionCandidate] = []
        for claim in sorted(claims, key=lambda item: (_as_utc(item.created_at), item.id), reverse=True):
            results.extend(await self.scan_for_new_claim(claim.id, scope=claim.scope))
        return results

    async def scan_for_new_claim(self, claim_id: str, *, scope: str | None = None) -> list[ContradictionCandidate]:
        new_claim = await self._get_item_or_raise(claim_id)
        if new_claim.kind != "claim" or new_claim.status != "active" or not new_claim.tags:
            return []

        candidates = await self._candidate_pool(new_claim)
        persisted: list[ContradictionCandidate] = []
        for old_claim in candidates:
            if await self._has_contradicts_edge(new_claim.id, old_claim.id):
                continue
            verdict = await self._judge(new_claim, old_claim)
            if verdict != "opposed":
                continue
            candidate = ContradictionCandidate(
                new_claim_id=new_claim.id,
                old_claim_id=old_claim.id,
                judge_verdict=verdict,
                cross_scope=new_claim.scope != old_claim.scope,
            )
            await self._persist_contradiction(candidate, now=datetime.now(UTC))
            persisted.append(candidate)
        return persisted

    async def undo(self, *, child_id: str, parent_id: str) -> dict[str, bool]:
        child = await self._get_item_or_none(child_id)
        parent = await self._get_item_or_none(parent_id)
        if child is None or parent is None:
            raise ValueError("contradiction edge not found")

        edge_exists = await self._edge_exists(child_id, parent_id, "contradicts")
        supersedes_exists = await self._edge_exists(child_id, parent_id, "supersedes")
        cross_scope = child.scope != parent.scope
        if not edge_exists:
            if parent.status == "active" and not supersedes_exists:
                return {"already_undone": True, "restored": False, "cross_scope": cross_scope}
            raise ValueError("contradiction edge not found")

        now = datetime.now(UTC).isoformat()
        await self.repo.conn.execute("BEGIN")
        try:
            if cross_scope:
                await self.repo.conn.execute(
                    """
                    DELETE FROM memory_item_parents
                    WHERE child_id = ? AND parent_id = ? AND role = 'contradicts'
                    """,
                    (child_id, parent_id),
                )
                if not await self._has_remaining_cross_scope_edges(child_id, child.scope):
                    await self._remove_tag(child_id, CROSS_SCOPE_OVERRIDE_TAG, now)
                restored = False
            else:
                await self.repo.conn.execute(
                    """
                    DELETE FROM memory_item_parents
                    WHERE child_id = ? AND parent_id = ? AND role IN ('contradicts', 'supersedes')
                    """,
                    (child_id, parent_id),
                )
                if not await self._has_remaining_supersedes_edges(parent_id):
                    await self.repo.conn.execute(
                        """
                        UPDATE memory_items
                        SET status = 'active', invalid_at = NULL, updated_at = ?
                        WHERE id = ?
                        """,
                        (now, parent_id),
                    )
                    restored = True
                else:
                    restored = False
            await self.repo.conn.commit()
        except BaseException:
            await self.repo.conn.rollback()
            raise
        return {"already_undone": False, "restored": restored, "cross_scope": cross_scope}

    async def _candidate_pool(self, new_claim: MemoryItem) -> list[MemoryItem]:
        claims = await self.repo.list_recent_items_all_scopes(kind="claim", window_days=30, limit=500)

        new_tags = set(new_claim.tags)
        return [
            claim
            for claim in claims
            if claim.id != new_claim.id
            and claim.kind == "claim"
            and claim.status == "active"
            and set(claim.tags) & new_tags
            and _is_older(claim, new_claim)
        ]

    async def _judge(self, new_claim: MemoryItem, old_claim: MemoryItem) -> str:
        if self.judge_client is None:
            return "unclear"
        prompt = _PROMPT_PATH.read_text().format(
            claim_a=old_claim.content,
            claim_b=new_claim.content,
            entities=", ".join(sorted(set(new_claim.tags) & set(old_claim.tags))) or "(none)",
            guard=_NOT_SAME_GUARD,
            learnings=self._learnings_block(),
        )
        response = (await self.judge_client(prompt)).strip()
        first_line = response.splitlines()[0].strip().lower() if response else "unclear"
        return first_line if first_line in _VERDICTS else "unclear"

    def _learnings_block(self) -> str:
        if self.learnings is None:
            return ""
        entries = self.learnings.load_block("contradiction")
        if not entries:
            return ""
        return f"\nPast corrections the user made about contradiction judging — honor them:\n{entries}\n"

    async def _persist_contradiction(self, candidate: ContradictionCandidate, *, now: datetime) -> None:
        if candidate.cross_scope:
            await self._persist_cross_scope(candidate, now=now)
        else:
            await self._persist_within_scope(candidate, now=now)

    async def _persist_within_scope(self, candidate: ContradictionCandidate, *, now: datetime) -> None:
        timestamp = now.isoformat()
        await self.repo.conn.execute("BEGIN")
        try:
            await self.repo.insert_parent_edge(
                candidate.new_claim_id,
                candidate.old_claim_id,
                "contradicts",
                commit=False,
            )
            await self.repo.insert_parent_edge(
                candidate.new_claim_id,
                candidate.old_claim_id,
                "supersedes",
                commit=False,
            )
            await self.repo.conn.execute(
                """
                UPDATE memory_items
                SET status = 'superseded', invalid_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (timestamp, timestamp, candidate.old_claim_id),
            )
            await self.repo.conn.commit()
        except BaseException:
            await self.repo.conn.rollback()
            raise

    async def _persist_cross_scope(self, candidate: ContradictionCandidate, *, now: datetime) -> None:
        timestamp = now.isoformat()
        await self.repo.conn.execute("BEGIN")
        try:
            await self.repo.insert_parent_edge(
                candidate.new_claim_id,
                candidate.old_claim_id,
                "contradicts",
                commit=False,
            )
            await self._append_tag(candidate.new_claim_id, CROSS_SCOPE_OVERRIDE_TAG, timestamp)
            await self.repo.conn.commit()
        except BaseException:
            await self.repo.conn.rollback()
            raise

    async def _has_contradicts_edge(self, new_claim_id: str, old_claim_id: str) -> bool:
        return await self._edge_exists(new_claim_id, old_claim_id, "contradicts") or await self._edge_exists(
            old_claim_id,
            new_claim_id,
            "contradicts",
        )

    async def _edge_exists(self, child_id: str, parent_id: str, role: str) -> bool:
        edges = await self.repo.list_parent_edges(child_id)
        return any(edge.parent_id == parent_id and edge.role == role for edge in edges)

    async def _has_remaining_supersedes_edges(self, parent_id: str) -> bool:
        rows = await self.repo.conn.execute_fetchall(
            """
            SELECT 1
            FROM memory_item_parents p
            JOIN memory_items child ON child.id = p.child_id
            WHERE p.parent_id = ?
              AND p.role = 'supersedes'
              AND child.status = 'active'
            LIMIT 1
            """,
            (parent_id,),
        )
        return bool(rows)

    async def _has_remaining_cross_scope_edges(self, child_id: str, child_scope: str) -> bool:
        rows = await self.repo.conn.execute_fetchall(
            """
            SELECT 1
            FROM memory_item_parents p
            JOIN memory_items m ON m.id = p.parent_id
            WHERE p.child_id = ?
              AND p.role = 'contradicts'
              AND m.scope != ?
              AND m.status = 'active'
            LIMIT 1
            """,
            (child_id, child_scope),
        )
        return bool(rows)

    async def _append_tag(self, item_id: str, tag: str, updated_at: str) -> None:
        item = await self._get_item_or_raise(item_id)
        if tag in item.tags:
            return
        tags = [*item.tags, tag]
        await self.repo.conn.execute(
            "UPDATE memory_items SET tags = ?, updated_at = ? WHERE id = ?",
            (json.dumps(tags, sort_keys=True), updated_at, item_id),
        )

    async def _remove_tag(self, item_id: str, tag: str, updated_at: str) -> None:
        item = await self._get_item_or_raise(item_id)
        if tag not in item.tags:
            return
        tags = [value for value in item.tags if value != tag]
        await self.repo.conn.execute(
            "UPDATE memory_items SET tags = ?, updated_at = ? WHERE id = ?",
            (json.dumps(tags, sort_keys=True), updated_at, item_id),
        )

    async def _get_item_or_raise(self, item_id: str) -> MemoryItem:
        item = await self._get_item_or_none(item_id)
        if item is None:
            raise ValueError(f"Item {item_id} not found")
        return item

    async def _get_item_or_none(self, item_id: str) -> MemoryItem | None:
        rows = await self.repo.conn.execute_fetchall(
            """
            SELECT m.*, v.embedding
            FROM memory_items m
            LEFT JOIN memory_items_vec v ON v.item_id = m.id
            WHERE m.id = ?
            """,
            (item_id,),
        )
        return _row_to_item(rows[0]) if rows else None


def _is_older(candidate: MemoryItem, new_claim: MemoryItem) -> bool:
    return (_as_utc(candidate.created_at), candidate.id) < (_as_utc(new_claim.created_at), new_claim.id)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
