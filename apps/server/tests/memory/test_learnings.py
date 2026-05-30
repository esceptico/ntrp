from datetime import date

import pytest

from ntrp.memory.learnings import Correction, LearningsStore


@pytest.fixture
def store(tmp_path):
    return LearningsStore(base_dir=tmp_path / "learnings")


def test_record_creates_file_with_header(store, tmp_path):
    store.record(
        Correction(adjudicator="contradiction", action="not_same", summary="A is not B"),
        on=date(2026, 5, 30),
    )
    text = store.load("contradiction")
    assert text.startswith("# Learnings: contradiction judging")
    assert "## 2026-05-30 — not_same" in text
    assert "A is not B" in text


def test_record_appends_without_duplicating_header(store):
    store.record(Correction(adjudicator="dedup", action="edit", summary="first"), on=date(2026, 5, 30))
    store.record(Correction(adjudicator="dedup", action="edit", summary="second"), on=date(2026, 5, 31))
    text = store.load("dedup")
    assert text.count("# Learnings") == 1
    assert "first" in text and "second" in text


def test_record_renders_optional_fields_only_when_present(store):
    store.record(
        Correction(
            adjudicator="entity_link",
            action="not_same",
            summary="Regina Lin is not Regina Volkov",
            subjects=("id_a", "id_b"),
            proposed="merge(id_a, id_b)",
            correct="not_same",
            reason="different people",
        ),
        on=date(2026, 5, 30),
    )
    text = store.load("entity_link")
    assert "- subjects: id_a, id_b" in text
    assert "- proposed: merge(id_a, id_b)" in text
    assert "- correct: not_same" in text
    assert "- reason: different people" in text


def test_record_omits_empty_fields(store):
    store.record(Correction(adjudicator="dedup", action="edit", summary="bare"), on=date(2026, 5, 30))
    text = store.load("dedup")
    assert "- subjects:" not in text
    assert "- reason:" not in text


def test_load_missing_returns_empty(store):
    assert store.load("dedup") == ""


def test_unknown_adjudicator_raises(store):
    with pytest.raises(ValueError):
        store.record(Correction(adjudicator="bogus", action="edit", summary="x"))
    with pytest.raises(ValueError):
        store.load("bogus")


def test_list_adjudicators(store):
    assert store.list_adjudicators() == []
    store.record(Correction(adjudicator="dedup", action="edit", summary="x"))
    store.record(Correction(adjudicator="contradiction", action="undo", summary="y"))
    assert store.list_adjudicators() == ["contradiction", "dedup"]
