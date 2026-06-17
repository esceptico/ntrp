import json
from pathlib import Path

from ntrp.agent_surface.models import AgentSurfaceManifest


def write_manifest(root: Path | str, manifest: AgentSurfaceManifest) -> Path:
    root = Path(root)
    out = root / ".ntrp" / "manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n")
    return out
