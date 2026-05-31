"""Lens pass.

Reads lens instruction files (see ``ntrp.memory.lenses``) and materializes
their effect into the canonical graph: one ``directory`` node per lens, the
``entity`` nodes that belong in it, and the ``member_of`` / ``evidence`` edges
linking them. The lens body has authority over *which* entities belong and how
each profile is shaped — the LLM applies those instructions, the graph stores
the result.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from ntrp.llm.router import get_completion_client
from ntrp.logging import get_logger
from ntrp.memory.connectors._confidence import compute_confidence
from ntrp.memory.items_store import MemoryItem, MemoryItemInsert, MemoryItemsRepository
from ntrp.memory.lenses import Lens, load_lenses

_EXTRACT_PROMPT_PATH = Path(__file__).with_name("prompts") / "lens_extract.txt"
_CANDIDATE_PAGE = 200
_CANDIDATE_CONTENT_CHARS = 600
_logger = get_logger(__name__)


class _ExtractedEntity(BaseModel):
    name: str
    profile: str
    source_ids: list[str] = []


class _ExtractedEntities(BaseModel):
    entities: list[_ExtractedEntity] = []


@dataclass(slots=True)
class LensPassRunResult:
    lenses: int
    directories: int
    entities_written: int
    edges_written: int
    elapsed_ms: int

    def to_dict(self) -> dict[str, int]:
        return {
            "lenses": self.lenses,
            "directories": self.directories,
            "entities_written": self.entities_written,
            "edges_written": self.edges_written,
            "elapsed_ms": self.elapsed_ms,
        }


class LensExtractionClient:
    """Default LLM client: returns the model's JSON text for a prompt."""

    def __init__(self, model: str):
        self.model = model

    async def __call__(self, prompt: str) -> str:
        response = await get_completion_client(self.model).completion(
            model=self.model,
            temperature=0,
            max_tokens=2000,
            response_format=_ExtractedEntities,
            messages=[
                {"role": "system", "content": "Organize personal memory into directories. Return strict JSON."},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content if response.choices else ""


class LensPass:
    def __init__(
        self,
        *,
        repo: MemoryItemsRepository,
        client: Any,
        lenses_dir: Path | None = None,
    ):
        self.repo = repo
        self.client = client
        self.lenses_dir = lenses_dir

    async def run(self, *, scope: str = "user", only: set[str] | None = None) -> LensPassRunResult:
        started = time.monotonic()
        lenses = [lens for lens in load_lenses(self.lenses_dir) if only is None or lens.slug in only]
        directories = 0
        entities_written = 0
        edges_written = 0
        for lens in lenses:
            directory_id = await self.repo.ensure_directory(
                lens.slug,
                lens.directory,
                self._directory_description(lens),
                scope=scope,
            )
            directories += 1
            candidates = await self._candidates(scope)
            if not candidates:
                continue
            extracted = await self._extract(lens, candidates)
            candidate_ids = {item.id for item in candidates}
            for entity in extracted:
                wrote_entity, entity_edges = await self._materialize(
                    entity, directory_id=directory_id, candidate_ids=candidate_ids, scope=scope
                )
                entities_written += wrote_entity
                edges_written += entity_edges
        return LensPassRunResult(
            lenses=len(lenses),
            directories=directories,
            entities_written=entities_written,
            edges_written=edges_written,
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )

    def _directory_description(self, lens: Lens) -> str:
        first = next((line.strip() for line in lens.body.splitlines() if line.strip() and not line.startswith("#")), "")
        return first or lens.directory

    async def _candidates(self, scope: str) -> list[MemoryItem]:
        # No recency cap: write-time entity linking (recall-bounded) is the scaling
        # mechanism now, so the lens pass organizes the full active set rather than the
        # most-recent N. We page only to keep any single query bounded.
        candidates: list[MemoryItem] = []
        offset = 0
        while True:
            page = await self.repo.list_items(
                kinds=["observation", "claim"],
                statuses=["active"],
                scope=scope,
                limit=_CANDIDATE_PAGE,
                offset=offset,
            )
            candidates.extend(page)
            if len(page) < _CANDIDATE_PAGE:
                return candidates
            offset += _CANDIDATE_PAGE

    async def _extract(self, lens: Lens, candidates: list[MemoryItem]) -> list[_ExtractedEntity]:
        bullets = "\n".join(f"- [{item.id}] {item.content[:_CANDIDATE_CONTENT_CHARS]}" for item in candidates)
        prompt = _EXTRACT_PROMPT_PATH.read_text().format(
            directory=lens.directory,
            entity_type=lens.entity_type,
            lens_body=lens.body,
            candidate_bullets=bullets,
        )
        raw = (await self.client(prompt)).strip()
        if not raw:
            return []
        try:
            return _ExtractedEntities.model_validate_json(raw).entities
        except ValidationError:
            try:
                return _ExtractedEntities.model_validate(json.loads(raw)).entities
            except (ValidationError, json.JSONDecodeError):
                _logger.warning("Lens '%s' extraction returned unparseable JSON", lens.slug)
                return []

    async def _materialize(
        self,
        entity: _ExtractedEntity,
        *,
        directory_id: str,
        candidate_ids: set[str],
        scope: str,
    ) -> tuple[int, int]:
        name = entity.name.strip()
        profile = entity.profile.strip()
        if not name or not profile:
            return 0, 0
        source_ids = [sid for sid in entity.source_ids if sid in candidate_ids]
        existing = await self.repo.find_entity_by_title(name, scope=scope)
        if existing:
            entity_id = existing.id
            await self.repo.conn.execute(
                "UPDATE memory_items SET content = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (profile, entity_id),
            )
            wrote_entity = 0
        else:
            source_confidences = await self._source_confidences(source_ids)
            entity_id = await self.repo.insert_item(
                MemoryItemInsert(
                    content=profile,
                    source_refs=[{"item_id": sid} for sid in source_ids],
                    confidence=compute_confidence(
                        provenance="inferred",
                        parent_confidences=source_confidences,
                        contradiction_count=0,
                        age_days=0,
                        last_used_days=0,
                        helped=0,
                        hurt=0,
                        ignored=0,
                    ),
                    title=name,
                    scope=scope,
                    kind="entity",
                    provenance="inferred",
                ),
                commit=False,
            )
            wrote_entity = 1
        edges = await self._link(entity_id, directory_id, source_ids)
        await self.repo.conn.commit()
        return wrote_entity, edges

    async def _source_confidences(self, source_ids: list[str]) -> list[float]:
        confidences: list[float] = []
        for sid in source_ids:
            source = await self.repo.get_item(sid)
            if source is not None:
                confidences.append(source.confidence)
        return confidences

    async def _link(self, entity_id: str, directory_id: str, source_ids: list[str]) -> int:
        edges = 0
        edges += await self._safe_edge(entity_id, directory_id, "member_of")
        for sid in source_ids:
            edges += await self._safe_edge(entity_id, sid, "evidence")
        return edges

    async def _safe_edge(self, child_id: str, parent_id: str, role: str) -> int:
        if child_id == parent_id:
            return 0
        try:
            await self.repo.insert_parent_edge(child_id, parent_id, role, commit=False)
        except ValueError:
            return 0
        return 1
