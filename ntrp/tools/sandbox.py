import hashlib
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from ntrp.logging import get_logger

_logger = get_logger(__name__)

DEPS_CACHE_DIR = Path.home() / ".cache" / "ntrp" / "tool-deps"

_SCRIPT_META_RE = re.compile(
    r"^# /// script\s*\n((?:#[^\n]*\n)*?)# ///$",
    re.MULTILINE,
)


def parse_inline_deps(source: str) -> list[str] | None:
    match = _SCRIPT_META_RE.search(source)
    if not match:
        return None
    toml_lines = [line.removeprefix("#").removeprefix(" ") for line in match.group(1).splitlines()]
    try:
        meta = tomllib.loads("\n".join(toml_lines))
    except Exception:
        return None
    deps = meta.get("dependencies")
    if not deps or not isinstance(deps, list):
        return None
    return deps


def ensure_deps(deps: list[str]) -> Path | None:
    uv = shutil.which("uv")
    if not uv:
        _logger.warning("uv not found — cannot install tool dependencies")
        return None

    cache_key = hashlib.sha256("\n".join(sorted(deps)).encode()).hexdigest()[:16]
    target = DEPS_CACHE_DIR / cache_key
    marker = target / ".installed"
    if marker.exists():
        return target

    _logger.info("Installing tool dependencies: %s", ", ".join(deps))
    target.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [uv, "pip", "install", "--target", str(target), *deps],
            check=True,
            capture_output=True,
            text=True,
        )
        marker.touch()
    except subprocess.CalledProcessError as e:
        _logger.warning("Failed to install tool deps [%s]: %s", ", ".join(deps), e.stderr.strip())
        return None

    return target


def add_to_path(target: Path) -> None:
    path_str = str(target)
    if path_str not in sys.path:
        sys.path.append(path_str)
