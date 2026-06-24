"""Memory router — directory-first memory artifacts plus records/labels for the
/admin/memory desktop contract.

The substrate is records + labels. There is no graph or canonical derivation DAG
in the read/write contract; item detail returns empty edge arrays for one release
for compatibility.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ntrp.memory.artifacts import ArtifactMemoryStore
from ntrp.memory.models import Record
from ntrp.memory.scopes import MemoryScope, scope_for_write
from ntrp.server.deps import require_knowledge_runtime
from ntrp.server.runtime import Runtime, get_runtime
from ntrp.server.runtime.knowledge import KnowledgeRuntime

router = APIRouter(prefix="/admin/memory", tags=["memory"])


def _record_store(knowledge: KnowledgeRuntime = Depends(require_knowledge_runtime)):
    if not knowledge._record_store:
        raise HTTPException(status_code=503, detail="memory not ready")
    return knowledge._record_store


def _artifact_store(knowledge: KnowledgeRuntime = Depends(require_knowledge_runtime)) -> ArtifactMemoryStore:
    return ArtifactMemoryStore(knowledge.config.memory_artifacts_dir)


# --- JSON adapters (record -> item) ------------------------------------------

# The lens.ts color ramp / badges key on these exact strings — emit nothing else.
_PROVENANCE_USER = "user_authored"
_PROVENANCE_RECORDED = "recorded"
_PROVENANCE_EXTERNAL = "external"
_USER_SOURCE_KINDS = {"desktop_pin", "user", "user_authored"}
_INTEGRATION_SOURCE_KINDS = {"file", "web", "email", "gmail", "calendar", "slack", "mcp", "integration"}


def _provenance(r: Record) -> str:
    if r.pinned:
        return _PROVENANCE_USER
    if r.source_ref is not None and r.source_ref.kind in _USER_SOURCE_KINDS:
        return _PROVENANCE_USER
    if r.source_ref is not None and r.source_ref.kind in _INTEGRATION_SOURCE_KINDS:
        return _PROVENANCE_EXTERNAL
    return _PROVENANCE_RECORDED


def record_to_item_json(r: Record, labels: list[str]) -> dict:
    """A Record rendered as the UI's `MemoryItem` record item shape. Records
    have no claims-era fields, so map deterministically: text->content,
    kind->canonical_subject, one flat user/null scope, no edges. `labels` come
    from a labels_for batch hydrate — list endpoints must never fetch them per
    record (N+1)."""
    source_refs = []
    if r.source_ref is not None:
        source_refs.append(
            {
                "kind": r.source_ref.kind,
                "ref": r.source_ref.ref,
                "captured_at": r.source_ref.captured_at,
            }
        )
    status = "superseded" if r.superseded_by else "active"
    return {
        "id": r.id,
        "content": r.text,
        "kind": r.kind,
        "canonical_subject": r.kind,
        "labels": labels,
        "scope": {"kind": r.scope_kind or "global", "key": r.scope_key},
        "provenance": _provenance(r),
        "pinned": r.pinned,
        "status": status,
        "standing": "active",
        "depth": 0,
        "valid_from": r.created_at,
        "invalid_at": None,
        "source_refs": source_refs,
        "corroboration": 1 + len(source_refs),
        "last_relevant_at": r.last_confirmed_at,
        "feedback": "confirmed" if r.pinned else "none",
        "created_at": r.created_at,
        "updated_at": r.last_confirmed_at,
    }


async def hydrated_items_json(store, records: list[Record]) -> list[dict]:
    """Render many records as MemoryItems with ONE labels_for batch query."""
    labels = await store.labels_for([r.id for r in records])
    return [record_to_item_json(r, labels[r.id]) for r in records]


# --- 1: scopes ---------------------------------------------------------------


@router.get("/scopes")
async def list_scopes() -> dict:
    """The UI currently shows one simple memory surface.

    Scopes are still stored and enforced by API/tool read paths; they are not a
    user-facing hierarchy or graph browser. Returning [] keeps the old scope-chip
    row hidden while the lean memory UI settles.
    """
    return {"scopes": []}


# --- 2: artifact memory surface ---------------------------------------------


def artifact_to_json(a) -> dict:
    return {
        "path": a.path,
        "title": a.title,
        "kind": a.kind,
        "type": a.type,
        "directory": a.directory,
        "scope": {"kind": a.scope_kind, "key": a.scope_key},
        "content": a.content,
        "snippet": a.snippet,
        "record_count": a.record_count,
        "generated": a.generated,
        "editable": a.editable,
        "readonly_reason": a.readonly_reason,
        "updated_at": a.updated_at,
        "labels": list(a.labels),
        "source": a.source,
        "timeline": [
            {"id": l.id, "text": l.text, "kind": l.kind, "date": l.date,
             "src": l.src, "pinned": l.pinned, "superseded": l.superseded}
            for l in (getattr(a, "timeline", ()) or ())
        ],
        "frontmatter": _json_safe(getattr(a, "frontmatter", {}) or {}),
    }


def _json_safe(fm: dict) -> dict:
    """Frontmatter values can carry YAML wrapper types (e.g. QuotedStr); coerce to
    plain JSON-friendly scalars/lists so the client renders them as Obsidian properties."""
    def coerce(v):
        if isinstance(v, (list, tuple)):
            return [coerce(x) for x in v]
        if isinstance(v, (str, int, float, bool)) or v is None:
            return v
        return str(v)
    return {str(k): coerce(v) for k, v in fm.items()}


@router.get("/artifacts")
def list_artifacts(
    kind: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    artifacts: ArtifactMemoryStore = Depends(_artifact_store),
) -> dict:
    return {"artifacts": [artifact_to_json(a) for a in artifacts.list_artifacts(kind=kind, q=q)]}


@router.post("/artifacts/rebuild")
async def rebuild_artifacts(
    artifacts: ArtifactMemoryStore = Depends(_artifact_store),
) -> dict:
    # Memory is file-canonical: the markdown pages ARE the source of truth, there
    # is no projection to re-derive. Exporting here would clobber the pages, so
    # this is a no-op that just returns the current pages.
    items = artifacts.list_artifacts()
    return {"artifacts": [artifact_to_json(a) for a in items], "detail": "no-op: memory is file-canonical"}


class InitBody(BaseModel):
    confirm: bool = Field(default=False)
    recency_days: int | None = Field(default=None, ge=1, le=3650)
    max_llm_calls: int = Field(default=400, ge=1, le=100_000)
    wipe: bool = Field(default=False)


@router.post("/init")
async def init_memory(
    body: InitBody,
    runtime: Runtime = Depends(get_runtime),
) -> dict:
    """/init: reset the curator + consolidate watermarks and (re)derive memory from
    ALL chat transcripts AND the connected integrations via the BULK curator gate,
    then consolidate and rebuild the artifact projection. Additive by default
    (keeps existing records, can only enrich); pass wipe=true for a destructive
    reset (wipe-except-pinned first). Requires confirm=true."""
    if not body.confirm:
        raise HTTPException(status_code=400, detail="init requires confirm=true")
    if not runtime.knowledge.memory_ready:
        raise HTTPException(status_code=503, detail="memory not ready")
    from ntrp.memory.init import run_memory_init

    return await run_memory_init(
        runtime.knowledge,
        recency_days=body.recency_days,
        max_llm_calls=body.max_llm_calls,
        integration_clients=runtime.integrations.clients,
        wipe=body.wipe,
    )


@router.post("/prune")
async def prune_records(store=Depends(_record_store)) -> dict:
    """Manually trigger the LINT pass: hard-delete superseded tombstones, drop the
    labels they orphan, and reconcile the vector index. Runs automatically each
    consolidate sweep too; this is the on-demand lever."""
    return await store.prune()


@router.get("/artifacts/{path:path}")
def read_artifact(path: str, artifacts: ArtifactMemoryStore = Depends(_artifact_store)) -> dict:
    try:
        return {"artifact": artifact_to_json(artifacts.read_artifact(path))}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="memory artifact not found") from exc


# --- 3: records (retrieval substrate / compatibility) ------------------------


class RecordBody(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    kind_tag: str = Field(default="fact", pattern="^(directive|fact|source)$")
    scope_kind: str | None = Field(default=None, max_length=64)
    scope_key: str | None = Field(default=None, max_length=500)


class PinBody(BaseModel):
    pinned: bool


@router.post("/record")
async def create_record(
    body: RecordBody,
    store=Depends(_record_store),
    artifacts: ArtifactMemoryStore = Depends(_artifact_store),
) -> dict:
    """Quick-capture write (the desktop pin-to-memory affordance): a single atomic
    record into the flat pool. Pinning is a follow-up call so the record survives
    consolidation decay."""
    explicit = MemoryScope(body.scope_kind, body.scope_key) if body.scope_kind or body.scope_key else None
    scope = scope_for_write(kind=body.kind_tag, explicit_scope=explicit)
    record = await store.add(body.text, kind=body.kind_tag, scope_kind=scope.kind, scope_key=scope.key)
    artifacts.append_event(f"Remembered: {body.text}")  # changelog audit (separate from canonical pages)
    # store.add already persists the page (canonical). Do NOT export_from_records —
    # that would re-derive the old projection over the canonical pages, clobbering them.
    return {"record": record_to_item_json(record, [])}


@router.post("/record/{record_id}/pin")
async def pin_record(
    record_id: str,
    body: PinBody,
    store=Depends(_record_store),
    artifacts: ArtifactMemoryStore = Depends(_artifact_store),
) -> dict:
    if not await store.set_pinned(record_id, body.pinned):
        raise HTTPException(status_code=404, detail="record not found")
    artifacts.append_event(f"{'pinned' if body.pinned else 'unpinned'} memory record")
    return {"ok": True, "pinned": body.pinned}


@router.get("/items")
async def list_items(
    status: str = Query(default="active"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, max_length=200),
    store=Depends(_record_store),
    # scope filters are visibility metadata; subject/valid_at remain accepted for older clients
    scope_kind: str | None = None,
    scope_key: str | None = None,
    kind: str | None = None,
    subject: str | None = None,
    valid_at: str | None = None,
) -> dict:
    include_superseded = status == "superseded"
    scopes = [(scope_kind, scope_key)] if scope_kind is not None else None
    if q:
        records = await store.search(
            q,
            include_superseded=include_superseded,
            limit=limit,
            scopes=scopes,
            kinds=[kind] if kind else None,
        )
    else:
        records = await store.list(
            include_superseded=include_superseded,
            limit=limit,
            offset=offset,
            scopes=scopes,
            kinds=[kind] if kind else None,
        )
    if status == "superseded":
        records = [r for r in records if r.superseded_by]
    return {"items": await hydrated_items_json(store, records), "limit": limit, "offset": offset}


@router.get("/items/{item_id}")
async def get_item(item_id: str, store=Depends(_record_store)) -> dict:
    record = await store.get(item_id)
    if record is None:
        raise HTTPException(status_code=404, detail="claim not found")
    labels = await store.labels_of(item_id)
    return {"item": record_to_item_json(record, labels), "parents": [], "children": []}


# --- 4: search ---------------------------------------------------------------


@router.get("/search")
async def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=50, ge=1, le=200),
    include_inactive: bool = Query(default=False),
    mode: str = Query(default="fts"),
    store=Depends(_record_store),
    scope_kind: str | None = None,
    scope_key: str | None = None,
    kind: str | None = None,
) -> dict:
    scopes = [(scope_kind, scope_key)] if scope_kind is not None else None
    records = await store.search(
        q,
        limit=limit,
        include_superseded=include_inactive,
        scopes=scopes,
        kinds=[kind] if kind else None,
    )
    return {
        "mode": "hybrid" if store._search_index is not None else "fts",
        "items": await hydrated_items_json(store, records),
        "degraded": store._search_index is None,
    }
