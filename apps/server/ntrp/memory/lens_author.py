"""Lens author.

Turns a natural-language query ("group the people I talk to by company") into a
lens spec, grounded in a sample of the user's actual memory. The generated lens
lands as a reviewable ``proposal`` item; approving it writes the lens file and
runs the pass for that one lens. See ``ntrp.memory.lenses`` for the file format
and ``ntrp.memory.lens_pass`` for execution.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from ntrp.llm.router import get_completion_client
from ntrp.logging import get_logger
from ntrp.memory.activation import MemoryActivationRequest
from ntrp.memory.items_store import MemoryItem, MemoryItemInsert, MemoryItemsRepository
from ntrp.memory.lens_pass import LensPass
from ntrp.memory.lenses import _SLUG_RE, _parse, get_lenses_dir
from ntrp.memory.retrieval import MemoryRetrieval

_AUTHOR_PROMPT_PATH = Path(__file__).with_name("prompts") / "lens_author.txt"
_GROUNDING_LIMIT = 20
_GROUNDING_CONTENT_CHARS = 200
_PROPOSAL_TAG = "lens-proposal"
_STATUS_OPEN = "proposal-status:open"
_STATUS_APPROVED = "proposal-status:approved"
_STATUS_REJECTED = "proposal-status:rejected"
_logger = get_logger(__name__)


class LensSpec(BaseModel):
    slug: str
    directory: str
    entity_type: str
    belongs: str
    profile_shape: list[str] = []


@dataclass(slots=True)
class LensProposal:
    proposal_id: str
    slug: str
    directory: str
    entity_type: str
    markdown: str


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:64]
    slug = slug.lstrip("0123456789-") or "lens"
    return slug if _SLUG_RE.match(slug) else "lens"


def _validate_lens_markdown(markdown: str) -> None:
    parsed = _parse(markdown)
    if parsed is None:
        raise LensAuthorError("lens markdown is missing valid YAML frontmatter")
    frontmatter, _ = parsed
    directory = frontmatter.get("directory")
    entity_type = frontmatter.get("entity_type")
    if not isinstance(directory, str) or not directory.strip():
        raise LensAuthorError("lens frontmatter must include a non-empty 'directory'")
    if not isinstance(entity_type, str) or not entity_type.strip():
        raise LensAuthorError("lens frontmatter must include a non-empty 'entity_type'")


def render_lens_markdown(spec: LensSpec) -> str:
    fields = "\n".join(f"- {field.strip()}" for field in spec.profile_shape if field.strip())
    profile_block = f"\n## Profile shape\n{fields}\n" if fields else ""
    return (
        f"---\ndirectory: {spec.directory}\nentity_type: {spec.entity_type}\n---\n"
        f"## Belongs\n{spec.belongs.strip()}\n{profile_block}"
    )


class LensAuthorClient:
    """Default LLM client: returns the model's LensSpec JSON for a prompt."""

    def __init__(self, model: str):
        self.model = model

    async def __call__(self, prompt: str) -> str:
        response = await get_completion_client(self.model).completion(
            model=self.model,
            temperature=0.2,
            max_tokens=600,
            response_format=LensSpec,
            messages=[
                {"role": "system", "content": "Design memory directory lenses. Return strict JSON."},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content if response.choices else ""


class LensAuthorError(ValueError):
    """Raised when a query cannot be turned into a valid lens spec."""


class LensAuthor:
    def __init__(
        self,
        *,
        repo: MemoryItemsRepository,
        retrieval: MemoryRetrieval,
        lens_pass: LensPass,
        client: Any,
        lenses_dir: Path | None = None,
    ):
        self.repo = repo
        self.retrieval = retrieval
        self.lens_pass = lens_pass
        self.client = client
        self.lenses_dir = lenses_dir or get_lenses_dir()

    async def propose(self, query: str, *, scope: str = "user") -> LensProposal:
        query = query.strip()
        if not query:
            raise LensAuthorError("query is empty")
        grounding = await self._grounding(query, scope)
        spec = await self._author(query, grounding)
        spec.slug = _slugify(spec.slug or spec.directory)
        markdown = render_lens_markdown(spec)
        proposal_id = await self.repo.insert_item(
            MemoryItemInsert(
                content=markdown,
                source_refs=[],
                confidence=0.6,
                title=spec.directory,
                scope=scope,
                kind="proposal",
                provenance="inferred",
                tags=[_PROPOSAL_TAG, _STATUS_OPEN, f"lens:{spec.slug}", f"entity-type:{spec.entity_type}"],
            )
        )
        return LensProposal(
            proposal_id=proposal_id,
            slug=spec.slug,
            directory=spec.directory,
            entity_type=spec.entity_type,
            markdown=markdown,
        )

    async def approve(self, proposal_id: str, *, slug: str | None = None, scope: str = "user") -> dict[str, Any]:
        item = await self._open_proposal(proposal_id)
        final_slug = _slugify(slug) if slug else _tag_value(item.tags, "lens:")
        if not final_slug:
            raise LensAuthorError("proposal has no slug")
        self.lenses_dir.mkdir(parents=True, exist_ok=True)
        (self.lenses_dir / f"{final_slug}.md").write_text(item.content, encoding="utf-8")
        run = await self.lens_pass.run(scope=scope, only={final_slug})
        await self._set_status(item, _STATUS_APPROVED)
        return {"slug": final_slug, "directory": item.title, "run": run.to_dict()}

    async def update_lens(self, slug: str, markdown: str, *, scope: str = "user") -> dict[str, Any]:
        """Overwrite a lens file's contents and re-run the pass for it."""
        final_slug = _slugify(slug)
        path = self.lenses_dir / f"{final_slug}.md"
        if not path.exists():
            raise LensAuthorError("lens not found")
        _validate_lens_markdown(markdown)
        path.write_text(markdown, encoding="utf-8")
        run = await self.lens_pass.run(scope=scope, only={final_slug})
        return {"slug": final_slug, "run": run.to_dict()}

    async def delete_lens(self, slug: str) -> dict[str, Any]:
        """Remove a lens entirely: delete its file and the materialized directory
        plus the entities that exist only because of this lens. Source memory
        (observations/claims/episodes) is left untouched."""
        final_slug = _slugify(slug)
        path = self.lenses_dir / f"{final_slug}.md"
        file_removed = path.exists()
        path.unlink(missing_ok=True)

        directory = await self._find_directory(final_slug)
        entities_removed = 0
        if directory is not None:
            for member in await self.repo.list_directory_members(directory.id):
                if member.kind != "entity":
                    continue
                memberships = [
                    e for e in await self.repo.list_parent_edges(member.id) if e.role == "member_of"
                ]
                if len(memberships) <= 1:
                    await self.repo.delete_item(member.id, commit=False)
                    entities_removed += 1
                else:
                    await self.repo.conn.execute(
                        "DELETE FROM memory_item_parents WHERE child_id = ? AND parent_id = ? AND role = 'member_of'",
                        (member.id, directory.id),
                    )
            await self.repo.delete_item(directory.id, commit=False)
            await self.repo.conn.commit()
        return {
            "slug": final_slug,
            "file_removed": file_removed,
            "directory_removed": directory is not None,
            "entities_removed": entities_removed,
        }

    async def _find_directory(self, slug: str) -> MemoryItem | None:
        rows = await self.repo.conn.execute_fetchall(
            "SELECT id FROM memory_items WHERE kind = 'directory' AND tags LIKE ? LIMIT 1",
            (f'%"lens:{slug}"%',),
        )
        return await self.repo.get_item(rows[0]["id"]) if rows else None

    async def reject(self, proposal_id: str) -> dict[str, Any]:
        item = await self._open_proposal(proposal_id)
        await self._set_status(item, _STATUS_REJECTED, archive=True)
        return {"rejected": True}

    async def list_proposals(self, *, scope: str | None = None) -> list[dict[str, Any]]:
        items = await self.repo.list_items(kinds=["proposal"], statuses=["active"], scope=scope, limit=100)
        out: list[dict[str, Any]] = []
        for item in items:
            if _PROPOSAL_TAG not in item.tags or _STATUS_OPEN not in item.tags:
                continue
            out.append(
                {
                    "proposal_id": item.id,
                    "slug": _tag_value(item.tags, "lens:"),
                    "directory": item.title,
                    "entity_type": _tag_value(item.tags, "entity-type:"),
                    "markdown": item.content,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                }
            )
        return out

    async def _grounding(self, query: str, scope: str) -> str:
        bundle = await self.retrieval.search(
            MemoryActivationRequest(
                query=query,
                scope=scope if scope != "user" else None,
                task="lens_author",
                budget_chars=4000,
                limit=_GROUNDING_LIMIT,
                record_access=False,
            )
        )
        lines = [f"- [{c.kind}] {c.content[:_GROUNDING_CONTENT_CHARS]}" for c in bundle.candidates]
        return "\n".join(lines) if lines else "(no matching memory yet)"

    async def _author(self, query: str, grounding: str) -> LensSpec:
        prompt = _AUTHOR_PROMPT_PATH.read_text().format(query=query, grounding=grounding)
        raw = (await self.client(prompt)).strip()
        if not raw:
            raise LensAuthorError("author returned empty response")
        try:
            return LensSpec.model_validate_json(raw)
        except ValidationError:
            try:
                return LensSpec.model_validate(json.loads(raw))
            except (ValidationError, json.JSONDecodeError) as exc:
                _logger.warning("Lens author returned unparseable spec for query %r", query)
                raise LensAuthorError("author returned an invalid lens spec") from exc

    async def _open_proposal(self, proposal_id: str) -> MemoryItem:
        item = await self.repo.get_item(proposal_id)
        if item is None or item.kind != "proposal" or _PROPOSAL_TAG not in item.tags:
            raise LensAuthorError("lens proposal not found")
        if _STATUS_OPEN not in item.tags:
            raise LensAuthorError("lens proposal is not open")
        return item

    async def _set_status(self, item: MemoryItem, status: str, *, archive: bool = False) -> None:
        tags = [t for t in item.tags if not t.startswith("proposal-status:")] + [status]
        await self.repo.conn.execute(
            "UPDATE memory_items SET tags = ?, status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (json.dumps(tags, sort_keys=True), "archived" if archive else item.status, item.id),
        )
        await self.repo.conn.commit()


def _tag_value(tags: list[str], prefix: str) -> str:
    for tag in tags:
        if tag.startswith(prefix):
            return tag[len(prefix) :]
    return ""
