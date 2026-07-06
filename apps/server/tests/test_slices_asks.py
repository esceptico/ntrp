from pathlib import Path
from ntrp.slices.asks import AskStore, nominate_focus
from ntrp.slices.models import Ask


def ask(id: str, slice_key: str, kind: str, created: str = "2026-07-06T10:00:00") -> Ask:
    return Ask(id=id, slice_key=slice_key, text=id, kind=kind, source="open_loop",
               actions=[], state="active", created_at=created)


def test_store_upsert_resolve_roundtrip(tmp_path: Path):
    store = AskStore(tmp_path / "state.json")
    store.upsert(ask("a1", "o-1a", "review"))
    store.resolve("a1", "dismissed")
    assert store.list("o-1a") == []
    assert store.list("o-1a", include_resolved=True)[0].state == "dismissed"


def test_snoozed_asks_hidden_until_deadline(tmp_path: Path):
    store = AskStore(tmp_path / "state.json")
    store.upsert(ask("a1", "o-1a", "review"))
    store.resolve("a1", "snoozed", snoozed_until="2099-01-01T00:00:00")
    assert store.list("o-1a") == []
    store.resolve("a1", "snoozed", snoozed_until="2000-01-01T00:00:00")
    assert [a.id for a in store.list("o-1a")] == ["a1"]  # snooze expired → active again


def test_nominate_focus_one_per_slice_kind_priority():
    asks = [
        ask("r", "dex", "review"), ask("d", "dex", "decide"),
        ask("x", "aside", "drift"), ask("y", "health", "act"),
    ]
    focus = nominate_focus(asks, cap=2)
    assert [a.id for a in focus] == ["d", "x"]  # decide beats review; drift beats act; cap 2
