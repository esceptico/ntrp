"""Memory router — the `/admin/memory` contract the desktop memory UI calls,
served entirely from the live flat RecordStore + LensStore.

The bridge: the UI is "claims-centric" (MemoryItem, Lens, ProjectedPage,
CoverageAdvisory) but the substrate is records + LABELS + on-demand lenses. A
RECORD *is* a claim — `record.text` is the claim content; LABELS are the
curator's open-vocabulary names on each record (hydrated in batch onto every
item); a lens's MEMBERS are the records its criterion judges in; a lens PAGE is
the synthesized markdown over those members. There are NO scopes (one flat
pool) — `/scopes` returns []. The GRAPH is the derivation DAG: inferred records
linked to their premises by `role="evidence"` edges, plus supersession lineage.

NO LLM CALL EVER RUNS ON A READ PATH. Lens pages are synthesized in the
BACKGROUND (LensStore.kick) and served from cache; while an evaluation is in
flight `getLensPage` returns the LensGenStatus shape and the UI polls
`/page/status` until the page lands.

Wiring: `require_knowledge_runtime` -> `KnowledgeRuntime._record_store` /
`._lens_store`. 503 when memory is off.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ntrp.constants import GENERIC_RATIO
from ntrp.memory.models import Record
from ntrp.server.deps import require_knowledge_runtime
from ntrp.server.runtime.knowledge import KnowledgeRuntime

router = APIRouter(prefix="/admin/memory", tags=["memory"])

# Node budgets that keep both graph payloads bounded.
GRAPH_NODE_CAP = 250
ITEM_GRAPH_NODE_CAP = 60


def _record_store(knowledge: KnowledgeRuntime = Depends(require_knowledge_runtime)):
    if not knowledge._record_store:
        raise HTTPException(status_code=503, detail="memory not ready")
    return knowledge._record_store


def _lens_store(knowledge: KnowledgeRuntime = Depends(require_knowledge_runtime)):
    if not knowledge._lens_store:
        raise HTTPException(status_code=503, detail="memory not ready")
    return knowledge._lens_store


# --- JSON adapters (record <-> claim, lens, page) ----------------------------

# The lens.ts color ramp / badges key on these exact strings — emit nothing else.
_PROVENANCE_USER = "user_authored"
_PROVENANCE_RECORDED = "recorded"
_USER_SOURCE_KINDS = {"desktop_pin", "user", "user_authored"}


def _provenance(r: Record) -> str:
    if r.pinned:
        return _PROVENANCE_USER  # the user's pin converts inference to knowledge
    if r.provenance == "derived":
        return "inferred"
    if r.source_ref is not None and r.source_ref.kind in _USER_SOURCE_KINDS:
        return _PROVENANCE_USER
    return _PROVENANCE_RECORDED


def record_to_item_json(r: Record, labels: list[str]) -> dict:
    """A Record rendered as the UI's `MemoryItem` (claims-only shape). Records
    have no claims-era fields, so map deterministically: text->content,
    kind->canonical_subject (keeps grouped bucketing meaningful), one flat
    user/null scope, no edges. `labels` come from a labels_for batch hydrate —
    list endpoints must never fetch them per record (N+1)."""
    source_refs = []
    if r.source_ref is not None:
        source_refs.append(
            {
                "kind": r.source_ref.kind,
                "ref": r.source_ref.ref,
                "captured_at": r.source_ref.captured_at,
            }
        )
    if r.superseded_by:
        status = "superseded"
    elif r.standing != "active":
        status = r.standing  # unresolved | retired (derivation lifecycle)
    else:
        status = "active"
    return {
        "id": r.id,
        "content": r.text,
        "canonical_subject": r.kind,
        "labels": labels,
        "scope": {"kind": "user", "key": None},
        "provenance": _provenance(r),
        "status": status,
        "standing": r.standing,
        "depth": r.depth,
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


def rendered_claim_json(r: Record) -> dict:
    """A member Record rendered as the UI's `RenderedClaim` (a lens-page block)."""
    source_refs = []
    if r.source_ref is not None:
        source_refs.append(
            {
                "kind": r.source_ref.kind,
                "ref": r.source_ref.ref,
                "captured_at": r.source_ref.captured_at,
            }
        )
    return {
        "claim_id": r.id,
        "content": r.text,
        "provenance": _provenance(r),
        "corroboration": 1 + len(source_refs),
        "feedback": "confirmed" if r.pinned else "none",
        "source_refs": source_refs,
    }


def lens_to_json(lens) -> dict:
    """A LensStore `Lens` ({id,name,criterion,created_at}) rendered as the UI's
    `Lens`. The synthesizer emits `## Name` sections, so render_mode is
    grouped_by_subject (the page builder splits on those headings)."""
    return {
        "id": lens.id,
        "name": lens.name,
        "criterion": lens.criterion,
        "entity_type": None,
        "scope": {"kind": "user", "key": None},
        "detail_level": "structured",
        "render_mode": "grouped_by_subject",
        "provenance": "user_authored",
        "status": "active",
        "promoted_to": lens.promoted_to,
        "created_at": lens.created_at,
        "updated_at": lens.created_at,
    }


def coverage_json(lens_id: str, member_count: int, scope_pool: int) -> dict:
    ratio = member_count / scope_pool if scope_pool else 0.0
    generic = scope_pool > 0 and ratio >= GENERIC_RATIO
    return {
        "lens_id": lens_id,
        "scope_pool": scope_pool,
        "member_count": member_count,
        "ratio": ratio,
        "generic": generic,
        "suggestion": "split" if generic else "",
    }


def _split_subject_sections(markdown: str, members: list[Record]) -> list[dict] | None:
    """Split the synthesized page on `## {subject}` headings into UI
    `ProjectedGroup`s. The synthesizer emits NO per-claim anchors, so blocks can't
    be mapped to a precise section — every group carries ALL member blocks (the
    drill-down is the whole evidence pool). Returns None when the page has no `##`
    sections (the UI then renders the flat markdown + blocks)."""
    if not markdown:
        return None
    lines = markdown.split("\n")
    sections: list[dict] = []
    cur: dict | None = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            if cur is not None:
                sections.append(cur)
            cur = {"subject": stripped[3:].strip(), "body": []}
        elif cur is not None:
            cur["body"].append(line)
    if cur is not None:
        sections.append(cur)
    if not sections:
        return None
    blocks = [rendered_claim_json(r) for r in members]
    return [
        {
            "subject": s["subject"],
            "markdown": "\n".join(s["body"]).strip(),
            "synthesized": True,
            "blocks": blocks,
        }
        for s in sections
    ]


async def _projected_page(store, lens, *, detail: str) -> dict:
    """Build the UI's `ProjectedPage` for a lens from CACHE (markdown + members
    are background-derived; this never triggers LLM work)."""
    markdown = await store.page(lens.name, detail=detail)
    members = await store.members(lens.name, limit=200)
    blocks = [rendered_claim_json(r) for r in members]
    groups = _split_subject_sections(markdown or "", members)
    member_count = await store.member_count(lens.id)
    scope_pool = await store._records.count_active()
    return {
        "lens_id": lens.id,
        "detail": detail,
        "markdown": markdown or "",
        "blocks": blocks,
        "synthesized": markdown is not None,
        "coverage": coverage_json(lens.id, member_count, scope_pool),
        "groups": groups,
    }


# --- request bodies ----------------------------------------------------------


class CreateLensBody(BaseModel):
    name: str | None = None
    criterion: str | None = None
    definition_markdown: str | None = None
    render_mode: str | None = None
    scope_kind: str | None = None
    scope_key: str | None = None


class CriterionBody(BaseModel):
    criterion: str


class DraftLensBody(BaseModel):
    name: str
    scope_kind: str | None = None
    scope_key: str | None = None


class PageEditOp(BaseModel):
    kind: str  # edit | reject | accept | include | edit_criterion
    claim_id: str | None = None
    new_text: str | None = None


class WriteBackBody(BaseModel):
    ops: list[PageEditOp]


def _parse_definition(markdown: str) -> tuple[str, str]:
    """Pull (name, criterion) out of a drafted lens markdown: the first `# Name`
    heading (or first non-empty line) is the name; the criterion is the plain
    PROSE after it — heading lines (`#`, `##`, ...) are template structure,
    never criterion text. The old version kept the raw remainder, so the draft
    template's `## Belongs` fragment was stored verbatim as the criterion."""
    lines = markdown.strip().split("\n")
    name = ""
    rest_start = 0
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        name = s[2:].strip() if s.startswith("# ") else s
        rest_start = i + 1
        break
    name = name or "Untitled lens"
    prose = (line.strip() for line in lines[rest_start:])
    criterion = " ".join(s for s in prose if s and not s.startswith("#"))
    return name, criterion or f"Records about {name}."


# --- 1: scopes (flat pool -> none) -------------------------------------------


@router.get("/scopes")
async def list_scopes() -> dict:
    """Records are ONE flat pool — no scope partition. Returning [] makes the
    UI's scope-chip row vanish (it renders only when scopes.length > 1)."""
    return {"scopes": []}


# --- 2: claims (records) -----------------------------------------------------


class RecordBody(BaseModel):
    text: str
    kind_tag: str = "note"


class PinBody(BaseModel):
    pinned: bool


@router.post("/record")
async def create_record(body: RecordBody, store=Depends(_record_store)) -> dict:
    """Quick-capture write (the desktop pin-to-memory affordance): a single atomic
    record into the flat pool. Pinning is a follow-up call so the record survives
    consolidation decay."""
    record = await store.add(body.text, kind=body.kind_tag)
    return {"record": record_to_item_json(record, [])}


@router.post("/record/{record_id}/pin")
async def pin_record(record_id: str, body: PinBody, store=Depends(_record_store)) -> dict:
    if not await store.set_pinned(record_id, body.pinned):
        raise HTTPException(status_code=404, detail="record not found")
    return {"ok": True, "pinned": body.pinned}


@router.get("/items")
async def list_items(
    status: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=500),
    store=Depends(_record_store),
    # accepted-but-inert (flat pool has no scope/subject/valid_at filter)
    scope_kind: str | None = None,
    scope_key: str | None = None,
    subject: str | None = None,
    valid_at: str | None = None,
) -> dict:
    include_superseded = status == "" or status == "superseded"
    records = await store.list(include_superseded=include_superseded, limit=limit)
    if status == "superseded":
        records = [r for r in records if r.superseded_by]
    return {"items": await hydrated_items_json(store, records), "limit": limit}


def _evidence_edge(derived_id: str, premise_id: str, created_at: str) -> dict:
    """A justification rendered as the UI's MemoryEdge: the derived record is the
    CHILD ("because of"), its premise the PARENT (walkable down to experience)."""
    return {
        "child_id": derived_id,
        "parent_id": premise_id,
        "role": "evidence",
        "position": 0,
        "created_at": created_at,
    }


@router.get("/items/{item_id}")
async def get_item(item_id: str, store=Depends(_record_store)) -> dict:
    """The claim + its epistemic edges: parents = the premises it was derived
    from ("because of…"), children = the inferences it supports ("supports…")."""
    record = await store.get(item_id)
    if record is None:
        raise HTTPException(status_code=404, detail="claim not found")
    labels = await store.labels_of(item_id)
    parents = [
        _evidence_edge(item_id, pid, j.created_at)
        for j in await store.justifications_of(item_id)
        for pid in j.premise_ids
    ]
    children = []
    for dep_id in await store.dependents_of(item_id):
        for j in await store.justifications_of(dep_id):
            if item_id in j.premise_ids:
                children.append(_evidence_edge(dep_id, item_id, j.created_at))
    return {"item": record_to_item_json(record, labels), "parents": parents, "children": children}


# --- 3: lenses (with coverage) -----------------------------------------------


@router.get("/lenses")
async def list_lenses(
    store=Depends(_lens_store),
    scope_kind: str | None = None,
    scope_key: str | None = None,
) -> dict:
    scope_pool = await store._records.count_active()
    out = []
    for lens in await store.list():
        member_count = await store.member_count(lens.id)
        out.append(
            {
                "lens": lens_to_json(lens),
                "coverage": coverage_json(lens.id, member_count, scope_pool),
            }
        )
    return {"lenses": out}


@router.post("/lenses/draft")
async def draft_lens(body: DraftLensBody) -> dict:
    """No LLM draft path on the records substrate — return an editable template
    the UI drops into its textarea. `# {name}` is parsed back as the name on
    create; the body is the criterion."""
    name = body.name.strip()
    markdown = (
        f"# {name}\n\n"
        f"## Belongs\n"
        f"Records about {name}.\n"
    )
    return {"markdown": markdown}


@router.post("/lenses")
async def create_lens(body: CreateLensBody, store=Depends(_lens_store)) -> dict:
    if body.definition_markdown is not None:
        name, criterion = _parse_definition(body.definition_markdown)
    elif body.name is not None:
        name = body.name.strip()
        criterion = (body.criterion or "").strip() or f"Records about {name}."
    else:
        raise HTTPException(status_code=422, detail="name or definition_markdown required")
    if not name:
        raise HTTPException(status_code=422, detail="lens name required")
    if await store.get(name) is not None:
        raise HTTPException(status_code=409, detail=f"lens {name!r} already exists")
    lens = await store.create(name, criterion)  # instant — membership derives on open
    return {"lens": lens_to_json(lens)}


@router.put("/lenses/{lens_id}/criterion")
async def edit_criterion(lens_id: str, body: CriterionBody, store=Depends(_lens_store)) -> dict:
    """A criterion change clears the membership cache only — the next open
    re-evaluates against the new criterion."""
    lens = await store.get_by_id(lens_id)
    if lens is None:
        raise HTTPException(status_code=404, detail="lens not found")
    updated = await store.update(lens.name, criterion=body.criterion)
    if updated is None:
        raise HTTPException(status_code=404, detail="lens not found")
    return {"lens": lens_to_json(updated)}


class PromoteBody(BaseModel):
    label: str


@router.post("/lenses/{lens_id}/promote")
async def promote_lens(lens_id: str, body: PromoteBody, store=Depends(_lens_store)) -> dict:
    """Graduate a durable lens into a LABEL: tag the CACHED members (you promote
    the membership you're looking at — no LLM in the request), mark the lens
    promoted. The curator tags future records since the label is in vocabulary."""
    label = body.label.strip()
    if not label:
        raise HTTPException(status_code=422, detail="label required")
    lens = await store.get_by_id(lens_id)
    if lens is None:
        raise HTTPException(status_code=404, detail="lens not found")
    try:
        count = await store.promote_to_label(lens_id, label)
    except ValueError:
        # Never evaluated — kick it and tell the client to wait for the page.
        store.kick(lens)
        raise HTTPException(status_code=409, detail="lens is still evaluating; open it first") from None
    return {"promoted": count, "label": label}


@router.delete("/lenses/{lens_id}")
async def delete_lens(lens_id: str, store=Depends(_lens_store)) -> dict:
    lens = await store.get_by_id(lens_id)
    if lens is None:
        raise HTTPException(status_code=404, detail="lens not found")
    deleted = await store.delete(lens.name)
    return {"deleted": deleted}


# --- 4: lens page (background synthesis, cache-served) ------------------------


def _gen_status(lens_id: str) -> dict:
    """The UI's LensGenStatus shape — it discriminates on the top-level `status`
    field (a ProjectedPage never has one) and polls until the page lands."""
    return {
        "lens_id": lens_id,
        "status": "generating",
        "subject": None,
        "progress": None,
        "error": None,
    }


@router.get("/lenses/{lens_id}/page")
async def lens_page(
    lens_id: str,
    detail: str = Query(default="structured", pattern="^(gist|structured|dossier)$"),
    refresh: bool = Query(default=False),
    store=Depends(_lens_store),
) -> dict:
    """The `ProjectedPage`, served from CACHE — a lookup never pays an LLM call.
    refresh=true (and an empty never-evaluated cache) KICKS a background
    evaluate+render and returns the generating status; the UI polls."""
    lens = await store.get_by_id(lens_id)
    if lens is None:
        raise HTTPException(status_code=404, detail="lens not found")
    if refresh:
        store.kick(lens)
        return _gen_status(lens_id)
    if store.status(lens_id) == "generating":
        return _gen_status(lens_id)
    page = await _projected_page(store, lens, detail=detail)
    if not page["blocks"] and not page["markdown"]:
        # Never evaluated (a pre-v2 lens, or a kick lost to a restart) — derive
        # it in the background rather than serving a permanently empty view.
        store.kick(lens)
        return _gen_status(lens_id)
    return page


@router.get("/lenses/{lens_id}/page/status")
async def lens_page_status(lens_id: str, store=Depends(_lens_store)) -> dict:
    """Real status: 'generating' while a background evaluate+render is in
    flight for this lens, else 'idle'."""
    return {
        "lens_id": lens_id,
        "status": store.status(lens_id),
        "subject": None,
        "progress": None,
        "error": None,
    }


# --- 5: the derivation DAG ----------------------------------------------------


@router.get("/graph")
async def whole_graph(
    store=Depends(_record_store),
    limit: int = Query(default=GRAPH_NODE_CAP, ge=1, le=1000),
    scope_kind: str | None = None,
    scope_key: str | None = None,
    subject: str | None = None,
    roles: str | None = None,
) -> dict:
    """The memory's epistemic structure — the derivation DAG: inferred records,
    their premises, and supersession lineage. Grows as the dreamer works; labels
    are metadata on the nodes, never edges (spec §6)."""
    included: dict[str, Record] = {}
    for d in await store.derived_records(limit=limit // 2):
        included[d.id] = d
        for just in await store.justifications_of(d.id):
            for pid in just.premise_ids:
                if pid not in included and len(included) < limit:
                    premise = await store.get(pid)
                    if premise is not None:
                        included[pid] = premise

    edges = [
        _evidence_edge(e["derived_id"], e["premise_id"], e["created_at"])
        for e in await store.justification_edges_among(list(included))
    ]
    for r in included.values():
        if r.superseded_by and r.superseded_by in included:
            edges.append({
                "child_id": r.id, "parent_id": r.superseded_by,
                "role": "supersedes", "position": 0, "created_at": r.last_confirmed_at,
            })
    nodes = await hydrated_items_json(store, list(included.values()))
    return {"nodes": nodes, "edges": edges, "scope": {"kind": "user", "key": None}}


@router.get("/items/{item_id}/graph")
async def item_graph(
    item_id: str,
    direction: str = Query(default="both"),
    depth: int = Query(default=3, ge=1, le=8),
    roles: str | None = None,
    store=Depends(_record_store),
) -> dict:
    """One record's epistemic neighborhood: premises and dependents, walked
    through justifications to `depth`."""
    record = await store.get(item_id)
    if record is None:
        raise HTTPException(status_code=404, detail="claim not found")

    included: dict[str, Record] = {item_id: record}
    frontier = {item_id}
    for _ in range(depth):
        nxt: set[str] = set()
        for fid in frontier:
            neighbor_ids = set(await store.dependents_of(fid))
            for just in await store.justifications_of(fid):
                neighbor_ids |= set(just.premise_ids)
            for nid in neighbor_ids:
                if nid not in included and len(included) < ITEM_GRAPH_NODE_CAP:
                    n = await store.get(nid)
                    if n is not None:
                        included[nid] = n
                        nxt.add(nid)
        if not nxt:
            break
        frontier = nxt

    edges = [
        _evidence_edge(e["derived_id"], e["premise_id"], e["created_at"])
        for e in await store.justification_edges_among(list(included))
    ]
    nodes = await hydrated_items_json(store, list(included.values()))
    return {
        "root_id": item_id,
        "nodes": nodes,
        "edges": edges,
        "depth": depth,
        "direction": direction,
    }


# --- 6: search ---------------------------------------------------------------


@router.get("/search")
async def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=50, ge=1, le=200),
    include_inactive: bool = Query(default=False),
    mode: str = Query(default="fts"),
    store=Depends(_record_store),
    scope_kind: str | None = None,
    scope_key: str | None = None,
) -> dict:
    records = await store.search(q, limit=limit, include_superseded=include_inactive)
    return {
        "mode": "fts",
        "items": await hydrated_items_json(store, records),
        "degraded": store._search_index is None,
    }


# --- 7: lens page write-back -------------------------------------------------


@router.post("/lenses/{lens_id}/writeback")
async def writeback(lens_id: str, body: WriteBackBody, knowledge=Depends(require_knowledge_runtime)) -> dict:
    """Apply page edits to the underlying records + lens membership.
      edit         -> supersede the record with new_text; the successor inherits
                      the membership slot (triggers re-derive).
      reject       -> drop the record from this lens (record survives).
      accept       -> confirm the record (refresh freshness).
      include      -> add the record to this lens's membership.
      edit_criterion -> re-cut the lens (re-backfill membership).
    """
    if not knowledge._lens_store or not knowledge._record_store:
        raise HTTPException(status_code=503, detail="memory not ready")
    lenses = knowledge._lens_store
    records = knowledge._record_store
    lens = await lenses.get_by_id(lens_id)
    if lens is None:
        raise HTTPException(status_code=404, detail="lens not found")

    applied: list[dict] = []
    rejected: list[dict] = []
    rederive = False

    for op in body.ops:
        kind = op.kind
        if kind in ("edit", "reject", "accept", "include") and not op.claim_id:
            rejected.append({"op": op.model_dump(), "reason": f"{kind} requires claim_id"})
            continue
        if kind == "edit":
            if not (op.new_text and op.new_text.strip()):
                rejected.append({"op": op.model_dump(), "reason": "edit requires new_text"})
                continue
            old = await records.get(op.claim_id)
            if old is None:
                rejected.append({"op": op.model_dump(), "reason": "claim not found"})
                continue
            successor = await records.supersede_with(
                op.claim_id, text=op.new_text.strip(), kind=old.kind, source_ref=old.source_ref
            )
            await lenses.replace_member(lens.id, op.claim_id, successor.id)
            applied.append({"kind": kind, "id": successor.id})
            rederive = True
        elif kind == "reject":
            removed = await lenses.remove_member(lens.id, op.claim_id)
            if removed:
                applied.append({"kind": kind, "id": op.claim_id})
            else:
                rejected.append({"op": op.model_dump(), "reason": "claim is not a member"})
        elif kind == "accept":
            if await records.confirm(op.claim_id):
                applied.append({"kind": kind, "id": op.claim_id})
            else:
                rejected.append({"op": op.model_dump(), "reason": "claim not found"})
        elif kind == "include":
            if await records.get(op.claim_id) is None:
                rejected.append({"op": op.model_dump(), "reason": "claim not found"})
                continue
            await lenses.add_member(lens.id, op.claim_id)
            applied.append({"kind": kind, "id": op.claim_id})
            rederive = True
        elif kind == "edit_criterion":
            if not (op.new_text and op.new_text.strip()):
                rejected.append({"op": op.model_dump(), "reason": "edit_criterion requires new_text"})
                continue
            await lenses.update(lens.name, criterion=op.new_text.strip())
            applied.append({"kind": kind, "id": lens.id})
            rederive = True
        else:
            rejected.append({"op": op.model_dump(), "reason": f"unknown op kind: {kind}"})

    return {"applied": applied, "rejected": rejected, "rederive_triggered": rederive}
