import importlib
import importlib.util
import pkgutil
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from pydantic import BaseModel

from ntrp.logging import get_logger
from ntrp.orchestra.engine import Orchestra
from ntrp.settings import NTRP_DIR

_logger = get_logger(__name__)


@dataclass(frozen=True)
class WorkflowMeta:
    name: str
    description: str
    params: type[BaseModel]


@dataclass(frozen=True)
class Workflow:
    meta: WorkflowMeta
    run: Callable[[Orchestra, BaseModel], Awaitable[Any]]
    location: str
    path: Path | None = None


def get_workflows_dirs() -> list[tuple[Path, str]]:
    return [
        (Path.cwd() / ".workflows", "project"),
        (NTRP_DIR / "workflows", "global"),
    ]


class WorkflowRegistry:
    def __init__(self) -> None:
        self._workflows: dict[str, Workflow] = {}

    def load(self, dirs: list[tuple[Path, str]]) -> None:
        self._workflows.clear()
        self._load_builtin()
        for base, location in dirs:
            self._scan_dir(base, location)

    def get(self, name: str) -> Workflow | None:
        return self._workflows.get(name)

    def list_all(self) -> list[Workflow]:
        return list(self._workflows.values())

    def _load_builtin(self) -> None:
        from ntrp.orchestra import workflows as builtin_pkg

        for info in pkgutil.iter_modules(builtin_pkg.__path__):
            if info.name.startswith("_"):
                continue
            module = importlib.import_module(f"{builtin_pkg.__name__}.{info.name}")
            self._add(module, location="builtin", path=None)

    def _scan_dir(self, base: Path, location: str) -> None:
        if not base.exists():
            return
        for path in sorted(base.glob("*.py")):
            if path.name.startswith("_"):
                continue
            module = self._load_file(path)
            if module is not None:
                self._add(module, location=location, path=path)

    def _load_file(self, path: Path) -> ModuleType | None:
        spec = importlib.util.spec_from_file_location(f"ntrp_workflows.{path.stem}", path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            _logger.warning("Failed to load workflow %s: %s", path, exc)
            return None
        return module

    def _add(self, module: ModuleType, *, location: str, path: Path | None) -> None:
        meta = getattr(module, "META", None)
        run = getattr(module, "run", None)
        if not isinstance(meta, WorkflowMeta) or not callable(run):
            _logger.warning("Workflow module %s missing META/run", getattr(module, "__name__", "?"))
            return
        if meta.name in self._workflows:
            return
        self._workflows[meta.name] = Workflow(meta=meta, run=run, location=location, path=path)


registry = WorkflowRegistry()
