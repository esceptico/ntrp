from pathlib import Path
from re import sub

from ntrp.knowledge.models import KnowledgeObject
from ntrp.settings import NTRP_DIR


def _sink_root() -> Path:
    root = (NTRP_DIR / "knowledge-sinks").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _slug(value: str) -> str:
    slug = sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-._")
    return slug[:120] or "artifact"


def _resolve_sink_path(sink: str, sink_ref: str | None, artifact: KnowledgeObject) -> Path:
    root = _sink_root()
    folder = root / _slug(sink)
    folder.mkdir(parents=True, exist_ok=True)
    if sink_ref:
        ref = Path(sink_ref)
        filename = ref.name if ref.name else _slug(artifact.title)
    else:
        filename = f"{artifact.id}-{_slug(artifact.title)}.md"
    if not filename.endswith(".md"):
        filename = f"{filename}.md"
    target = (folder / filename).resolve()
    if not target.is_relative_to(root):
        raise ValueError("sink path must stay inside the knowledge sink directory")
    return target


async def publish_artifact(artifact: KnowledgeObject, *, sink: str, sink_ref: str | None) -> dict[str, object]:
    target = _resolve_sink_path(sink, sink_ref, artifact)
    target.write_text(artifact.text, encoding="utf-8")
    return {
        "sink": sink,
        "sink_ref": sink_ref,
        "path": str(target),
        "bytes": target.stat().st_size,
    }
