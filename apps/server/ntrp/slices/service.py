from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime

from ntrp.memory.pages import Page
from ntrp.slices.asks import AskStore, nominate_focus
from ntrp.slices.models import Ask, AskState, Autonomy
from ntrp.slices.projection import page_summary
from ntrp.slices.registry import SliceRegistry


class SliceService:
    def __init__(
        self,
        registry: SliceRegistry,
        asks: AskStore,
        get_page: Callable[[str], Page],
        pending_approvals: Callable[[], list[dict]],
        session_slice: Callable[[str], str | None],
        slice_automations: Callable[[str], list[dict]],
        slice_sessions: Callable[[str], list[dict]],
    ) -> None:
        self._registry = registry
        self._asks = asks
        self._get_page = get_page
        self._pending_approvals = pending_approvals
        self._session_slice = session_slice
        self._slice_automations = slice_automations
        self._slice_sessions = slice_sessions

    def refresh_mechanical(self) -> None:
        now = datetime.now(UTC).isoformat()
        existing = {a.id for a in self._asks.list(include_resolved=True)}
        for row in self._pending_approvals():
            key = self._session_slice(row["session_id"])
            if key is None:
                continue
            ask_id = f"approval:{row['run_id']}:{row['tool_call_id']}"
            if ask_id in existing:
                continue
            self._asks.upsert(Ask(
                id=ask_id, slice_key=key,
                text=f"{row['tool_name']} wants: {row['preview'] or row['tool_name']}",
                kind="decide", source="approval",
                actions=[{"verb": "open_session", "ref": row["session_id"]}],
                state="active", created_at=now,
                provenance=f"run:{row['run_id']}",
            ))
        for s in self._registry.load():
            for auto in self._slice_automations(s.key):
                if not auto.get("last_result") or not str(auto["last_result"]).startswith("error"):
                    continue
                ask_id = f"runfail:{auto['name']}:{auto['last_run_at']}"
                if ask_id in existing:
                    continue
                self._asks.upsert(Ask(
                    id=ask_id, slice_key=s.key,
                    text=f"{auto['name']} failed — {auto['last_result']}",
                    kind="review", source="run_failed",
                    actions=[{"verb": "retry", "ref": auto["name"]}],
                    state="active", created_at=now,
                ))

    def overview(self) -> dict:
        slices = self._registry.load()
        all_asks = self._asks.list()
        focus = nominate_focus(all_asks)
        out = []
        for s in slices:
            summary = page_summary(self._get_page(s.page_path))
            slice_asks = [a for a in all_asks if a.slice_key == s.key]
            out.append({
                "key": s.key, "title": s.title, "autonomy": s.autonomy,
                "live": bool(slice_asks) or bool(
                    any(a.get("running_since") for a in self._slice_automations(s.key))
                ),
                "updated": summary["updated"], "ask_count": len(slice_asks),
            })
        return {"slices": out, "focus": [asdict(a) for a in focus]}

    def resolve_ask(self, ask_id: str, state: AskState, snoozed_until: str | None) -> dict:
        return asdict(self._asks.resolve(ask_id, state, snoozed_until))

    def update_autonomy(self, key: str, autonomy: Autonomy) -> dict:
        return asdict(self._registry.update_autonomy(key, autonomy))

    def create_slice(self, key: str, title: str, page_path: str) -> dict:
        return asdict(self._registry.create(key, title, page_path))

    def detail(self, key: str) -> dict:
        s = self._registry.get(key)
        summary = page_summary(self._get_page(s.page_path))
        return {
            "key": s.key, "title": s.title, "autonomy": s.autonomy,
            "page_path": s.page_path, "related": s.related,
            "open_loops": summary["open_loops"], "updated": summary["updated"],
            "asks": [asdict(a) for a in self._asks.list(key)],
            "sessions": self._slice_sessions(key),
            "automations": self._slice_automations(key),
        }
