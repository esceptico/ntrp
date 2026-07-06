import json
from pathlib import Path
from ntrp.slices.models import Slice
from ntrp.slices.registry import SliceRegistry


def test_registry_roundtrip(tmp_path: Path):
    path = tmp_path / "slices.json"
    reg = SliceRegistry(path)
    assert reg.load() == []
    reg.save([Slice(key="o-1a", title="O-1A", page_path="topics/o-1a.md", autonomy="observe")])
    loaded = SliceRegistry(path).load()
    assert loaded[0].key == "o-1a"
    assert loaded[0].autonomy == "observe"
    assert json.loads(path.read_text())["slices"][0]["page_path"] == "topics/o-1a.md"


def test_registry_get_unknown_lists_valid_keys(tmp_path: Path):
    reg = SliceRegistry(tmp_path / "slices.json")
    reg.save([Slice(key="o-1a", title="O-1A", page_path="topics/o-1a.md", autonomy="observe")])
    try:
        reg.get("visa")
        raise AssertionError("expected KeyError")
    except KeyError as e:
        assert "o-1a" in str(e)  # self-correcting interface: list valid keys on miss
