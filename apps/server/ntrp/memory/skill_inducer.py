from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ntrp.constants import NTRP_TMP_BASE
from ntrp.logging import get_logger
from ntrp.memory.connectors._confidence import compute_confidence
from ntrp.memory.items_store import MemoryItem, MemoryItemInsert, MemoryItemsRepository, _row_to_item

DEFAULT_MIN_SUPPORTING_ITEMS = 3
_TOOLABLE_PROMPT_PATH = Path(__file__).with_name("prompts") / "is_toolable.txt"
_SKILL_DRAFT_PROMPT_PATH = Path(__file__).with_name("prompts") / "skill_draft.txt"
_logger = get_logger(__name__)


class ProposalNotFound(ValueError):
    pass


class ProposalStateError(ValueError):
    pass


class ProposalDraftGone(ValueError):
    pass


class SkillSlugCollision(ValueError):
    pass


@dataclass(slots=True)
class ToolableEvaluation:
    is_toolable: bool
    reason: str


@dataclass(slots=True)
class ProposalDraft:
    skill_slug: str
    trigger: str
    skill_body: str
    source_claim_ids: list[str]
    draft_path: Path


@dataclass(slots=True)
class InducerRunResult:
    claims_considered: int
    toolable_claims: int
    clusters_found: int
    proposals_written: int
    elapsed_ms: int

    def to_dict(self) -> dict[str, int]:
        return {
            "claims_considered": self.claims_considered,
            "toolable_claims": self.toolable_claims,
            "clusters_found": self.clusters_found,
            "proposals_written": self.proposals_written,
            "elapsed_ms": self.elapsed_ms,
        }


SkillInducerRunResult = InducerRunResult


class IsToolableGate:
    def __init__(
        self,
        *,
        repo: MemoryItemsRepository,
        judge_client: Any | None = None,
        min_episodes: int = DEFAULT_MIN_SUPPORTING_ITEMS,
    ):
        self.repo = repo
        self.judge_client = judge_client
        self.min_episodes = min_episodes

    async def evaluate(self, claim: MemoryItem | str) -> ToolableEvaluation:
        item = await self._get_item_or_raise(claim) if isinstance(claim, str) else claim
        if item.kind != "claim":
            return ToolableEvaluation(False, f"kind {item.kind!r} is not claim")

        checks: list[tuple[bool, str]] = []
        repetition = await self._check_repetition(item)
        checks.append(repetition)
        if not repetition[0]:
            return ToolableEvaluation(False, _join_reasons(checks))

        checks.append(await self._check_determinism(item))
        trigger = await self._check_trigger(item)
        checks.append(trigger)
        if not trigger[0]:
            return ToolableEvaluation(False, _join_reasons(checks))
        checks.append(await self._check_success_signal(item))
        return ToolableEvaluation(all(ok for ok, _ in checks), _join_reasons(checks))

    async def evaluate_and_tag(self, claim_id: str) -> ToolableEvaluation:
        evaluation = await self.evaluate(claim_id)
        verdict_tag = "toolable:true" if evaluation.is_toolable else "toolable:false"
        await self._replace_toolable_tag(claim_id, verdict_tag)
        _logger.info(
            "is_toolable verdict claim=%s passed=%s reason=%s",
            claim_id,
            evaluation.is_toolable,
            evaluation.reason,
        )
        return evaluation

    async def _check_repetition(self, claim: MemoryItem) -> tuple[bool, str]:
        edges = await self.repo.list_parent_edges(claim.id)
        evidence_count = sum(1 for edge in edges if edge.role == "evidence")
        if evidence_count < self.min_episodes:
            return False, f"only {evidence_count} supporting items (need >= {self.min_episodes})"
        return True, f"{evidence_count} supporting items"

    async def _check_determinism(self, claim: MemoryItem) -> tuple[bool, str]:
        return True, "determinism skipped - see slice 7 v1 limitation"

    async def _check_trigger(self, claim: MemoryItem) -> tuple[bool, str]:
        trigger = await self._extract_trigger_with_llm(claim)
        if trigger is None:
            return False, "no identifiable trigger"
        await self._add_tag_if_missing(claim.id, f"trigger:{_slugify(trigger)}")
        return True, f"trigger: {trigger!r}"

    async def _check_success_signal(self, claim: MemoryItem) -> tuple[bool, str]:
        return True, "success signal skipped - see slice 7 v1 limitation"

    async def _extract_trigger_with_llm(self, claim: MemoryItem) -> str | None:
        if self.judge_client is None:
            return None
        evidence = await self._supporting_items(claim, limit=5)
        bullets = "\n".join(f"- {item.content}" for item in evidence) or "- (none)"
        prompt = _TOOLABLE_PROMPT_PATH.read_text().format(claim_content=claim.content, evidence_bullets=bullets)
        response = (await self.judge_client(prompt)).strip()
        first_line = response.splitlines()[0].strip(" -\t\"'") if response else ""
        if not first_line or first_line.lower() == "unclear":
            return None
        return first_line

    async def _supporting_items(self, claim: MemoryItem, *, limit: int) -> list[MemoryItem]:
        edges = await self.repo.list_parent_edges(claim.id)
        items: list[MemoryItem] = []
        for edge in edges:
            if edge.role == "evidence":
                items.append(await self._get_item_or_raise(edge.parent_id))
        return sorted(items, key=lambda item: (_as_utc(item.created_at), item.id))[:limit]

    async def _replace_toolable_tag(self, item_id: str, verdict_tag: str) -> None:
        item = await self._get_item_or_raise(item_id)
        tags = [tag for tag in item.tags if tag not in {"toolable:true", "toolable:false"}]
        tags.append(verdict_tag)
        await self._set_tags(item_id, tags)

    async def _add_tag_if_missing(self, item_id: str, tag: str) -> None:
        item = await self._get_item_or_raise(item_id)
        if tag in item.tags:
            return
        await self._set_tags(item_id, [*item.tags, tag])

    async def _set_tags(self, item_id: str, tags: list[str]) -> None:
        await self.repo.conn.execute(
            "UPDATE memory_items SET tags = ?, updated_at = ? WHERE id = ?",
            (json.dumps(_dedupe(tags), sort_keys=True), datetime.now(UTC).isoformat(), item_id),
        )
        await self.repo.conn.commit()

    async def _get_item_or_raise(self, item_id: str) -> MemoryItem:
        return await _get_item_or_raise(self.repo, item_id)


class SkillInducer:
    def __init__(
        self,
        *,
        repo: MemoryItemsRepository,
        draft_client: Any,
        embedder: Any | None = None,
        draft_dir: Path | str | None = None,
        skills_dir: Path | str | None = None,
        min_cluster_size: int = 1,
    ):
        self.repo = repo
        self.draft_client = draft_client
        self.embedder = embedder
        self.draft_dir = Path(draft_dir or os.getenv("NTRP_PROPOSED_SKILLS_DIR", f"{NTRP_TMP_BASE}/proposed-skills"))
        self.skills_dir = Path(skills_dir or os.getenv("NTRP_SKILLS_DIR", "~/.ntrp/skills")).expanduser()
        self.min_cluster_size = min_cluster_size

    async def run(
        self,
        *,
        window_days: int = 30,
        scope: str = "user",
        limit: int = 500,
        now: datetime | None = None,
    ) -> SkillInducerRunResult:
        started = time.perf_counter()
        timestamp = _as_utc(now or datetime.now(UTC))
        claims = await self.repo.list_recent_items(kind="claim", window_days=window_days, limit=limit, scope=scope, now=timestamp)
        toolable_claims = [claim for claim in claims if claim.status == "active" and "toolable:true" in claim.tags]

        candidates: list[MemoryItem] = []
        for claim in toolable_claims:
            if await self._has_existing_derivation(claim.id):
                continue
            candidates.append(claim)

        clusters = _cluster_by_trigger(candidates)
        clusters = [cluster for cluster in clusters if len(cluster) >= self.min_cluster_size]

        proposals_written = 0
        for trigger, cluster in clusters:
            draft = await self._draft_proposal(trigger=trigger, claims=cluster)
            await self._persist_proposal(draft, scope=scope, now=timestamp)
            proposals_written += 1

        return SkillInducerRunResult(
            claims_considered=len(claims),
            toolable_claims=len(toolable_claims),
            clusters_found=len(clusters),
            proposals_written=proposals_written,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
        )

    async def list_proposals(
        self,
        *,
        status: str = "open",
        scope: str = "user",
        window_days: int = 365,
    ) -> list[dict[str, Any]]:
        proposals = await self.repo.list_recent_items(kind="proposal", window_days=window_days, limit=500, scope=scope)
        return [
            _proposal_payload(proposal)
            for proposal in proposals
            if _proposal_status(proposal.tags) == status
        ]

    async def approve_proposal(
        self,
        proposal_id: str,
        *,
        slug: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, str]:
        timestamp = _as_utc(now or datetime.now(UTC))
        proposal = await self._get_proposal(proposal_id)
        if _proposal_status(proposal.tags) != "open":
            raise ProposalStateError("proposal is not open")

        proposal_ref = _proposal_ref(proposal)
        skill_slug = _slugify(slug or str(proposal_ref.get("skill_slug", "")) or _slug_from_tags(proposal.tags))
        draft_path = Path(str(proposal_ref.get("draft_path", ""))).expanduser()
        if not draft_path.exists():
            raise ProposalDraftGone("draft file missing")
        target_dir = self.skills_dir / skill_slug
        if target_dir.exists():
            raise SkillSlugCollision(f"skill slug exists: {skill_slug}")

        skill_body = draft_path.read_text()
        source_claim_ids = _source_claim_ids(proposal)
        source_claims = [await _get_item_or_raise(self.repo, claim_id) for claim_id in source_claim_ids]
        trigger_tags = [tag for tag in proposal.tags if tag.startswith("trigger:")]
        confidence = compute_confidence(
            provenance="user_authored",
            parent_confidences=[claim.confidence for claim in source_claims],
            contradiction_count=0,
            age_days=0,
            last_used_days=0,
            helped=0,
            hurt=0,
            ignored=0,
        )
        embedding = await self.embedder.embed_one(skill_body) if self.embedder is not None else None
        skill_path = target_dir / "SKILL.md"
        moved_to_final = False
        await self.repo.conn.execute("BEGIN")
        try:
            target_dir.mkdir(parents=True)
            draft_path.rename(skill_path)
            moved_to_final = True
            skill_id = await self.repo.insert_item(
                MemoryItemInsert(
                    kind="skill",
                    content=skill_body,
                    provenance="user_authored",
                    source_refs=[{"type": "skill_path", "path": str(skill_path)}],
                    confidence=confidence,
                    status="active",
                    scope=proposal.scope,
                    tags=["skill", f"slug:{skill_slug}", *trigger_tags],
                    embedding=embedding,
                    valid_from=timestamp,
                ),
                commit=False,
            )
            for claim_id in source_claim_ids:
                await self.repo.insert_parent_edge(skill_id, claim_id, "evidence", commit=False)
            await self._update_proposal_tags(
                proposal.id,
                _transition_proposal_tags(proposal.tags, "approved", timestamp, reason=None),
            )
            await self.repo.update_status(proposal.id, "superseded", invalid_at=timestamp, commit=False)
            await self.repo.conn.commit()
        except BaseException:
            await self.repo.conn.rollback()
            if moved_to_final and skill_path.exists():
                draft_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    skill_path.rename(draft_path)
                except OSError:
                    _logger.warning("skill_approval_rollback_failed", draft_path=str(draft_path), skill_path=str(skill_path))
            try:
                target_dir.rmdir()
            except OSError:
                pass
            raise
        return {"skill_id": skill_id, "skill_path": str(skill_path)}

    async def reject_proposal(
        self,
        proposal_id: str,
        *,
        reason: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, str]:
        timestamp = _as_utc(now or datetime.now(UTC))
        proposal = await self._get_proposal(proposal_id)
        if _proposal_status(proposal.tags) != "open":
            raise ProposalStateError("proposal is not open")

        proposal_ref = _proposal_ref(proposal)
        draft_path = Path(str(proposal_ref.get("draft_path", ""))).expanduser()
        try:
            draft_path.unlink()
        except FileNotFoundError:
            pass
        await self._update_proposal_tags(
            proposal.id,
            _transition_proposal_tags(proposal.tags, "rejected", timestamp, reason=reason),
        )
        await self.repo.update_status(proposal.id, "archived", invalid_at=timestamp, commit=False)
        await self.repo.conn.commit()
        return {"rejected_at": timestamp.isoformat()}

    async def _draft_proposal(self, *, trigger: str, claims: list[MemoryItem]) -> ProposalDraft:
        supporting = await self._supporting_items_for_claims(claims)
        prompt = _SKILL_DRAFT_PROMPT_PATH.read_text().format(
            trigger=trigger,
            claim_bullets="\n".join(f"- {claim.content}" for claim in claims),
            episode_bullets="\n".join(f"- {item.content}" for item in supporting) or "- (none)",
        )
        body = (await self.draft_client(prompt)).strip()
        title = _skill_title(body) or _title_from_slug(trigger)
        body = _normalize_skill_body(body, title)
        slug = _slugify(title)
        return ProposalDraft(
            skill_slug=slug,
            trigger=trigger,
            skill_body=body,
            source_claim_ids=[claim.id for claim in claims],
            draft_path=self.draft_dir / slug / "SKILL.md",
        )

    async def _persist_proposal(self, draft: ProposalDraft, *, scope: str, now: datetime) -> str:
        draft.draft_path.parent.mkdir(parents=True, exist_ok=True)
        draft.draft_path.write_text(draft.skill_body)
        source_refs = [
            {"type": "proposal", "skill_slug": draft.skill_slug, "draft_path": str(draft.draft_path)},
            *[{"type": "source_claim", "id": claim_id} for claim_id in draft.source_claim_ids],
        ]
        await self.repo.conn.execute("BEGIN")
        try:
            proposal_id = await self.repo.insert_item(
                MemoryItemInsert(
                    kind="proposal",
                    content=draft.skill_body,
                    provenance="inferred",
                    source_refs=source_refs,
                    confidence=0.5,
                    status="active",
                    scope=scope,
                    tags=[
                        "proposal",
                        "skill-draft",
                        "proposal-status:open",
                        f"slug:{draft.skill_slug}",
                        f"trigger:{_slugify(draft.trigger)}",
                    ],
                    valid_from=now,
                ),
                commit=False,
            )
            for claim_id in draft.source_claim_ids:
                await self.repo.insert_parent_edge(proposal_id, claim_id, "evidence", commit=False)
            await self.repo.conn.commit()
            return proposal_id
        except BaseException:
            await self.repo.conn.rollback()
            if draft.draft_path.exists():
                try:
                    draft.draft_path.unlink()
                except OSError:
                    _logger.warning("skill_proposal_draft_cleanup_failed", draft_path=str(draft.draft_path))
            try:
                draft.draft_path.parent.rmdir()
            except OSError:
                pass
            raise

    async def _supporting_items_for_claims(self, claims: list[MemoryItem]) -> list[MemoryItem]:
        seen: set[str] = set()
        items: list[MemoryItem] = []
        for claim in claims:
            for edge in await self.repo.list_parent_edges(claim.id):
                if edge.role != "evidence" or edge.parent_id in seen:
                    continue
                seen.add(edge.parent_id)
                items.append(await _get_item_or_raise(self.repo, edge.parent_id))
        return items

    async def _has_existing_derivation(self, claim_id: str) -> bool:
        rows = await self.repo.conn.execute_fetchall(
            """
            SELECT 1
            FROM memory_item_parents p
            JOIN memory_items m ON m.id = p.child_id
            WHERE p.parent_id = ?
              AND p.role = 'evidence'
              AND m.kind IN ('proposal', 'skill')
            LIMIT 1
            """,
            (claim_id,),
        )
        return bool(rows)

    async def _get_proposal(self, proposal_id: str) -> MemoryItem:
        item = await _get_item_or_raise(self.repo, proposal_id)
        if item.kind != "proposal":
            raise ProposalNotFound(f"proposal not found: {proposal_id}")
        return item

    async def _update_proposal_tags(self, proposal_id: str, tags: list[str]) -> None:
        await self.repo.conn.execute(
            "UPDATE memory_items SET tags = ?, updated_at = ? WHERE id = ?",
            (json.dumps(_dedupe(tags), sort_keys=True), datetime.now(UTC).isoformat(), proposal_id),
        )


async def _get_item_or_raise(repo: MemoryItemsRepository, item_id: str) -> MemoryItem:
    rows = await repo.conn.execute_fetchall(
        """
        SELECT m.*, v.embedding
        FROM memory_items m
        LEFT JOIN memory_items_vec v ON v.item_id = m.id
        WHERE m.id = ?
        """,
        (item_id,),
    )
    if not rows:
        raise ProposalNotFound(f"item not found: {item_id}")
    return _row_to_item(rows[0])


def _cluster_by_trigger(claims: list[MemoryItem]) -> list[tuple[str, list[MemoryItem]]]:
    clusters: dict[str, list[MemoryItem]] = {}
    for claim in claims:
        trigger_tags = sorted(tag for tag in claim.tags if tag.startswith("trigger:"))
        if not trigger_tags:
            continue
        clusters.setdefault(trigger_tags[0].removeprefix("trigger:"), []).append(claim)
    return sorted(clusters.items(), key=lambda item: item[0])


def _proposal_payload(proposal: MemoryItem) -> dict[str, Any]:
    return {
        "id": proposal.id,
        "content": proposal.content,
        "status": _proposal_status(proposal.tags),
        "slug": _slug_from_tags(proposal.tags),
        "draft_path": str(_proposal_ref(proposal).get("draft_path", "")),
        "source_claim_count": len(_source_claim_ids(proposal)),
        "scope": proposal.scope,
    }


def _proposal_ref(proposal: MemoryItem) -> dict[str, Any]:
    for ref in proposal.source_refs:
        if ref.get("type") == "proposal":
            return ref
    raise ProposalDraftGone("proposal source ref missing")


def _source_claim_ids(proposal: MemoryItem) -> list[str]:
    return [str(ref["id"]) for ref in proposal.source_refs if ref.get("type") == "source_claim" and ref.get("id")]


def _proposal_status(tags: list[str]) -> str:
    for tag in tags:
        if tag.startswith("proposal-status:"):
            return tag.removeprefix("proposal-status:")
    return "open"


def _slug_from_tags(tags: list[str]) -> str:
    for tag in tags:
        if tag.startswith("slug:"):
            return tag.removeprefix("slug:")
    return ""


def _transition_proposal_tags(tags: list[str], status: str, timestamp: datetime, *, reason: str | None) -> list[str]:
    next_tags = [tag for tag in tags if not tag.startswith("proposal-status:")]
    next_tags.append(f"proposal-status:{status}")
    if status == "approved":
        next_tags.append(f"approved-at:{timestamp.isoformat()}")
    if status == "rejected" and reason:
        next_tags.append(f"rejection-reason:{_slugify(reason)}")
    return next_tags


def _skill_title(body: str) -> str | None:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.removeprefix("# ").strip()
        if stripped:
            return None
    return None


def _normalize_skill_body(body: str, title: str) -> str:
    stripped = body.strip()
    if stripped.startswith("# "):
        return stripped + "\n"
    return f"# {title}\n\n{stripped}\n"


def _title_from_slug(slug: str) -> str:
    words = []
    for part in slug.split("-"):
        words.append(part.upper() if part in {"api", "cli", "db", "llm", "mcp", "pr", "ui"} else part.capitalize())
    return " ".join(words) or "Proposed Skill"


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized.lower()).strip("-")
    return slug[:40].strip("-") or "skill"


def _dedupe(tags: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for tag in tags:
        if tag in seen:
            continue
        seen.add(tag)
        result.append(tag)
    return result


def _join_reasons(checks: list[tuple[bool, str]]) -> str:
    return "; ".join(message for _, message in checks)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
