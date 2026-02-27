import asyncio
import logging
import os
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from ntrp.sources.base import NotesSource, Source
from ntrp.sources.models import RawItem

_logger = logging.getLogger(__name__)


def _walk_markdown_files(root_path: Path) -> Iterator[tuple[Path, str]]:
    for root, dirs, files in os.walk(root_path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for filename in files:
            if filename.endswith(".md"):
                filepath = Path(root) / filename
                relative_path = str(filepath.relative_to(root_path))
                yield filepath, relative_path


class ObsidianSource(Source, NotesSource):
    name = "notes"

    def __init__(self, vault_path: Path):
        self.vault_path = vault_path.resolve()
        if not self.vault_path.exists():
            raise ValueError(f"Vault path does not exist: {self.vault_path}")

    def _safe_path(self, relative_path: str) -> Path:
        resolved = (self.vault_path / relative_path).resolve()
        if not resolved.is_relative_to(self.vault_path):
            raise ValueError(f"Path escapes vault: {relative_path}")
        return resolved

    @property
    def details(self) -> dict:
        return {"path": str(self.vault_path)}

    async def scan(self) -> list[RawItem]:
        return await asyncio.to_thread(self._scan_sync)

    def _scan_sync(self) -> list[RawItem]:
        items = []
        for filepath, relative_path in _walk_markdown_files(self.vault_path):
            if item := self._read_file(filepath, relative_path):
                items.append(item)
        return items

    def _read_file(self, filepath: Path, relative_path: str) -> RawItem | None:
        try:
            content = filepath.read_text(encoding="utf-8")
            stat = filepath.stat()

            title = filepath.stem

            if content.startswith("---"):
                end_idx = content.find("---", 3)
                if end_idx != -1:
                    frontmatter = content[3:end_idx]
                    for line in frontmatter.split("\n"):
                        if line.startswith("title:"):
                            title = line[6:].strip().strip("\"'")
                            break
            elif content.startswith("# "):
                first_line = content.split("\n")[0]
                title = first_line[2:].strip()

            return RawItem(
                source="obsidian",
                source_id=relative_path,
                title=title,
                content=content,
                created_at=datetime.fromtimestamp(stat.st_ctime),
                updated_at=datetime.fromtimestamp(stat.st_mtime),
                metadata={
                    "path": relative_path,
                    "size_bytes": stat.st_size,
                },
            )
        except Exception as e:
            _logger.warning("Could not read %s: %s", filepath, e)
            return None

    def read(self, source_id: str) -> str | None:
        filepath = self._safe_path(source_id)
        if not filepath.exists():
            return None
        try:
            return filepath.read_text(encoding="utf-8")
        except Exception:
            return None

    def search(self, pattern: str) -> list[str]:
        matches = []
        pattern_lower = pattern.lower()

        for filepath, relative_path in _walk_markdown_files(self.vault_path):
            try:
                content = filepath.read_text(encoding="utf-8")
                if pattern_lower in content.lower():
                    matches.append(relative_path)
            except Exception:
                continue

        return matches

    def get_all_with_mtime(self) -> dict[str, datetime]:
        result = {}
        for filepath, relative_path in _walk_markdown_files(self.vault_path):
            try:
                mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
                result[relative_path] = mtime
            except Exception:
                continue
        return result

    def scan_item(self, source_id: str) -> RawItem | None:
        filepath = self._safe_path(source_id)
        if not filepath.exists():
            return None
        return self._read_file(filepath, source_id)

    def write(self, relative_path: str, content: str) -> bool:
        filepath = self._safe_path(relative_path)
        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content, encoding="utf-8")
            return True
        except Exception:
            return False

    def exists(self, relative_path: str) -> bool:
        try:
            return self._safe_path(relative_path).exists()
        except ValueError:
            return False

    def delete(self, relative_path: str) -> bool:
        filepath = self._safe_path(relative_path)
        try:
            if filepath.exists():
                filepath.unlink()
                return True
            return False
        except Exception:
            return False

    def move(self, source_path: str, dest_path: str) -> bool:
        source = self._safe_path(source_path)
        dest = self._safe_path(dest_path)
        try:
            if not source.exists():
                return False
            dest.parent.mkdir(parents=True, exist_ok=True)
            source.rename(dest)
            return True
        except Exception:
            return False
