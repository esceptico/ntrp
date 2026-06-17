from importlib.metadata import version
from pathlib import Path

from ntrp.agent_surface.discovery import discover_agent_surface
from ntrp.agent_surface.manifest import write_manifest
from ntrp.agent_surface.models import RuntimeInfo


def build_runtime_info(root: Path | str = ".") -> RuntimeInfo:
    manifest = discover_agent_surface(root)
    write_manifest(root, manifest)
    data = manifest.model_dump(mode="json")
    data["version"] = version("ntrp")
    return RuntimeInfo(**data)
