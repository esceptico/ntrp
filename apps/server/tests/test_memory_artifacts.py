"""Artifact memory export/redaction and filesystem safety."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from ntrp.memory.artifacts import (
    ARTIFACT_WRAP_WIDTH,
    ArtifactMemoryStore,
    _redact_changelog,
    _sanitize_visible_text,
)
from ntrp.memory.models import Kind, SourceRef
from ntrp.memory.records import RecordStore

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.asyncio


async def _record_store(tmp_path: Path) -> RecordStore:
    return RecordStore(tmp_path / "memory.db", search_index=None)


def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlinks unavailable: {exc}")


async def test_export_emits_no_summary_bucket(tmp_path: Path):
    records = await _record_store(tmp_path)
    # Legacy summary-kind records are no longer a writable kind; they must not
    # resurrect a summaries/ projection. They land in the DB-backed fact pool.
    await records.add("legacy catch-up note that used to be a summary record", kind="summary")
    root = tmp_path / "artifacts"
    artifacts = ArtifactMemoryStore(root)

    await artifacts.export_from_records(records)

    assert not (root / "summaries").exists()
    assert not (root / "summaries.md").exists()
    with pytest.raises(FileNotFoundError):
        artifacts.read_artifact("summaries/index.md")
    assert not any(a.path.startswith("summaries/") for a in artifacts.list_artifacts())
    assert "summaries/" not in artifacts.read_artifact("README.md").content
    await records.close()


async def test_export_renders_project_prose_faithfully(tmp_path: Path):
    # Subject/project pages render records faithfully — real paths and names, no
    # [path]/[id] redaction (records are written clean by the curator).
    records = await _record_store(tmp_path)
    await records.add(
        "The ntrp artifact exporter keeps meaningful project prose visible, including "
        "real paths like /Users/escept1co/src/ntrp and names like obsidian-mcp.",
        kind=Kind.FACT,
        scope_kind="project",
        scope_key="export-artifact-demo",
    )

    artifacts = ArtifactMemoryStore(tmp_path / "artifacts")
    await artifacts.export_from_records(records)

    index = artifacts.read_artifact("projects/index.md").content
    content = artifacts.read_artifact("projects/export-artifact-demo.md").content
    assert "[[export-artifact-demo]]" in index
    assert "ntrp artifact exporter keeps meaningful project prose visible" in content
    assert "/Users/escept1co/src/ntrp" in content  # faithful: real path shown, not [path]
    assert "obsidian-mcp" in content
    assert all(len(line) <= ARTIFACT_WRAP_WIDTH + 40 for line in content.splitlines())
    await records.close()


async def test_changelog_redactor_preserves_meaningful_identifiers():
    content = _redact_changelog(
        "Completed final evaluations for stage25_sentence_bridge_300 and stage3_from_bridge_nl_400 "
        "all had exact_match 0.0. For stage25_sentence_bridge_300 at final step 299: correct "
        "normalized_similarity 0.7880833141408634 and avg_loss 1.3262231744255655; no_act "
        "normalized_similarity 0.6998057188013818. Artifacts included "
        "stage1_v3_delta_noact_calib_200_metrics.jsonl and train_tiny_oracle_delta_calib.py. "
        "The stage-3-from-bridge-nl-400 dashed slug is also meaningful. "
        "Legacy unquoted [technical id] placeholder damage should read as a technical identifier. "
        "Sensitive values remain hidden: run_id=run_secret123456 span_id=span_secret123456 "
        "project:proj_secret123456 abcdef1234567890abcdef1234567890 /Users/me/src/private/file.py",
        max_chars=2000,
    )
    for token in (
        "stage25_sentence_bridge_300",
        "stage3_from_bridge_nl_400",
        "exact_match",
        "normalized_similarity",
        "avg_loss",
        "no_act",
        "stage1_v3_delta_noact_calib_200_metrics.jsonl",
        "train_tiny_oracle_delta_calib.py",
        "stage-3-from-bridge-nl-400",
        "0.7880833141408634",
        "1.3262231744255655",
        "0.6998057188013818",
        "Legacy unquoted technical identifier placeholder damage",
    ):
        assert token in content
    assert "[technical id]" not in content
    for sensitive in (
        "run_secret123456",
        "span_secret123456",
        "project:proj_secret123456",
        "abcdef1234567890abcdef1234567890",
        "/Users/me",
    ):
        assert sensitive not in content


class EmptyRecords:
    async def list(self, *, limit):
        return []

    async def labels_for(self, record_ids):
        return {rid: [] for rid in record_ids}

    async def list_labels(self):
        return []


async def test_source_ref_repr_debug_fragment_is_migrated_and_stripped_from_changelog(tmp_path: Path):
    root = tmp_path / "artifacts"
    root.mkdir()
    raw = (
        "# Changelog\n\n"
        "- 2025-01-01T00:00:00+00:00 — remembered summary "
        "source_ref=SourceRef(kind='chat_turn', ref='session-secret:toolu_secret123456', "
        "captured_at='2025-01-01T00:00:00Z', scope_kind='session') trailing prose\n"
    )
    (root / "changelog.md").write_text(raw, encoding="utf-8")

    store = ArtifactMemoryStore(root)
    await store.export_from_records(EmptyRecords())  # type: ignore[arg-type]
    artifact = store.read_artifact("changelog/2025/2025-01.md")

    assert not (root / "changelog.md").exists()
    # The legacy line is contentless audit noise → dropped on render; either way
    # no raw provenance reprs/secrets survive into the changelog.
    for raw_token in ("SourceRef", "session-secret", "toolu_secret123456", "captured_at", "scope_kind", "source_ref"):
        assert raw_token not in artifact.content


async def test_changelog_migration_sanitizes_existing_content(tmp_path: Path):
    root = tmp_path / "artifacts"
    root.mkdir()
    (root / "changelog.md").write_text(
        "# Changelog\n\n"
        "- 2025-01-01T00:00:00+00:00 — pinned record abcdef1234567890abcdef1234567890 "
        "scope=project:proj_readsecret123 /Users/me/src/ntrp run_id=run_readsecret123456\n",
        encoding="utf-8",
    )

    store = ArtifactMemoryStore(root)
    await store.export_from_records(EmptyRecords())  # type: ignore[arg-type]
    artifact = store.read_artifact("changelog/2025/2025-01.md")

    # Contentless secret-laden legacy line → dropped on render; no secrets survive.
    for raw_token in (
        "abcdef1234567890abcdef1234567890",
        "scope=",
        "project:proj_readsecret123",
        "/Users/me",
        "run_readsecret",
    ):
        assert raw_token not in artifact.content
    assert (root / "changelog" / "2025" / "2025-01.md").read_text(encoding="utf-8") == artifact.content


async def test_changelog_append_uses_monthly_file_after_missing_final_newline(tmp_path: Path):
    root = tmp_path / "artifacts"
    root.mkdir()
    (root / "changelog.md").write_text("# Changelog", encoding="utf-8")

    # A content-bearing event (contentless ones like "added fact memory" are
    # dropped as noise on render).
    ArtifactMemoryStore(root).append_event("Remembered: the user prefers tea")

    month = datetime.now(UTC).strftime("%Y-%m")
    content = (root / "changelog" / month[:4] / f"{month}.md").read_text(encoding="utf-8")
    assert f"# Changelog {month}" in content
    assert "\n- " in content
    assert "Remembered: the user prefers tea" in content
    assert "Changelog- " not in content


def _mkfifo_or_skip(path: Path) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("mkfifo unavailable")
    try:
        os.mkfifo(path)
    except OSError as exc:
        pytest.skip(f"mkfifo unavailable: {exc}")


async def test_existing_fifo_generated_artifact_write_fails_safe(tmp_path: Path):
    root = tmp_path / "artifacts"
    (root / "facts").mkdir(parents=True)
    _mkfifo_or_skip(root / "facts" / "index.md")

    with pytest.raises(FileNotFoundError):
        await ArtifactMemoryStore(root).export_from_records(EmptyRecords())  # type: ignore[arg-type]


async def test_existing_fifo_changelog_append_fails_safe(tmp_path: Path):
    root = tmp_path / "artifacts"
    root.mkdir()
    _mkfifo_or_skip(root / "changelog.md")

    with pytest.raises(FileNotFoundError):
        ArtifactMemoryStore(root).append_event("remembered fact memory")


async def test_failed_record_read_preserves_existing_generated_artifacts(tmp_path: Path):
    root = tmp_path / "artifacts"
    (root / "facts").mkdir(parents=True)
    (root / "facts" / "global.md").write_text("# Global facts\n\n- keep me\n", encoding="utf-8")

    class BrokenRecords:
        async def list(self, *, limit):
            raise RuntimeError("database unavailable")

    with pytest.raises(RuntimeError):
        await ArtifactMemoryStore(root).export_from_records(BrokenRecords())  # type: ignore[arg-type]

    assert (root / "facts" / "global.md").read_text(encoding="utf-8") == "# Global facts\n\n- keep me\n"


async def test_artifact_root_under_symlinked_parent_is_allowed(tmp_path: Path):
    records = await _record_store(tmp_path)
    await records.add("ntrp keeps artifacts under memory", kind=Kind.FACT)
    real_parent = tmp_path / "real-parent"
    alias_parent = tmp_path / "alias-parent"
    real_parent.mkdir()
    try:
        alias_parent.symlink_to(real_parent, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"directory symlinks unavailable: {exc}")

    artifacts = ArtifactMemoryStore(alias_parent / "memory")
    await artifacts.export_from_records(records)

    facts = artifacts.read_artifact("facts/index.md").content
    assert "Facts are DB-backed" in facts
    assert "global: 1 active fact records" in facts
    assert "ntrp keeps artifacts under memory" not in facts
    await records.close()


async def test_existing_changelog_is_sanitized_on_rebuild_without_reconstruction(tmp_path: Path):
    records = await _record_store(tmp_path)
    root = tmp_path / "artifacts"
    root.mkdir()
    raw_event = (
        "- 2024-01-02T03:04:05+00:00 — added fact record "
        "abcdef1234567890abcdef1234567890 scope=project:proj_forbidden123456 "
        "source_ref=chat_turn:session path=/Users/escept1co/src/ntrp "
        "run_id=run_forbidden123456 span_id=span_forbidden123456 tool_id=toolu_forbidden123456 "
        "hash=abcdef1234567890abcdef1234567890\n"
    )
    (root / "changelog.md").write_text("# Changelog\n\n" + raw_event, encoding="utf-8")

    await ArtifactMemoryStore(root).export_from_records(records)

    content = (root / "changelog" / "2024" / "2024-01.md").read_text(encoding="utf-8")
    # Contentless secret-laden legacy line → dropped on render; no secrets survive.
    for raw in (
        "abcdef1234567890abcdef1234567890",
        "scope=",
        "project:proj_forbidden123456",
        "source_ref",
        "/Users/escept1co/src/ntrp",
        "run_forbidden123456",
        "span_forbidden123456",
        "toolu_forbidden123456",
    ):
        assert raw not in content
    assert not (root / "changelog.md").exists()
    await records.close()


async def test_broken_symlink_nested_artifact_write_fails_safe(tmp_path: Path):
    records = await _record_store(tmp_path)
    await records.add("Regina drives the entity dossier", kind=Kind.FACT)
    root = tmp_path / "artifacts"
    outside = tmp_path / "outside"
    (root / "entities").mkdir(parents=True)
    outside.mkdir()
    _symlink_or_skip(root / "entities" / "index.md", outside / "owned.md")

    with pytest.raises(FileNotFoundError):
        await ArtifactMemoryStore(root).export_from_records(records)

    assert not (outside / "owned.md").exists()
    await records.close()


async def test_broken_symlink_changelog_append_fails_safe(tmp_path: Path):
    root = tmp_path / "artifacts"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    _symlink_or_skip(root / "changelog.md", outside / "owned.md")

    with pytest.raises(FileNotFoundError):
        ArtifactMemoryStore(root).append_event("remembered fact memory")

    assert not (outside / "owned.md").exists()


async def test_read_and_list_skip_symlinked_nested_artifacts(tmp_path: Path):
    root = tmp_path / "artifacts"
    outside = tmp_path / "outside"
    (root / "facts").mkdir(parents=True)
    outside.mkdir()
    (outside / "index.md").write_text("# Outside\n", encoding="utf-8")
    _symlink_or_skip(root / "facts" / "index.md", outside / "index.md")

    artifacts = ArtifactMemoryStore(root)
    assert artifacts.list_artifacts(kind="fact") == []
    with pytest.raises(FileNotFoundError):
        artifacts.read_artifact("facts/index.md")


async def test_export_default_requests_unbounded_record_list(tmp_path: Path):
    class FakeRecords:
        def __init__(self):
            self.limit = "unset"

        async def list(self, *, limit):
            self.limit = limit
            return []

        async def labels_for(self, record_ids):
            return {rid: [] for rid in record_ids}

        async def list_labels(self):
            return []

    fake = FakeRecords()

    await ArtifactMemoryStore(tmp_path / "artifacts").export_from_records(fake)  # type: ignore[arg-type]

    assert fake.limit is None


async def test_v3_facts_index_replaces_fact_dumps(tmp_path: Path):
    records = await _record_store(tmp_path)
    await records.add("known raw global fact should not dump", kind=Kind.FACT)
    await records.add("known raw user fact should not dump", kind=Kind.FACT, scope_kind="user")
    artifacts = ArtifactMemoryStore(tmp_path / "artifacts")

    await artifacts.export_from_records(records)

    facts = artifacts.read_artifact("facts/index.md")
    assert facts.kind == "fact"
    assert facts.record_count is None
    assert "Facts are DB-backed" in facts.content
    assert "known raw global fact" not in facts.content
    assert "known raw user fact" not in facts.content
    for legacy in ("facts/global.md", "facts/user.md", "facts/other-scopes.md"):
        with pytest.raises(FileNotFoundError):
            artifacts.read_artifact(legacy)
    for path in (tmp_path / "artifacts" / "facts").glob("*.md"):
        content = path.read_text(encoding="utf-8")
        assert "known raw" not in content
    await records.close()


async def test_references_consolidate_sources_files_and_docs(tmp_path: Path):
    records = await _record_store(tmp_path)
    await records.add(
        "Edited the exporter in apps/server/ntrp/memory/artifacts.py for the bucket fix",
        kind=Kind.FACT,
    )
    await records.add(
        "Reviewed the README documentation and the project docs for the rollout",
        kind=Kind.FACT,
        scope_kind="user",
    )
    artifacts = ArtifactMemoryStore(tmp_path / "artifacts")

    await artifacts.export_from_records(records)

    references = artifacts.read_artifact("references/index.md")
    source_records = artifacts.read_artifact("references/records.md")

    assert references.kind == "source"
    assert references.record_count is None
    assert "## Source types" in references.content
    assert "## Buckets" in references.content
    assert "## Recent pointers" in references.content
    assert "files/repos: 1 records" in references.content
    assert "docs/web: 1 records" in references.content
    assert "artifacts.py for the bucket fix" in references.content
    assert "README documentation" in references.content
    assert source_records.path == "references/records.md"

    for old_path in ("files/index.md", "docs/index.md", "sources/index.md"):
        with pytest.raises(FileNotFoundError):
            artifacts.read_artifact(old_path)
    await records.close()


async def test_context_index_and_schema_are_generated(tmp_path: Path):
    records = await _record_store(tmp_path)
    await records.add("ntrp memory keeps records canonical", kind=Kind.FACT)
    artifacts = ArtifactMemoryStore(tmp_path / "artifacts")

    await artifacts.export_from_records(records)

    context = artifacts.read_artifact("context/index.md")
    schema = artifacts.read_artifact("context/SCHEMA.md")
    assert context.kind == "topic"
    assert schema.kind == "topic"
    assert "me.md" in context.content
    assert "active-work.md" in context.content
    assert "SQLite" in schema.content
    assert "directive | fact | source" in schema.content
    assert "changelog` is generated audit output" in schema.content
    assert "context/index.md" in {artifact.path for artifact in artifacts.list_artifacts()}
    assert "context/SCHEMA.md" in {artifact.path for artifact in artifacts.list_artifacts(q="SQLite")}
    for old_path in ("sources/index.md", "files/index.md", "docs/index.md"):
        with pytest.raises(FileNotFoundError):
            artifacts.read_artifact(old_path)
    await records.close()


async def test_skill_candidates_are_generated_from_directives_only(tmp_path: Path):
    records = await _record_store(tmp_path)
    await records.add(
        "Always use repo-grounded evidence before making codebase claims from "
        "rec_secret123456 and 123e4567-e89b-12d3-a456-426614174000 and "
        "abcdef1234567890abcdef1234567890",
        kind=Kind.DIRECTIVE,
    )
    await records.add("The user has a plain fact that should not be a skill", kind=Kind.FACT)
    await records.add("A source receipt that should not be a skill", kind=Kind.SOURCE)
    artifacts = ArtifactMemoryStore(tmp_path / "artifacts")

    await artifacts.export_from_records(records)

    index = artifacts.read_artifact("context/skill-candidates/index.md")
    candidates = [
        a for a in artifacts.list_artifacts(q="create_skill") if a.path.startswith("context/skill-candidates/")
    ]
    assert "repo-grounded" in index.content
    assert "plain fact" not in index.content
    assert any(a.path != "context/skill-candidates/index.md" for a in candidates)
    page = artifacts.read_artifact(next(a.path for a in candidates if a.path != "context/skill-candidates/index.md"))
    assert page.kind == "topic"
    assert page.source == "deterministic"
    assert page.record_count == 1
    assert "not an installed skill" in page.content
    assert "create_skill" in page.content
    assert "Use when" in page.content
    assert "repo-grounded evidence" in page.content
    assert "rec_secret123456" not in page.content
    assert "rec_" not in page.content
    assert "123e4567-e89b-12d3-a456-426614174000" not in page.content
    assert "abcdef1234567890abcdef1234567890" not in page.content
    await records.close()


async def test_integration_reference_pages_are_generated_from_existing_records(tmp_path: Path):
    records = await _record_store(tmp_path)
    await records.add(
        "Slack channel #eng discussed memory publish ordering",
        kind=Kind.FACT,
        source_ref=SourceRef(kind="slack", ref="channel:eng"),
    )
    await records.add(
        "Gmail receipt for a customer follow-up",
        kind=Kind.SOURCE,
        scope_kind="integration",
        scope_key="gmail:gmail:batch",
        source_ref=SourceRef(kind="gmail", ref="message:abc"),
    )
    await records.add(
        "Email receipt for a customer follow-up",
        kind=Kind.SOURCE,
        scope_kind="integration",
        scope_key="email:message:xyz",
        source_ref=SourceRef(kind="email", ref="message:xyz"),
    )
    await records.add(
        "Generic integration receipt for external ingest",
        kind=Kind.SOURCE,
        scope_kind="integration",
        scope_key="integration:external:item",
        source_ref=SourceRef(kind="integration", ref="external:item"),
    )
    await records.add(
        "Linear issue receipt for roadmap context",
        kind=Kind.SOURCE,
        scope_kind="integration",
        scope_key="linear:issue:ABC-123",
    )
    await records.add(
        "Curator wrote an internal fact and should not get an integration page",
        kind=Kind.FACT,
        source_ref=SourceRef(kind="curator", ref="internal"),
    )
    artifacts = ArtifactMemoryStore(tmp_path / "artifacts")

    await artifacts.export_from_records(records)

    index = artifacts.read_artifact("context/integrations/index.md")
    slack = artifacts.read_artifact("context/integrations/slack.md")
    gmail = artifacts.read_artifact("context/integrations/gmail.md")
    email = artifacts.read_artifact("context/integrations/email.md")
    integration = artifacts.read_artifact("context/integrations/integration.md")
    linear = artifacts.read_artifact("context/integrations/linear.md")
    assert "[[Slack]]" in index.content
    assert "[[Gmail]]" in index.content
    assert "[[Email]]" in index.content
    assert "[[Integration]]" in index.content
    assert "[[Linear]]" in index.content
    assert slack.record_count == 1
    assert gmail.record_count == 1
    assert email.record_count == 1
    assert integration.record_count == 1
    assert linear.record_count == 1
    assert "channel #eng" in slack.content
    assert "Gmail receipt" in gmail.content
    assert "Email receipt" in email.content
    assert "Generic integration receipt" in integration.content
    assert "Linear issue receipt" in linear.content
    with pytest.raises(FileNotFoundError):
        artifacts.read_artifact("context/integrations/gmail-gmail-batch.md")
    with pytest.raises(FileNotFoundError):
        artifacts.read_artifact("context/integrations/email-message-xyz.md")
    with pytest.raises(FileNotFoundError):
        artifacts.read_artifact("context/integrations/integration-external-item.md")
    with pytest.raises(FileNotFoundError):
        artifacts.read_artifact("context/integrations/linear-issue-abc-123.md")
    with pytest.raises(FileNotFoundError):
        artifacts.read_artifact("context/integrations/curator.md")
    await records.close()


async def test_entity_dossier_from_shared_safe_label(tmp_path: Path):
    records = await _record_store(tmp_path)
    r1 = await records.add("Regina is researching context windows for the research thread", kind=Kind.FACT)
    r2 = await records.add("Research thread needs a concise dossier?", kind=Kind.FACT)
    # entity_labels drive dossier generation; meta_labels (flat list) do not
    await records.set_labels(r1.id, [], entity_labels=["Regina", "Research thread"])
    await records.set_labels(r2.id, [], entity_labels=["Regina", "Research thread"])
    artifacts = ArtifactMemoryStore(tmp_path / "artifacts")

    await artifacts.export_from_records(records)

    index = artifacts.read_artifact("entities/index.md")
    dossier = artifacts.read_artifact("entities/regina.md")
    assert "[[Regina]]" in index.content
    assert dossier.kind == "topic"
    assert dossier.scope_kind == "entity"
    assert dossier.record_count == 2
    assert dossier.source == "consolidate"
    assert "Research thread" in dossier.labels
    for heading in ("## What we know", "## Open questions"):
        assert heading in dossier.content
    assert "## Metadata" not in dossier.content
    assert "Generated read-only dossier" not in dossier.content
    assert "summarizes 2 active memory records" not in dossier.content
    assert r1.id not in dossier.content and r2.id not in dossier.content
    assert "source_ref" not in dossier.content
    assert "/Users/" not in dossier.content
    assert all(len(line) <= 1000 for line in dossier.content.splitlines())
    await records.close()


async def test_entity_dossier_compiled_brief_sections(tmp_path: Path):
    """An entity label with >=2 records yields a sectioned compiled brief:
    What we know, Open questions, Related. The page is a clean Obsidian note —
    no agent-tool footer. Directives are global rules (directives.md) and are
    EXCLUDED from subject pages. A meta label gets no page and the index is not
    the placeholder."""
    records = await _record_store(tmp_path)
    # Directive record on the subject — must NOT appear in the subject page.
    d = await records.add("Always greet Dex by name in updates", kind=Kind.DIRECTIVE)
    f1 = await records.add("Dex started crawling", kind=Kind.FACT)
    f2 = await records.add("Dex started crawling last week in the living room", kind=Kind.FACT)
    # A question record -> ## Open questions.
    q = await records.add("When does Dex start daycare?", kind=Kind.FACT)
    for r in (d, f1, f2, q):
        await records.set_labels(r.id, ["Sleep"], entity_labels=["Dex"])
    # A pure meta label (no entity_label) -> must NOT get a dossier.
    m = await records.add("intermittent 500 on the memory router", kind=Kind.FACT)
    await records.set_labels(m.id, ["Bug"])
    artifacts = ArtifactMemoryStore(tmp_path / "artifacts")

    await artifacts.export_from_records(records)

    dossier = artifacts.read_artifact("entities/dex.md")
    content = dossier.content
    assert "_Compiled subject brief" in content
    assert "## Directives" not in content  # directives excluded from subject dossiers
    assert "Always greet Dex by name" not in content
    assert "## What we know" in content
    assert "## Open questions" in content
    assert "When does Dex start daycare?" in content
    assert "## Related" in content
    assert "Sleep" in content  # co-occurring label
    # Human note: no agent-tool footer.
    assert "recall(" not in content
    assert "_Raw records" not in content

    # Meta-only label produced no dossier.
    with pytest.raises(FileNotFoundError):
        artifacts.read_artifact("entities/bug.md")

    index = artifacts.read_artifact("entities/index.md")
    assert "[[Dex]]" in index.content
    assert "_No high-confidence entity dossiers yet._" not in index.content
    await records.close()


async def test_low_confidence_entity_labels_go_to_triage(tmp_path: Path):
    records = await _record_store(tmp_path)
    r = await records.add("Orchidaceae note should not get a one-off dossier", kind=Kind.FACT)
    # One entity_label record is below MIN_ENTITY_RECORDS threshold -> triage
    await records.set_labels(r.id, [], entity_labels=["Orchidaceae"])
    artifacts = ArtifactMemoryStore(tmp_path / "artifacts")

    await artifacts.export_from_records(records)

    with pytest.raises(FileNotFoundError):
        artifacts.read_artifact("entities/orchidaceae.md")
    triage = artifacts.read_artifact("entities/needs-triage.md")
    assert "Orchidaceae: 1 record" in triage.content
    await records.close()


async def test_project_dossier_is_not_fact_bullet_dump(tmp_path: Path):
    records = await _record_store(tmp_path)
    await records.add(
        "Project alpha should ship dossiers", kind=Kind.FACT, scope_kind="project", scope_key="proj_alpha123"
    )
    artifacts = ArtifactMemoryStore(tmp_path / "artifacts")

    await artifacts.export_from_records(records)

    index = artifacts.read_artifact("projects/index.md")
    assert "[[proj_alpha123]]" in index.content
    dossier_path = next(
        a.path
        for a in artifacts.list_artifacts()
        if a.path.startswith("projects/") and a.path not in ("projects/index.md", "projects/inbox.md")
    )
    dossier = artifacts.read_artifact(dossier_path)
    assert dossier.kind == "topic"
    assert dossier.record_count == 1
    assert "Generated read-only dossier" not in dossier.content
    assert "## What we know" in dossier.content
    assert "# Project facts" not in dossier.content
    await records.close()


async def test_entity_labels_only_entity_kind_gets_dossier(tmp_path: Path):
    """meta_labels (flat list) never produce dossiers; only entity_labels do.
    Garbage like URLs or opaque IDs should never reach entity_labels in the first
    place (the curator is responsible for that), but if they somehow do they still
    won't produce a dossier because the curator sanitized them before storing."""
    records = await _record_store(tmp_path)
    r1 = await records.add("Customer success needs durable account context", kind=Kind.FACT)
    r2 = await records.add("Customer success onboarding should be summarized", kind=Kind.FACT)
    # entity_labels: only real named entities
    await records.set_labels(r1.id, ["Bug", "Open loop"], entity_labels=["Customer success"])
    await records.set_labels(r2.id, ["Bug"], entity_labels=["Customer success"])
    artifacts = ArtifactMemoryStore(tmp_path / "artifacts")

    await artifacts.export_from_records(records)

    index = artifacts.read_artifact("entities/index.md")
    assert "[[Customer success]]" in index.content
    dossier = artifacts.read_artifact("entities/customer-success.md")
    assert dossier.title == "Customer success"

    # meta labels must NOT produce dossiers
    for bad in ("entities/bug.md", "entities/open-loop.md"):
        with pytest.raises(FileNotFoundError):
            artifacts.read_artifact(bad)
    await records.close()


async def test_project_dossier_preserves_canonical_scope_key_in_api_metadata(tmp_path: Path):
    records = await _record_store(tmp_path)
    await records.add(
        "Project alpha needs a brief", kind=Kind.FACT, scope_kind="project", scope_key="project:proj_alpha123"
    )
    artifacts = ArtifactMemoryStore(tmp_path / "artifacts", project_names={"project:proj_alpha123": "Alpha"})

    await artifacts.export_from_records(records)

    dossier = artifacts.read_artifact("projects/alpha.md")
    assert dossier.scope_kind == "project"
    assert dossier.scope_key == "project:proj_alpha123"
    listed = {a.path: a for a in artifacts.list_artifacts()}
    assert listed["projects/alpha.md"].scope_key == "project:proj_alpha123"
    await records.close()
