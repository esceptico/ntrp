import json
from dataclasses import asdict
from pathlib import Path

from ntrp.slices.models import Slice


class SliceRegistry:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> list[Slice]:
        if not self._path.exists():
            return []
        data = json.loads(self._path.read_text())
        return [Slice(**s) for s in data["slices"]]

    def save(self, slices: list[Slice]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps({"slices": [asdict(s) for s in slices]}, indent=2))

    def get(self, key: str) -> Slice:
        slices = self.load()
        for s in slices:
            if s.key == key:
                return s
        raise KeyError(f"unknown slice '{key}'; valid: {[s.key for s in slices]}")
