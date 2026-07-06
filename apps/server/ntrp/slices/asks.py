import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from ntrp.slices.models import Ask, AskState

_KIND_PRIORITY = {"decide": 0, "drift": 1, "review": 2, "act": 3}


class AskStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._asks: dict[str, Ask] = {}
        if path.exists():
            data = json.loads(path.read_text())
            self._asks = {a["id"]: Ask(**a) for a in data["asks"]}

    def _flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps({"asks": [asdict(a) for a in self._asks.values()]}, indent=2))

    def upsert(self, ask: Ask) -> None:
        self._asks[ask.id] = ask
        self._flush()

    def resolve(self, ask_id: str, state: AskState, snoozed_until: str | None = None) -> Ask:
        if ask_id not in self._asks:
            raise KeyError(f"unknown ask '{ask_id}'; valid: {list(self._asks)}")
        ask = self._asks[ask_id]
        ask.state = state
        ask.snoozed_until = snoozed_until
        self._flush()
        return ask

    def list(self, slice_key: str | None = None, include_resolved: bool = False) -> list[Ask]:
        now = datetime.now(UTC).isoformat()
        out = []
        for a in self._asks.values():
            if slice_key and a.slice_key != slice_key:
                continue
            active = a.state == "active" or (
                a.state == "snoozed" and a.snoozed_until is not None and a.snoozed_until <= now
            )
            if include_resolved or active:
                out.append(a)
        return sorted(out, key=lambda a: a.created_at, reverse=True)


def nominate_focus(asks: list[Ask], cap: int = 4) -> list[Ask]:
    best: dict[str, Ask] = {}
    for a in asks:
        cur = best.get(a.slice_key)
        if cur is None or (_KIND_PRIORITY[a.kind], a.created_at) < (_KIND_PRIORITY[cur.kind], cur.created_at):
            best[a.slice_key] = a
    ranked = sorted(best.values(), key=lambda a: (_KIND_PRIORITY[a.kind], a.created_at))
    return ranked[:cap]
