"""Filesystem-backed memory artifact projection (v3).

SQLite/RecordStore remains canonical for atomic records and retrieval. Markdown
under the configured memory artifacts directory is a safe readable projection and
context surface only: facts are represented by a DB-backed index, while
entities/projects are concise generated dossiers rather than fact dumps.

memory/
  README.md
  tooling.md
  directives.md
  facts/index.md
  context/
  entities/
  projects/
  references/
  changelog/
"""

from __future__ import annotations

import errno
import hashlib
import logging
import os
import re
import sqlite3
import stat
import textwrap
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ntrp.memory import prompts_synthesis
from ntrp.memory.frontmatter import QuotedStr, dump_frontmatter, parse_frontmatter, strip_frontmatter
from ntrp.memory.models import Record
from ntrp.memory.pages import SENTINEL as _PAGE_SENTINEL
from ntrp.memory.pages import parse_line as _parse_line
from ntrp.memory.records import RecordStore
from ntrp.memory.scopes import INTEGRATION_SOURCE_KINDS as SCOPE_INTEGRATION_SOURCE_KINDS

_logger = logging.getLogger(__name__)

CANONICAL_KINDS = {"directive", "fact", "source"}

# Frontmatter `source` marker on LLM-synthesized pages (me.md, dossiers,
# active-work.md). The cheap mechanical sync preserves these instead of
# clobbering them with bullet dumps; only a full LLM rebuild refreshes them.
SYNTHESIS_SOURCE = "synthesis"
ACTIVE_WORK_RECENT_DAYS = 7
PROFILE_RECORD_CAP = 80
LEGACY_KIND_MAP = {
    "preference": "fact",
    "project_fact": "fact",
    "feedback": "source",
    "changelog": "source",
}

ROOT_ARTIFACTS: dict[str, tuple[str, str]] = {
    "me.md": ("topic", "Profile"),
    "active-work.md": ("topic", "Active work"),
    "README.md": ("source", "Memory artifacts"),
    "tooling.md": ("source", "Agent memory tooling"),
    "directives.md": ("directive", "Directives"),
    "lessons.md": ("directive", "Playbook (learned)"),
    "index.md": ("topic", "Index"),
    "AGENTS.md": ("source", "Memory conventions"),
    "health.md": ("topic", "Health & gaps"),
}
ARTIFACT_DIR_KINDS: dict[str, str] = {
    "facts": "fact",
    "context": "topic",
    "topics": "topic",  # unified subject folder (people/products/projects/topics)
    "entities": "topic",  # legacy — folded into topics/ (kept so leftovers still read)
    "projects": "topic",  # legacy — folded into topics/
    "references": "source",
    "observations": "source",  # per-source raw integration stream (gmail/slack/calendar) — browsable, not a dossier
    "insights": "topic",  # cross-domain dream outputs (OKF insights/)
    "daily": "source",  # dated activity logs (daily/<date>.md) — browsable history, prose-only
    "changelog": "changelog",
}
ARTIFACT_DIR_ORDER = {name: i for i, name in enumerate(ARTIFACT_DIR_KINDS)}
KNOWN_INTEGRATION_SOURCE_KINDS = frozenset({
    *SCOPE_INTEGRATION_SOURCE_KINDS,
    "github",
    "notion",
    "obsidian",
})
INTEGRATION_TITLES = {
    "slack": "Slack",
    "gmail": "Gmail",
    "email": "Email",
    "calendar": "Calendar",
    "github": "GitHub",
    "notion": "Notion",
    "obsidian": "Obsidian",
    "mcp": "MCP",
    "web": "Web",
    "file": "File",
    # Generic source_ref.kind="integration" is part of the write/provenance
    # contract. Roll it up deliberately instead of fragmenting by scope ref.
    "integration": "Integration",
}

ARTIFACT_WRAP_WIDTH = 100
MAX_BULLET_CHARS = 1000
MAX_LOG_CHARS = 500
MAX_TITLE_CHARS = 120
MAX_DOSSIER_SNIPPET_CHARS = 280
MAX_DOSSIER_ITEMS = 5
MAX_ENTITY_DOSSIERS = 25
MIN_ENTITY_RECORDS = 2
MIN_TRIAGE_RECORDS = 1

_CHANGELOG_HEADER_TEMPLATE = (
    "# Changelog {month}\n\n"
    "Atomic monthly memory mutation log for {month}. "
    "Markdown is generated from DB mutations and append events; do not edit it as canonical memory.\n"
)
_LEGACY_CHANGELOG_RE = re.compile(r"^-\s+(\d{4})-(\d{2})")
_CHANGELOG_MONTH_RE = re.compile(r"^changelog/(\d{4})/(\d{4}-\d{2})\.md$")
_CHANGELOG_YEAR_RE = re.compile(r"^changelog/(\d{4})\.md$")
_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")
_WIKILINK_RE = re.compile(r"\[\[([^\]#|]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]")
_DEBUG_KEYS = (
    "scope",
    "scope_key",
    "scope_kind",
    "source",
    "source_ref",
    "source_kind",
    "ref",
    "captured_at",
    "project",
    "project_id",
    "session",
    "session_id",
    "run_id",
    "span_id",
    "tool_id",
    "trigger_key",
    "record_id",
    "hash",
)
_DEBUG_KEY_PATTERN = "|".join(re.escape(k).replace("_", r"[_-]?") for k in _DEBUG_KEYS)
_SOURCE_REF_RE = re.compile(r"\bSourceRef\([^)]*\)", flags=re.IGNORECASE)
_URL_RE = re.compile(r"https?://[^\s,;)]+")
_DEBUG_KV_RE = re.compile(
    r"(?:(?<=^)|(?<=[\s,;({\[]))"
    r"[\"']?(?:" + _DEBUG_KEY_PATTERN + r")[\"']?"
    r"\s*[:=]\s*"
    r"(?:\{[^}\r\n]*\}|\[[^\]\r\n]*\]|[A-Za-z_][\w.]*\([^)]*\)|\([^)]*\)|\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;)\]}]+)",
    flags=re.IGNORECASE,
)
_LOCAL_PATH_RE = re.compile(
    r"(?<!\w)(?:~|/Users|/home|/private/var/folders|/private/tmp|/tmp|/var/folders)(?:/[^\s,;:)]*)*"
    r"|\b[A-Za-z]:(?:\\|/)[^\s,;)]*",
)
_REPO_PATH_RE = re.compile(
    r"(?<!\w)(?:apps|packages|src|tests|docs|backup|session_logs|preserved_tmp_[A-Za-z0-9_-]*|pipeline-v2|trigger|scripts)(?:/[^\s,;:)]+)+"
    r"|(?<!\w)/api(?:/[^\s,;:)]+)+"
    r"|(?<!\w)[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[^\s,;:)]+)*(?:\.(?:py|ts|tsx|rs|md|jsonl?|ya?ml|toml|log|sh|sql|html|css))",
)
_UUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_LONG_HEX_RE = re.compile(r"(?i)(?=[0-9a-f]*[a-f])\b[0-9a-f]{16,}\b")
_SHORT_COMMIT_RE = re.compile(r"(?i)(?=.*[a-f])\b[0-9a-f]{7,15}\b")
# Redact opaque operational identifiers, not meaningful technical names.
# Human-readable experiment/metric tokens like `stage25_sentence_bridge_300`,
# `exact_match`, `avg_loss`, `no_act`, and dashed slugs must remain readable.
_DASHED_ID_RE = re.compile(r"\b[A-Z0-9]{5,}(?:-[A-Z0-9]{4,})+\b")
_PROJECT_ID_RE = re.compile(r"\bproject:proj_[A-Za-z0-9_-]+\b|\bproj_[A-Za-z0-9_-]{8,}\b")
_RECORD_ID_RE = re.compile(r"\brec_[A-Za-z0-9_-]{6,}\b")
_OPERATIONAL_ID_RE = re.compile(
    r"\b(?:prod|run|span|tool|toolu|call|trigger|task|thread|msg)_[A-Za-z0-9-]{8,}\b"
    r"|\btr_dev_[A-Za-z0-9-]{8,}\b"
    r"|\bchatcmpl-[A-Za-z0-9_-]{6,}\b"
    r"|\bC[A-Z0-9]{8,}/p\d{10,}\b"
    r"|\b[CDG][A-Z0-9]{8,}\b"
    r"|\bp\d{10,}\b"
)
_LEGACY_UNQUOTED_TECH_PLACEHOLDER_RE = re.compile(r"(?<!`)\[technical id\](?!`)")
_FILE_TOKEN_RE = re.compile(
    r"(?<!\w)[A-Za-z0-9_.@+-]+\.(?:py|ts|tsx|rs|md|jsonl?|ya?ml|toml|log|sh|sql|html|css|tar|pdf|docx?)(?!\w)"
)
_HASH_WORD_RE = re.compile(r"\b(?:sha256|sha-?256|hash(?:es|ed|ing)?|checksum(?:s)?)\b", flags=re.IGNORECASE)
_PROVENANCE_PHRASE_RE = re.compile(
    r"\b(?:trace link|source inspection|supporting evidence|run artifacts?|exact reports?|files touched|raw html/api error|known-issue pointers?)\b",
    flags=re.IGNORECASE,
)
_WHITESPACE_RE = re.compile(r"\s+")


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _trim_at_word_boundary(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    suffix = "…"
    limit = max(max_chars - len(suffix), 0)
    cut = text[:limit].rstrip()
    boundary = cut.rfind(" ")
    if boundary >= max_chars // 2:
        cut = cut[:boundary].rstrip()
    cut = cut.rstrip(" ,;:-")
    return f"{cut}{suffix}" if cut else suffix[:max_chars]


def _sanitize_visible_text(text: str, *, max_chars: int) -> str:
    """Collapse whitespace and trim to length — NO content redaction. Records are
    written clean by the curator (LLM judgment keeps meaningful names and omits
    secrets/opaque ids), so subject pages render REAL paths/names/links instead of
    useless [path]/[id] placeholders. Redaction here was a regex blacklist that
    made memory less useful, not more."""
    visible = _WHITESPACE_RE.sub(" ", str(text or "")).strip()
    return _trim_at_word_boundary(visible, max_chars)


def _redact_changelog(text: str, *, max_chars: int) -> str:
    """The changelog is an auto-generated AUDIT log of mutations, not user content;
    its events can carry raw SourceRef reprs / opaque ids, so this one path still
    strips them. (Subject pages use the faithful _sanitize_visible_text above.)"""
    visible = re.sub(r"[\r\n]+", " ", str(text or ""))
    visible = _SOURCE_REF_RE.sub(" ", visible)
    visible = _DEBUG_KV_RE.sub(" ", visible)
    visible = _URL_RE.sub("[link]", visible)
    visible = _LEGACY_UNQUOTED_TECH_PLACEHOLDER_RE.sub("technical identifier", visible)
    visible = _LOCAL_PATH_RE.sub("[path]", visible)
    visible = _REPO_PATH_RE.sub("[path]", visible)
    visible = _UUID_RE.sub("[id]", visible)
    visible = _LONG_HEX_RE.sub("[id]", visible)
    visible = _SHORT_COMMIT_RE.sub("[id]", visible)
    visible = _DASHED_ID_RE.sub("[id]", visible)
    visible = _PROJECT_ID_RE.sub("[id]", visible)
    visible = _OPERATIONAL_ID_RE.sub("[id]", visible)
    visible = _HASH_WORD_RE.sub("provenance marker", visible)
    visible = _PROVENANCE_PHRASE_RE.sub("diagnostic detail", visible)
    visible = visible.replace("provenance marker provenance marker", "provenance marker")
    visible = _WHITESPACE_RE.sub(" ", visible).strip()
    return _trim_at_word_boundary(visible, max_chars)


def _safe_log(event: str) -> str:
    return _redact_changelog(event, max_chars=MAX_LOG_CHARS)


def summarize_changelog_text(items: list[str], *, max_items: int = 3) -> str:
    snippets = [
        _redact_changelog(item, max_chars=180)
        for item in items
        if _redact_changelog(item, max_chars=180)
    ][:max_items]
    if not snippets:
        return "details redacted"
    suffix = "" if len(items) <= max_items else f"; +{len(items) - max_items} more"
    return "; ".join(snippets) + suffix


def canonical_kind(kind: str | None) -> str:
    k = (kind or "fact").strip().lower()
    return k if k in CANONICAL_KINDS else LEGACY_KIND_MAP.get(k, "fact")


def _wrap_bullet(text: str, *, max_chars: int) -> str:
    text = _sanitize_visible_text(text, max_chars=max_chars) or "[redacted]"
    lines = textwrap.wrap(
        text,
        width=ARTIFACT_WRAP_WIDTH,
        break_long_words=True,
        break_on_hyphens=True,
    ) or ["[redacted]"]
    return "- " + "\n  ".join(lines)


def _bullet(record: Record, *, max_chars: int = MAX_BULLET_CHARS) -> str:
    return _wrap_bullet(record.text, max_chars=max_chars)


def _display_text(text: str, *, fallback: str) -> str:
    return _sanitize_visible_text(text, max_chars=MAX_TITLE_CHARS) or fallback


def _slug(text: str | None, *, fallback: str) -> str:
    raw = str(text or "").strip()
    base_source = fallback if _PROJECT_ID_RE.fullmatch(raw) else raw
    base = _SLUG_RE.sub("-", base_source).strip(".-_").lower()
    return base[:60].strip(".-_") or fallback


def _collision_slug(text: str | None, *, fallback: str) -> str:
    raw = str(text or "").strip()
    base = _slug(raw, fallback=fallback)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8] if raw else "empty"
    return f"{base}-{digest}"


def _cooccurring_labels(rows: list[Record], labels_by_id: dict[str, list], title: str) -> tuple[str, ...]:
    """The labels that actually co-occur on a dossier's records (excluding the
    subject title itself), most common first, top 6 — the frontmatter `labels`
    for a topic page."""
    counts = Counter(
        (entry["label"] if isinstance(entry, dict) else entry)
        for r in rows
        for entry in labels_by_id.get(r.id, [])
        if (entry["label"] if isinstance(entry, dict) else entry).lower() != title.lower()
    )
    return tuple(label for label, _count in counts.most_common(6))


def _flat_labels(labels_by_id: dict[str, list]) -> dict[str, list[str]]:
    """Flatten typed labels (dict[id, list[dict(label, kind)]]) to plain
    dict[id, list[str]] for synthesis prompts. Tolerates already-flat input."""
    out: dict[str, list[str]] = {}
    for rid, entries in labels_by_id.items():
        out[rid] = [e["label"] if isinstance(e, dict) else e for e in entries]
    return out


def _related_link(label: str, known_subjects: frozenset[str]) -> str:
    if label.lower() in known_subjects:
        return f"- [[{label}]]"
    return f"- {label}"


def _safe_source_label(kind: str) -> str:
    label = re.sub(r"[^A-Za-z0-9_. -]+", " ", str(kind or "")).strip()
    label = _WHITESPACE_RE.sub(" ", label)
    return _trim_at_word_boundary(label, 80) or "unknown"


def source_kind_description(kind: str) -> str:
    if kind == "curator":
        return "generated by the memory curator from chat/session transcripts."
    if kind == "chat_turn":
        return "explicit memory writes from chat/tool calls."
    if kind == "seed":
        return "seeded/imported memory from prior stores."
    if kind == "dreamer":
        return "background/generated reflection receipts; useful as provenance only, not authoritative facts."
    if kind == "consolidate":
        return "records promoted or merged by consolidation."
    return f"{kind} receipts."


def _artifact_record_count(kind: str, content: str) -> int:
    if kind in {"directive", "fact"}:
        return len(re.findall(r"^- ", content, flags=re.MULTILINE))
    return 0


def _record_count_for_artifact(rel: str, kind: str, content: str) -> int | None:
    if rel in {"README.md", "tooling.md"} or rel.startswith("changelog/"):
        return None
    if rel.endswith("/index.md"):
        return None
    fm, body = parse_frontmatter(content)
    if _PAGE_SENTINEL in body:  # two-zone canonical page: count active timeline atoms
        _, _, tl = body.partition(_PAGE_SENTINEL)
        return sum(1 for raw in tl.splitlines() if (ln := _parse_line(raw)) is not None and not ln.superseded)
    if "record_count" in fm:
        value = fm["record_count"]
        return int(value) if value is not None else None
    if kind == "topic":
        match = re.search(r"^- Records?: (\d+)\s*$", body, flags=re.MULTILINE)
        return int(match.group(1)) if match else 0
    return _artifact_record_count(kind, body)


def _artifact_directory(rel: str) -> str:
    parts = Path(rel).parts
    return parts[0] if len(parts) > 1 else "memory"


def _artifact_generated(rel: str, content: str) -> bool:
    # Two-zone canonical pages (file-canonical memory) are NOT generated projections.
    if _PAGE_SENTINEL in content:
        return False
    fm, _ = parse_frontmatter(content)
    if "generated" in fm:
        return bool(fm["generated"])
    marker = "<!-- ntrp-memory: generated=false editable=true -->"
    return marker not in content


def _artifact_editable(rel: str, content: str) -> bool:
    if rel.startswith("changelog/"):
        return False
    if _PAGE_SENTINEL in content:  # canonical two-zone pages are directly editable
        return True
    fm, _ = parse_frontmatter(content)
    if "editable" in fm:
        return bool(fm["editable"])
    return not _artifact_generated(rel, content)


def _readonly_reason(rel: str, kind: str, generated: bool) -> str | None:
    if rel == "AGENTS.md":
        return "Conventions doc — regenerated on load."
    if rel == "health.md":
        return "Self-audit — regenerated on load from the current pages."
    if rel == "facts/index.md":
        return "Generated from DB records; use recall/record tools for facts."
    if rel.startswith("changelog/"):
        return "Generated audit log; append events through memory tools."
    if generated:
        return "Synthesized prose above the timeline — edits are overwritten; change the records below."
    return None


def _artifact_snippet(content: str, query: str | None = None) -> str | None:
    content = strip_frontmatter(content)
    if _PAGE_SENTINEL in content:  # two-zone page: preview the prose, not the timeline dump
        content = content.partition(_PAGE_SENTINEL)[0]
    lines = [_sanitize_visible_text(line, max_chars=MAX_DOSSIER_SNIPPET_CHARS) for line in content.splitlines()]
    lines = [
        line
        for line in lines
        if line and not line.startswith("#") and not line.startswith("_Generated read-only dossier")
    ]
    if query:
        q = query.lower()
        for line in lines:
            if q in line.lower():
                return line
    for line in lines:
        if not line.startswith("---"):
            return line
    return None


def _title_from_content(content: str, fallback: str) -> str:
    content = strip_frontmatter(content)
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip() or fallback
    return fallback


_CHANGELOG_LINE_DATE_RE = re.compile(r"^-\s+\d{4}-\d{2}-(\d{2})T(\d{2}:\d{2})\S*\s*$")


def _compact_changelog_prefix(prefix: str) -> str:
    """Trim a legacy full-ISO line prefix to day + time — the year-month is
    already the file name, and microseconds/offset are noise. No-op if already
    compact or not a dated prefix."""
    m = _CHANGELOG_LINE_DATE_RE.match(prefix)
    return f"- {m.group(1)} {m.group(2)}" if m else prefix


# Going-forward events carry real change text ("Learned: …" / "Remembered: …").
# Legacy lines are normalized on render: maintenance + contentless generics are
# dropped; the old "curator updated N record(s) … transcript:" wrapper is folded
# into a plain "Learned: …".
_CHANGELOG_CURATOR_PREFIX_RE = re.compile(
    r"^curator updated \d+ memory record\(s\) from chat transcript:\s*", flags=re.IGNORECASE
)
_CHANGELOG_DROP_RE = re.compile(
    r"^(?:"
    r"(?:manual\s+)?memory filesystem\b"  # maintenance: rebuild / patch / vN
    r"|curator updated [^:]*\(\d+\s*change\(s\)\)\s*$"  # count-only, no content
    r"|(?:remembered|forgot|added|pinned|unpinned)\b[^:]*$"  # generic verb, no content
    r")",
    flags=re.IGNORECASE,
)


def _normalize_changelog_text(text: str) -> str | None:
    if _CHANGELOG_DROP_RE.match(text):
        return None
    return _CHANGELOG_CURATOR_PREFIX_RE.sub("Learned: ", text).strip() or None
_EVENT_FLAT_RE = re.compile(r"^-\s+(\d{2})\s+(\d{2}:\d{2})\s+—\s+(.*)$")
_EVENT_GROUPED_RE = re.compile(r"^-\s+(\d{2}:\d{2})\s+—\s+(.*)$")
_EVENT_LEGACY_FULL_RE = re.compile(r"^-\s+\d{4}-\d{2}-(\d{2})T(\d{2}:\d{2})\S*\s+—\s+(.*)$")


def _render_changelog_month(content: str, *, year: int, month_num: int, month_label: str) -> str:
    """Group a monthly changelog into readable day sections (## Weekday, Mon D),
    dropping legacy contentless noise. Robust to flat `- DD HH:MM — …`,
    already-grouped `## day` + `- HH:MM — …`, and legacy full-ISO lines."""
    events: list[tuple[str, str, str]] = []  # (day, time, text), file order
    current_day: str | None = None
    for line in content.splitlines():
        if line.startswith("## "):
            m = re.search(r"(\d{1,2})\s*$", line)
            if m:
                current_day = f"{int(m.group(1)):02d}"
            continue
        if not (line.startswith("- ") and " — " in line):
            continue
        flat, legacy, grouped = (
            _EVENT_FLAT_RE.match(line),
            _EVENT_LEGACY_FULL_RE.match(line),
            _EVENT_GROUPED_RE.match(line),
        )
        if flat:
            day, time, text = flat.group(1), flat.group(2), flat.group(3)
        elif legacy:
            day, time, text = legacy.group(1), legacy.group(2), legacy.group(3)
        elif grouped and current_day:
            day, time, text = current_day, grouped.group(1), grouped.group(2)
        else:
            continue
        text = (_safe_log(text) or "").strip()
        text = _normalize_changelog_text(text) if text else None
        if not text:
            continue
        events.append((day, time, text))

    header = _CHANGELOG_HEADER_TEMPLATE.format(month=month_label).rstrip("\n")
    if not events:
        return header + "\n"
    out = [header]
    last_day: str | None = None
    for day, time, text in events:
        if day != last_day:
            try:
                label = datetime(year, month_num, int(day)).strftime("%A, %b ") + str(int(day))
            except ValueError:
                label = f"Day {day}"
            out.extend(["", f"## {label}"])
            last_day = day
        out.append(f"- {time} — {text}")
    return "\n".join(out) + "\n"


def _sanitize_changelog_content(content: str, *, compact_dates: bool = False) -> str:
    # compact_dates only when the content is already routed into a monthly file
    # (the year-month is the filename) — NOT during legacy migration, where the
    # full line date is still needed to route each line to the right month.
    if not content:
        return content
    out: list[str] = []
    for line in content.splitlines():
        if not line.strip():
            out.append("")
            continue
        if line.startswith("- "):
            if " — " in line:
                prefix, payload = line.split(" — ", 1)
                if compact_dates:
                    prefix = _compact_changelog_prefix(prefix)
                out.append(f"{prefix} — {_safe_log(payload) or '[redacted]'}")
            else:
                out.append(f"- {_safe_log(line[2:]) or '[redacted]'}")
        else:
            out.append(_sanitize_visible_text(line, max_chars=MAX_LOG_CHARS))
    sanitized = "\n".join(out) + ("\n" if content.endswith("\n") else "")
    sanitized = sanitized.replace(
        "Markdown is generated from DB mutations and append events; do not edit it as canonical memory.\n- ",
        "Markdown is generated from DB mutations and append events; do not edit it as canonical memory.\n\n- ",
    )
    return sanitized


def _source_kind(record: Record) -> str:
    return str(record.source_ref.kind if record.source_ref is not None else "").lower()


def _source_ref(record: Record) -> str:
    return str(record.source_ref.ref if record.source_ref is not None else "").lower()


def _integration_key(record: Record) -> str | None:
    kind = _source_kind(record).strip().lower()
    if kind in KNOWN_INTEGRATION_SOURCE_KINDS:
        return kind
    if (record.scope_kind or "").strip().lower() != "integration":
        return None
    raw = str(record.scope_key or "").strip()
    if not raw:
        return None
    provider = raw.split(":", 1)[0].strip().lower()
    if provider in KNOWN_INTEGRATION_SOURCE_KINDS:
        return provider
    return _slug(provider, fallback="integration")


def _integration_title(key: str) -> str:
    normalized = _slug(key, fallback="integration")
    if normalized in INTEGRATION_TITLES:
        return INTEGRATION_TITLES[normalized]
    words = [word for word in re.split(r"[-_.\s]+", normalized) if word]
    return " ".join(word.capitalize() for word in words) or "Integration"


def _safe_source_ref_label(ref: str) -> str:
    label = _sanitize_visible_text(ref, max_chars=120)
    label = _LOCAL_PATH_RE.sub("[local path]", label)
    label = _UUID_RE.sub("[id]", label)
    label = _LONG_HEX_RE.sub("[id]", label)
    label = _PROJECT_ID_RE.sub("[id]", label)
    label = _OPERATIONAL_ID_RE.sub("[id]", label)
    return _trim_at_word_boundary(label, 120) or "unknown"


def _reference_snippet(record: Record) -> str:
    text = _sanitize_visible_text(record.text, max_chars=220)
    text = _LOCAL_PATH_RE.sub("[local path]", text)
    text = _UUID_RE.sub("[id]", text)
    text = _LONG_HEX_RE.sub("[id]", text)
    text = _PROJECT_ID_RE.sub("[id]", text)
    text = _OPERATIONAL_ID_RE.sub("[id]", text)
    if record.source_ref is not None:
        ref = _sanitize_visible_text(record.source_ref.ref, max_chars=120)
        ref = _LOCAL_PATH_RE.sub("[local path]", ref)
        ref = _UUID_RE.sub("[id]", ref)
        ref = _LONG_HEX_RE.sub("[id]", ref)
        ref = _PROJECT_ID_RE.sub("[id]", ref)
        ref = _OPERATIONAL_ID_RE.sub("[id]", ref)
        if ref and ref not in text:
            text = f"{text} ({ref})" if text else ref
    return _trim_at_word_boundary(text, 260)


def _is_file_record(record: Record) -> bool:
    kind = _source_kind(record)
    ref = _source_ref(record)
    text = str(record.text or "")
    return (
        any(token in kind for token in ("file", "attachment", "filesystem", "repo", "path"))
        or any(token in ref for token in ("file", ".py", ".ts", ".tsx", ".md", ".json", ".yaml", ".yml"))
        or _FILE_TOKEN_RE.search(text) is not None
        or _REPO_PATH_RE.search(text) is not None
    )


def _is_doc_record(record: Record) -> bool:
    kind = _source_kind(record)
    ref = _source_ref(record)
    text = str(record.text or "")
    return (
        any(token in kind for token in ("doc", "document", "pdf", "web", "url", "notion", "obsidian", "wiki"))
        or any(token in ref for token in (".md", ".pdf", "docs/", "wiki", "notion", "obsidian", "http://", "https://"))
        or re.search(r"\b(?:docs?|documentation|readme|pdf)\b", text, flags=re.IGNORECASE) is not None
    )


@dataclass(frozen=True)
class ArtifactMeta:
    labels: tuple[str, ...] = ()
    source: str | None = None


@dataclass(frozen=True)
class MemoryArtifact:
    path: str
    title: str
    kind: str
    scope_kind: str
    scope_key: str | None
    content: str
    record_count: int | None
    updated_at: str | None
    type: str = "file"
    directory: str = "memory"
    generated: bool = True
    editable: bool = False
    readonly_reason: str | None = None
    snippet: str | None = None
    labels: tuple[str, ...] = ()
    source: str | None = None
    timeline: tuple = ()  # parsed timeline atoms (read_artifact only; () in list view)


class ArtifactMemoryStore:
    def __init__(self, root: Path, *, project_names: dict[str, str] | None = None):
        self.root = root
        self.project_names = project_names or self._load_project_names()
        self._scope_keys_by_rel: dict[str, str] = {}

    def _load_project_names(self) -> dict[str, str]:
        db_path = self.root.parent / "sessions.db"
        if not db_path.exists() or db_path.is_symlink():
            return {}
        try:
            conn = sqlite3.connect(db_path)
            rows = conn.execute(
                "SELECT project_id, name, knowledge_scope FROM projects WHERE archived_at IS NULL"
            ).fetchall()
        except sqlite3.Error:
            return {}
        finally:
            try:
                conn.close()
            except Exception:
                pass
        names: dict[str, str] = {}
        for project_id, name, knowledge_scope in rows:
            if not project_id or not name:
                continue
            display = str(name).strip()
            if not display:
                continue
            names[str(project_id)] = display
            names[f"project:{project_id}"] = display
            if knowledge_scope:
                names[str(knowledge_scope)] = display
        return names

    def _project_title(self, key: str | None) -> str:
        if key and key in self.project_names:
            return self.project_names[key]
        return _display_text(key or "project", fallback="project")

    def _project_rel_for_key(self, key: str, used: set[str]) -> str:
        title = self._project_title(key)
        slug = _slug(title, fallback="project")
        rel = f"projects/{slug}.md"
        if rel in used:
            digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]
            rel = f"projects/{slug}-{digest}.md"
        used.add(rel)
        return rel

    def ensure_dirs(self) -> None:
        self._assert_root_safe()
        self.root.mkdir(parents=True, exist_ok=True)
        self._assert_root_safe()

    def append_event(self, event: str) -> None:
        self.ensure_dirs()
        self._migrate_legacy_changelog()
        now = datetime.now(UTC)
        rel = self._changelog_month_rel(now)
        path = self._safe_path(rel)
        self._ensure_month_changelog(path, now.strftime("%Y-%m"))
        # Year-month is already the file name (changelog/YYYY/YYYY-MM.md), so the
        # line only needs day + time — no redundant full ISO / microseconds / offset.
        self._append_text_no_symlink(path, f"- {now.strftime('%d %H:%M')} — {_safe_log(event) or '[redacted]'}\n")
        self._write_changelog_rollups()

    async def export_from_records(
        self, records: RecordStore, *, limit: int | None = None, llm=None, model: str = ""
    ) -> list[MemoryArtifact]:
        """Regenerate generated browse artifacts from active DB records.

        `limit=None` is intentional: rebuild/export has no silent cap. Markdown is
        an agent/UI read surface; SQLite records remain canonical for writes.

        When `llm` (a completion client) and `model` are provided, the expensive
        prose-synthesis pages are (re)generated: `me.md`, LLM-written entity/project
        dossiers, and `active-work.md`. Without them the export is purely mechanical
        (the cheap per-session/per-mutation sync path) and preserves any existing
        synthesized pages rather than clobbering them with bullet dumps.
        """
        synthesize = llm is not None and bool(model)
        self.ensure_dirs()
        rows = await records.list(limit=limit)
        labels_by_id = await records.labels_for([r.id for r in rows], include_kind=True) if rows else {}
        label_vocab = await records.list_labels()
        self._migrate_legacy_changelog()
        self._clear_generated_artifacts()

        directives: list[Record] = []
        facts: list[Record] = []
        source_records: list[Record] = []

        for r in rows:
            kind = canonical_kind(r.kind)
            if kind == "directive":
                directives.append(r)
            elif kind == "fact":
                facts.append(r)
            else:
                source_records.append(r)

        self._write_readme()
        self._write_tooling()
        self._write_directives(directives)
        self._write_facts_index(facts)
        await self._write_entity_dossiers(rows, labels_by_id, label_vocab, llm=llm, model=model)
        await self._write_project_dossiers(facts, labels_by_id, llm=llm, model=model)
        self._write_references(rows, source_records)
        self._write_context_docs()
        self._write_integration_context(rows)
        if synthesize:
            await self._synthesize_profile(rows, directives, facts, labels_by_id, llm=llm, model=model)
            await self._synthesize_active_work(rows, labels_by_id, llm=llm, model=model)
        self._ensure_changelog()
        self._write_context_links()
        return self.list_artifacts()

    def _clear_generated_artifacts(self) -> None:
        # me.md / active-work.md (root) and per-subject dossier bodies are NOT
        # cleared here: synthesized pages must survive a mechanical sync. The
        # entity/project writers prune their own stale bodies (preserving
        # synthesized ones) via _prune_dossier_dir.
        for rel in ("README.md", "tooling.md", "directives.md", "facts.md", "summaries.md", "sources.md"):
            self._unlink_regular_artifact(rel)
        for dirname in ("facts", "context", "references"):
            directory = self.root / dirname
            self._remove_markdown_tree(directory)
        for dirname in ("sources", "files", "docs", "summaries"):
            self._remove_defunct_dir(dirname)

    def _synthesized_subject(self, rel: str) -> str | None:
        """The subject TITLE of an existing LLM-synthesized page at `rel`, or None
        if the file is absent or not synthesized. Returns the title (not just a
        bool) so a mechanical sync can tell whether a synthesized page belongs to
        the subject about to be written: two distinct labels can slugify to the
        same file (e.g. 'O-1A' and 'O 1A' -> entities/o-1a.md), and a rank-flip
        between runs must not let one subject squat the other's slug."""
        try:
            path = self._safe_path(rel)
            st = path.lstat()
        except (FileNotFoundError, OSError):
            return None
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
            return None
        try:
            fm, _ = parse_frontmatter(self._read_text_no_symlink(path))
        except (FileNotFoundError, OSError):
            return None
        if fm.get("source") != SYNTHESIS_SOURCE:
            return None
        return str(fm.get("title") or "")

    def _prune_dossier_dir(self, dirname: str, keep_rels: set[str]) -> None:
        """Remove every generated dossier .md under `dirname` whose rel is not in
        `keep_rels`. Stale synthesized pages (subject dropped below threshold) are
        pruned too; symlinks are skipped (write-time safety handles those)."""
        directory = self.root / dirname
        try:
            st = directory.lstat()
        except FileNotFoundError:
            return
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
            return
        try:
            children = sorted(directory.iterdir(), key=lambda p: p.name)
        except OSError:
            return
        for child in children:
            try:
                child_st = child.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(child_st.st_mode) or not stat.S_ISREG(child_st.st_mode):
                continue
            if child.suffix != ".md":
                continue
            rel = child.relative_to(self.root).as_posix()
            if rel not in keep_rels and self._within_root(child):
                child.unlink(missing_ok=True)

    def _remove_defunct_dir(self, dirname: str) -> None:
        directory = self.root / dirname
        self._remove_markdown_tree(directory)
        try:
            if directory.is_dir() and not stat.S_ISLNK(directory.lstat().st_mode):
                directory.rmdir()
        except OSError:
            pass

    def _write_readme(self) -> MemoryArtifact:
        body = [
            "# ntrp memory filesystem v3",
            "",
            "This directory is a generated browse surface for ntrp memory.",
            "SQLite `memory.db` records are canonical for recall, mutation, and sync;",
            "Markdown here is regenerated and should be treated as read-only context unless explicitly marked editable.",
            "",
            "## Directory map",
            "",
            "- `directives.md` — generated standing behavior rules.",
            "- `facts/index.md` — DB-backed fact counts and querying guidance; no fact dumps are generated.",
            "- `context/` — generated agent context index, readme, and link map.",
            "- `entities/` — emergent topic pages and triage.",
            "- `projects/` — project topic pages.",
            "- `references/` — evidence, receipt, file, doc, and integration pointers.",
            "- `changelog/` — append-only monthly audit logs and generated rollups.",
            "",
            "## Operating rules",
            "",
            "- Use recall/record tools or the Memory UI to inspect and mutate canonical facts.",
            "- Use artifact browse/read/search tools for dossiers, source context, and audit history.",
            "- Rebuild artifacts after record migrations or repairs to sync this projection.",
        ]
        return self._write("README.md", "Memory artifacts", "source", "global", None, "\n".join(body) + "\n", None)

    def _write_tooling(self) -> MemoryArtifact:
        body = [
            "# Agent memory tooling",
            "",
            "Use database-backed memory tools for facts and atomic records.",
            "These artifacts are generated context surfaces, not canonical write targets.",
            "",
            "## Write path",
            "",
            "- `remember` writes one durable directive, fact, or source record.",
            "- `forget` removes the best matching durable record.",
            "- `memory_patch` edits filesystem projection files only and does not mutate canonical DB records.",
            "- `memory_patch` refuses generated artifacts unless `force_generated` is explicit and approved.",
            "- `memory_rebuild` regenerates artifacts from SQLite records.",
            "",
            "## Read path",
            "",
            "- `recall` queries SQLite records and is the canonical retrieval path for facts.",
            "- `memory_tree`, `memory_read`, and `memory_search` browse generated dossiers/context/source docs.",
            "- Browse `context/` for the lookup guide and exact generated-note link map.",
            "- Browse `entities/` and `projects/` for topic pages built from the records.",
            "- Facts live in the database; `facts/index.md` carries counts, while `references/` carries concise pointers.",
            "- Monthly changelog files are append-only atomic event logs; rollups are regenerated indexes.",
            "",
            "## Non-goals",
            "",
            "No graph export, no full transcript dumps, and no Markdown-as-canonical-write-source.",
        ]
        return self._write("tooling.md", "Agent memory tooling", "source", "global", None, "\n".join(body) + "\n", None)

    def _write_directives(self, rows: list[Record]) -> MemoryArtifact:
        body = ["# Rules", "", "Standing behavior rules. Keep these rare, explicit, and user-approved.", ""]
        if rows:
            body.extend(_bullet(r) for r in sorted(rows, key=lambda r: r.created_at, reverse=True))
        else:
            body.append("_No directives yet._")
        content = "\n".join(body).rstrip() + "\n"
        content = content.replace("Generated read-only dossier", "boilerplate generated-dossier")
        return self._write(
            "directives.md",
            "Directives",
            "directive",
            "global",
            None,
            content,
            len(rows),
        )

    def _write_facts_index(self, rows: list[Record]) -> MemoryArtifact:
        by_scope = Counter((r.scope_kind or "global").strip().lower() or "global" for r in rows)
        body = [
            "# Facts",
            "",
            "Facts are DB-backed. SQLite/RecordStore is canonical for atomic facts, retrieval, and mutation.",
            "This Markdown projection intentionally does not contain fact bullet dumps.",
            "",
            "## Counts",
            "",
        ]
        for scope in ("global", "user", "project"):
            body.append(f"- {scope}: {by_scope.get(scope, 0)} active fact records")
        other = sum(c for k, c in by_scope.items() if k not in {"global", "user", "project"})
        body.append(f"- other: {other} active fact records")
        return self._write("facts/index.md", "Facts", "fact", "global", None, "\n".join(body).rstrip() + "\n", None)

    def _entity_candidates(
        self, rows: list[Record], labels_by_id: dict[str, list]
    ) -> tuple[list[tuple[str, str, list[Record]]], list[tuple[str, int]]]:
        """Group records by entity-typed label, returning (candidates, triage).

        Directives are excluded (global rules, not subject knowledge). Only labels
        with kind='entity' qualify; meta/legacy labels are ignored. Candidates have
        >= MIN_ENTITY_RECORDS and are ranked: most records, then most recent, then
        alphabetical.
        """
        label_groups: dict[str, list[Record]] = defaultdict(list)
        canonical: dict[str, str] = {}
        for record in rows:
            if canonical_kind(record.kind) == "directive":
                continue
            for entry in labels_by_id.get(record.id, []):
                if not isinstance(entry, dict) or entry.get("kind") != "entity":
                    continue
                raw = entry["label"]
                if not raw or not raw.strip():
                    continue
                key = raw.strip().lower()
                canonical.setdefault(key, raw.strip())
                label_groups[key].append(record)

        candidates: list[tuple[str, str, list[Record]]] = []
        triage: list[tuple[str, int]] = []
        for key, group in label_groups.items():
            grouped = list({r.id: r for r in group}.values())
            label = canonical[key]
            if len(grouped) >= MIN_ENTITY_RECORDS:
                candidates.append((label, key, grouped))
            elif len(grouped) >= MIN_TRIAGE_RECORDS:
                triage.append((label, len(grouped)))
        candidates.sort(key=lambda item: item[0].lower())
        candidates.sort(key=lambda item: max((r.last_confirmed_at for r in item[2]), default=""), reverse=True)
        candidates.sort(key=lambda item: len(item[2]), reverse=True)
        return candidates, triage

    async def _write_entity_dossiers(
        self, rows: list[Record], labels_by_id: dict[str, list], label_vocab: list[dict], *, llm=None, model: str = ""
    ) -> None:
        """Build entity dossiers from entity-typed labels only.

        With `llm`+`model`, each dossier body is LLM-synthesized prose (falling
        back to the mechanical bullet brief on synthesis failure). Without them,
        bodies are the mechanical bullet brief, and any existing synthesized page
        is preserved rather than downgraded.
        """
        _ = label_vocab
        candidates, triage = self._entity_candidates(rows, labels_by_id)
        written: list[tuple[str, str, int, str | None]] = []
        used: set[str] = {"entities/index.md", "entities/needs-triage.md"}
        known_subjects = frozenset(label.lower() for label, _key, _grouped in candidates[:MAX_ENTITY_DOSSIERS])
        known_titles = [label for label, _key, _grouped in candidates[:MAX_ENTITY_DOSSIERS]]
        rel_for: list[tuple[str, str, list[Record]]] = []
        for label, _key, grouped in candidates[:MAX_ENTITY_DOSSIERS]:
            rel = f"entities/{_slug(label, fallback='entity')}.md"
            if rel in used:
                rel = f"entities/{_collision_slug(label, fallback='entity')}.md"
            used.add(rel)
            rel_for.append((rel, label, grouped))
        # Prune stale bodies (dropped subjects), preserving valid ones.
        self._prune_dossier_dir("entities", used)
        for rel, label, grouped in rel_for:
            last = max((r.last_confirmed_at for r in grouped), default=None)
            await self._emit_dossier(
                rel,
                label,
                grouped,
                scope_kind="entity",
                scope_key=_slug(label, fallback="entity"),
                labels_by_id=labels_by_id,
                known_subjects=known_subjects,
                known_titles=[t for t in known_titles if t.lower() != label.lower()],
                llm=llm,
                model=model,
            )
            written.append((rel, label, len(grouped), last))
        for label, _key, grouped in candidates[MAX_ENTITY_DOSSIERS:]:
            triage.append((label, len(grouped)))

        index = [
            "# Entities",
            "",
            "What we know about each subject, built from your records.",
            "",
            "## Topics",
            "",
        ]
        if written:
            for _rel, label, count, last in written:
                tail = f"; last updated {last[:10]}" if last else ""
                index.append(f"- [[{label}]] — {count} records{tail}.")
        else:
            index.append("_No topics yet — they appear as subjects gather records._")
        index.extend(["", "See `entities/needs-triage.md` for low-confidence candidates."])
        self._write("entities/index.md", "Entities", "topic", "global", None, "\n".join(index).rstrip() + "\n", None)

        triage_body = [
            "# Entity triage",
            "",
            "Low-confidence labels are summarized here instead of becoming one-file dossiers.",
            "",
        ]
        if triage:
            for label, count in sorted(triage, key=lambda kv: (-kv[1], kv[0].lower()))[:100]:
                triage_body.append(f"- {label}: {count} record{'s' if count != 1 else ''}")
        else:
            triage_body.append("_No low-confidence entity candidates._")
        self._write(
            "entities/needs-triage.md",
            "Entity triage",
            "topic",
            "global",
            None,
            "\n".join(triage_body).rstrip() + "\n",
            None,
        )

    async def _write_project_dossiers(
        self, facts: list[Record], labels_by_id: dict[str, list[str]], *, llm=None, model: str = ""
    ) -> None:
        project_rows: defaultdict[str, list[Record]] = defaultdict(list)
        inbox: list[Record] = []
        for record in facts:
            if (record.scope_kind or "").strip().lower() != "project":
                continue
            if record.scope_key:
                project_rows[record.scope_key].append(record)
            else:
                inbox.append(record)
        used_paths: set[str] = set()
        entries: list[tuple[str, str, str, list[Record]]] = []
        for key in sorted(project_rows, key=lambda k: self._project_title(k).lower()):
            title = self._project_title(key)
            rel = self._project_rel_for_key(key, used_paths)
            entries.append((key, title, rel, project_rows[key]))
        index = [
            "# Projects",
            "",
            "Generated project context dossiers derived from active memory records.",
            "",
            "## Topics",
            "",
        ]
        project_subjects = frozenset(title.lower() for _key, title, _rel, _rows in entries)
        project_titles = [title for _key, title, _rel, _rows in entries]
        if entries:
            for _key, title, _rel, rows in entries:
                last = max((r.last_confirmed_at for r in rows), default=None)
                tail = f"; last updated {last[:10]}" if last else ""
                index.append(f"- [[{title}]] — {len(rows)} records{tail}.")
        else:
            index.append("_No keyed project dossiers yet._")
        index.append(f"- [[Project inbox]] — {len(inbox)} records.")
        keep = {"projects/index.md", "projects/inbox.md", *(rel for _key, _title, rel, _rows in entries)}
        self._prune_dossier_dir("projects", keep)
        self._write("projects/index.md", "Projects", "topic", "global", None, "\n".join(index).rstrip() + "\n", None)
        # Inbox stays mechanical — a low-value unscoped catch-all not worth a call.
        self._write_dossier(
            "projects/inbox.md",
            "Project inbox",
            inbox,
            scope_kind="global",
            scope_key=None,
            labels_by_id=labels_by_id,
            known_subjects=project_subjects,
        )
        for key, title, rel, grouped in entries:
            await self._emit_dossier(
                rel,
                title,
                grouped,
                scope_kind="project",
                scope_key=key,
                labels_by_id=labels_by_id,
                known_subjects=project_subjects,
                known_titles=[t for t in project_titles if t.lower() != title.lower()],
                llm=llm,
                model=model,
            )

    def _project_dossier_titles(self, facts: list[Record]) -> list[str]:
        keys = {
            record.scope_key
            for record in facts
            if (record.scope_kind or "").strip().lower() == "project" and record.scope_key
        }
        return [self._project_title(key) for key in sorted(keys, key=lambda k: self._project_title(k).lower())]

    def _profile_known_titles(
        self,
        rows: list[Record],
        facts: list[Record],
        labels_by_id: dict[str, list],
    ) -> list[str]:
        candidates, _triage = self._entity_candidates(rows, labels_by_id)
        titles = [label for label, _key, _grouped in candidates[:MAX_ENTITY_DOSSIERS]]
        titles.extend(self._project_dossier_titles(facts))
        seen: set[str] = set()
        out: list[str] = []
        for title in titles:
            key = title.strip().lower()
            if key and key not in seen:
                seen.add(key)
                out.append(title)
        return out

    @staticmethod
    def _strip_unknown_profile_wikilinks(text: str, known_titles: list[str]) -> str:
        known = {title.strip().lower() for title in known_titles}

        def repl(match: re.Match) -> str:
            title = match.group(1).strip()
            display = (match.group(2) or title).strip()
            if title.lower() in known:
                return match.group(0)
            return display

        return _WIKILINK_RE.sub(repl, text)

    def _write_dossier(
        self,
        rel: str,
        title: str,
        rows: list[Record],
        *,
        scope_kind: str,
        scope_key: str | None,
        labels_by_id: dict[str, list[str]],
        known_subjects: frozenset[str] = frozenset(),
    ) -> MemoryArtifact:
        sorted_rows = sorted(rows, key=lambda r: r.last_confirmed_at, reverse=True)
        display_title = _display_text(title, fallback="Dossier")
        body = [f"# {display_title}", ""]

        if not sorted_rows:
            body.extend(["_No active records currently match this dossier._", ""])
            return self._write(rel, title, "topic", scope_kind, scope_key, "\n".join(body).rstrip() + "\n", 0)

        last = max((r.last_confirmed_at for r in sorted_rows), default="")
        last_date = last[:10] if last else "unknown"
        body.append(
            f"_Compiled subject brief · {len(sorted_rows)} records · "
            f"last updated {last_date} · generated, read-only_"
        )

        # "What we know": non-directive records, recency-sorted, deduped (drop a
        # bullet whose visible text is a case-insensitive substring of an
        # already-emitted longer one), top ~15.
        known: list[str] = []
        for r in sorted_rows:
            if canonical_kind(r.kind) == "directive":
                continue
            visible = _sanitize_visible_text(r.text, max_chars=260)
            if not visible:
                continue
            known.append(visible)
            if len(known) >= 15:
                break
        if known:
            body.extend(["", "## What we know", "", *(_wrap_bullet(text, max_chars=260) for text in known)])

        questions = [
            _sanitize_visible_text(r.text, max_chars=220)
            for r in sorted_rows
            if "?" in str(r.text or "")
        ][:4]
        if questions:
            body.extend(["", "## Open questions", "", *(f"- {q}" for q in questions if q)])

        label_counts = Counter(
            entry["label"] if isinstance(entry, dict) else entry
            for r in rows
            for entry in labels_by_id.get(r.id, [])
            if (entry["label"] if isinstance(entry, dict) else entry).lower() != display_title.lower()
        )
        related = [label for label, _count in label_counts.most_common(6)]
        if related:
            body.extend(["", "## Related", "", *(_related_link(label, known_subjects) for label in related)])

        return self._write(
            rel,
            title,
            "topic",
            scope_kind,
            scope_key,
            "\n".join(body).rstrip() + "\n",
            len(rows),
            meta=ArtifactMeta(labels=tuple(label_counts), source="consolidate"),
        )

    # --- LLM synthesis -----------------------------------------------------

    async def _synthesize(self, llm, model: str, system: str, user: str) -> str | None:
        """One completion call (same client/contract as the curator). Returns the
        stripped text, or None on any error / empty completion so callers degrade
        to the mechanical projection instead of persisting garbage."""
        try:
            resp = await llm.completion(
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                model=model,
                langfuse_name="memory.synthesize",
            )
        except Exception:
            _logger.warning("memory synthesis LLM call failed", exc_info=True)
            return None
        content = resp.choices[0].message.content if resp.choices else None
        return content.strip() if content and content.strip() else None

    @staticmethod
    def _validate_provenance(text: str, allowed: set[str]) -> bool:
        """Every (record:XXXXXXXX) the model cited must be an id we actually
        handed it — a single fabricated citation rejects the page (we fall back to
        the mechanical brief rather than persist an unverifiable claim)."""
        return prompts_synthesis.cited_ids(text).issubset({a[:8].lower() for a in allowed})

    async def _emit_dossier(
        self,
        rel: str,
        title: str,
        rows: list[Record],
        *,
        scope_kind: str,
        scope_key: str | None,
        labels_by_id: dict[str, list],
        known_subjects: frozenset[str],
        known_titles: list[str],
        llm=None,
        model: str = "",
    ) -> None:
        """Write one dossier body. LLM path: synthesized prose (verified
        provenance) with mechanical fallback. Mechanical path: bullet brief, but
        an existing synthesized page is preserved (not downgraded)."""
        if llm is not None and model:
            body = await self._synthesize_dossier_body(
                title, rows, known_titles, labels_by_id, llm=llm, model=model
            )
            if body is not None:
                self._write(
                    rel, title, "topic", scope_kind, scope_key, body,
                    len(rows),
                    meta=ArtifactMeta(labels=_cooccurring_labels(rows, labels_by_id, title), source=SYNTHESIS_SOURCE),
                )
                return
            # fall through to mechanical brief on synthesis failure
        elif (existing := self._synthesized_subject(rel)) is not None and existing.strip().lower() == title.strip().lower():
            # Preserve a synthesized page ONLY when it belongs to THIS subject.
            # On a slug-collision rank-flip the file holds a different subject's
            # prose, so fall through and overwrite it with this subject's brief
            # rather than skip (which would strand the current subject's content).
            return
        self._write_dossier(
            rel, title, rows, scope_kind=scope_kind, scope_key=scope_key,
            labels_by_id=labels_by_id, known_subjects=known_subjects,
        )

    async def _synthesize_dossier_body(
        self, title: str, rows: list[Record], known_titles: list[str],
        labels_by_id: dict[str, list], *, llm, model: str,
    ) -> str | None:
        flat = _flat_labels(labels_by_id)
        ordered = sorted(rows, key=lambda r: r.last_confirmed_at, reverse=True)
        user = prompts_synthesis.dossier_user_message(title, ordered, known_titles, flat)
        out = await self._synthesize(llm, model, prompts_synthesis.DOSSIER_SYSTEM, user)
        if not out or out.strip() == prompts_synthesis.INSUFFICIENT_DOSSIER:
            return None
        if not self._validate_provenance(out, {r.id for r in ordered}):
            _logger.warning("dossier synthesis cited an unknown record id (%s); using mechanical brief", title)
            return None
        return out.rstrip() + "\n"

    async def _synthesize_profile(
        self, rows: list[Record], directives: list[Record], facts: list[Record],
        labels_by_id: dict[str, list], *, llm, model: str,
    ) -> None:
        """me.md — a prose self-page from directives + user-scoped facts + pins."""
        seen: set[str] = set()
        selected: list[Record] = []
        for r in [
            *directives,
            *(f for f in facts if (f.scope_kind or "").strip().lower() in ("user", "global", "")),
            *(r for r in rows if r.pinned and canonical_kind(r.kind) != "source"),
        ]:
            if r.id not in seen:
                seen.add(r.id)
                selected.append(r)
        if not selected:
            return
        selected.sort(key=lambda r: (r.pinned, r.last_confirmed_at), reverse=True)
        selected = selected[:PROFILE_RECORD_CAP]
        known_titles = self._profile_known_titles(rows, facts, labels_by_id)
        user = prompts_synthesis.profile_user_message(
            selected,
            _flat_labels(labels_by_id),
            known_subjects=known_titles,
        )
        out = await self._synthesize(llm, model, prompts_synthesis.PROFILE_SYSTEM, user)
        if not out or not self._validate_provenance(out, {r.id for r in selected}):
            if out:
                _logger.warning("profile synthesis cited an unknown record id; skipping me.md")
            return
        out = self._strip_unknown_profile_wikilinks(out, known_titles)
        self._write(
            "me.md", "Profile", "topic", "user", None, out.rstrip() + "\n",
            len(selected), meta=ArtifactMeta(source=SYNTHESIS_SOURCE),
        )

    async def _synthesize_active_work(
        self, rows: list[Record], labels_by_id: dict[str, list], *, llm, model: str,
    ) -> None:
        """active-work.md — current threads from recent + project-scoped records."""
        cutoff = (datetime.now(UTC) - timedelta(days=ACTIVE_WORK_RECENT_DAYS)).isoformat()
        recent = [r for r in rows if canonical_kind(r.kind) != "source" and (r.last_confirmed_at or "") >= cutoff]
        project = [r for r in rows if (r.scope_kind or "").strip().lower() == "project"]
        if not recent and not project:
            return
        user = prompts_synthesis.active_work_user_message(recent, project, _flat_labels(labels_by_id))
        out = await self._synthesize(llm, model, prompts_synthesis.ACTIVE_WORK_SYSTEM, user)
        if not out:
            return
        allowed = {r.id for r in [*recent, *project]}
        if out.strip() != prompts_synthesis.NO_ACTIVE_WORK and not self._validate_provenance(out, allowed):
            _logger.warning("active-work synthesis cited an unknown record id; skipping active-work.md")
            return
        self._write(
            "active-work.md", "Active work", "topic", "global", None, out.rstrip() + "\n",
            len({*allowed}), meta=ArtifactMeta(source=SYNTHESIS_SOURCE),
        )

    def _write_context_docs(self) -> None:
        index = [
            "# Context",
            "",
            "Generated context map for agents and memory tools.",
            "SQLite records remain canonical; these files are read-only.",
            "",
            "## Primary surfaces",
            "",
            "- `context/README.md` — how to use this memory artifact tree.",
            "- `context/links.md` — exact `memory_read` paths for generated notes.",
            "- `me.md` — synthesized profile when a model-backed rebuild is available.",
            "- `active-work.md` — synthesized current-work summary when a model-backed rebuild is available.",
            "- `entities/index.md` — generated entity topic index.",
            "- `projects/index.md` — generated project topic index.",
            "- `references/index.md` — generated evidence and pointer index.",
            "- `changelog/index.md` — generated memory mutation rollup.",
            "- `context/integrations/index.md` — generated integration overview pages.",
            "",
            "## Lookup flow",
            "",
            "1. Read `me.md` and `active-work.md` for the hot working set.",
            "2. Read `context/links.md` when you need exact paths or titles.",
            "3. Search `entities/`, `projects/`, and `context/integrations/` for topic detail.",
            "4. Use `references/` and `changelog/` when provenance or mutation history matters.",
        ]
        self._write(
            "context/index.md",
            "Context",
            "topic",
            "global",
            None,
            "\n".join(index).rstrip() + "\n",
            None,
        )

        readme = [
            "# Context README",
            "",
            "This directory is the agent-facing entry point for generated memory artifacts.",
            "It follows the same useful pattern as Dex's `.agent/context/`: small navigational files,",
            "then linked topic pages that tools can browse, read, and search.",
            "",
            "## Contract",
            "",
            "- SQLite `memory.db` records are canonical for writes and retrieval.",
            "- Markdown here is a generated read surface for agents and UI browsing.",
            "- Agents should use `memory_tree`, `memory_read`, and `memory_search` against these paths.",
            "- Do not patch generated files to change memory. Update canonical records instead.",
            "",
            "## What To Read",
            "",
            "- Start at `context/index.md` for navigation.",
            "- Read `context/links.md` for exact tool-readable paths.",
            "- Read `me.md` for stable profile and working-style context.",
            "- Read `active-work.md` for current project state.",
            "- Read `context/integrations/index.md` for source-specific overviews.",
            "- Search `entities/` and `projects/` for topic dossiers.",
            "- Read `references/` for raw-ish provenance pointers.",
            "",
            "## Non-Goals",
            "",
            "- No separate graph, lens, facet, or CRM-style type system is implied here.",
            "- No generated skill proposals live here.",
            "- No compatibility folders such as `sources/`, `files/`, or `docs/` are generated.",
        ]
        self._write(
            "context/README.md",
            "Context README",
            "topic",
            "global",
            None,
            "\n".join(readme).rstrip() + "\n",
            None,
        )

    def _write_context_links(self) -> None:
        artifacts = [a for a in self.list_artifacts() if a.path != "context/links.md"]

        def line(artifact: MemoryArtifact) -> str:
            count = f" — {artifact.record_count} records" if artifact.record_count is not None else ""
            return f'- `memory_read(path="{artifact.path}")` — {artifact.title}{count}'

        def section(title: str, paths: list[str]) -> list[str]:
            by_path = {a.path: a for a in artifacts}
            lines = [f"## {title}", ""]
            selected = [by_path[path] for path in paths if path in by_path]
            if not selected:
                lines.append("_No generated notes yet._")
            else:
                lines.extend(line(artifact) for artifact in selected)
            lines.append("")
            return lines

        context = sorted(
            (a for a in artifacts if a.path.startswith("context/") and a.path not in {"context/index.md", "context/README.md"}),
            key=lambda a: a.path,
        )
        facts = sorted((a for a in artifacts if a.path.startswith("facts/")), key=lambda a: a.path)
        entities = sorted((a for a in artifacts if a.path.startswith("entities/")), key=lambda a: a.path)
        projects = sorted((a for a in artifacts if a.path.startswith("projects/")), key=lambda a: a.path)
        references = sorted((a for a in artifacts if a.path.startswith("references/")), key=lambda a: a.path)
        changelog = sorted((a for a in artifacts if a.path.startswith("changelog/")), key=lambda a: a.path)
        body = [
            "# Context Links",
            "",
            "Exact generated-note addresses for agents and memory tools.",
            "SQLite records remain canonical; these links are regenerated from the artifact tree.",
            "Use `memory_search` when the title/path below is not enough.",
            "",
        ]
        body.extend(
            section(
                "Hot Entries",
                ["me.md", "active-work.md", "context/index.md", "context/README.md", "tooling.md", "directives.md"],
            )
        )
        body.insert(len(body) - 1, '- `memory_read(path="context/links.md")` — Context links')
        for title, rows in (
            ("Context Pages", context),
            ("Fact Pages", facts),
            ("Entity Pages", entities),
            ("Project Pages", projects),
            ("Reference Pages", references),
            ("Audit Pages", changelog),
        ):
            body.extend([f"## {title}", ""])
            if rows:
                body.extend(line(artifact) for artifact in rows)
            else:
                body.append("_No generated notes yet._")
            body.append("")

        self._write(
            "context/links.md",
            "Context links",
            "topic",
            "global",
            None,
            "\n".join(body).rstrip() + "\n",
            None,
        )

    def _write_integration_context(self, rows: list[Record]) -> None:
        grouped: defaultdict[str, list[Record]] = defaultdict(list)
        for record in rows:
            key = _integration_key(record)
            if key:
                grouped[key].append(record)

        entries: list[tuple[str, str, int, str | None]] = []
        for key in sorted(grouped, key=lambda k: (_integration_title(k).lower(), k)):
            records = sorted(grouped[key], key=lambda r: (r.last_confirmed_at, r.created_at, r.id), reverse=True)
            title = _integration_title(key)
            rel = f"context/integrations/{_slug(key, fallback='integration')}.md"
            self._write_integration_page(rel, title, key, records)
            entries.append((key, title, len(records), max((r.last_confirmed_at for r in records), default=None)))

        index = [
            "# Integrations",
            "",
            "Generated from flat records, scopes, and source refs; this is not canonical integration config.",
            "",
            "## Pages",
            "",
        ]
        if entries:
            for _key, title, count, last in entries:
                suffix = f"; last updated {last[:10]}" if last else ""
                index.append(f"- [[{title}]] — {count} records{suffix}.")
        else:
            index.append("_No integration records detected yet._")
        self._write(
            "context/integrations/index.md",
            "Integrations",
            "topic",
            "global",
            None,
            "\n".join(index).rstrip() + "\n",
            None,
        )

    def _write_integration_page(self, rel: str, title: str, key: str, rows: list[Record]) -> None:
        last = max((r.last_confirmed_at for r in rows), default=None)
        last_date = last[:10] if last else "unknown"
        body = [
            f"# {title}",
            "",
            "## What this page is",
            "",
            f"Generated from {len(rows)} flat memory records whose scope or source refs identify {title}.",
            f"Last updated {last_date}. This is not canonical integration config.",
            "",
            "## Recent records",
            "",
        ]
        snippets = [_reference_snippet(record) for record in rows[:10]]
        snippets = [snippet for snippet in snippets if snippet]
        body.extend(f"- {snippet}" for snippet in snippets)
        if not snippets:
            body.append("_No visible record snippets._")

        receipt_counts: Counter[tuple[str, str]] = Counter()
        for record in rows:
            if record.source_ref is None:
                receipt_counts[("scope", "integration")] += 1
                continue
            kind = _safe_source_label(record.source_ref.kind)
            ref = _safe_source_ref_label(record.source_ref.ref)
            receipt_counts[(kind, ref)] += 1
        body.extend(["", "## Source receipts", ""])
        for (kind, ref), count in sorted(receipt_counts.items(), key=lambda kv: (-kv[1], kv[0][0], kv[0][1]))[:10]:
            body.append(f"- **{kind}** · {ref} — {count} records")
        if not receipt_counts:
            body.append("_No source receipts._")

        self._write(
            rel,
            title,
            "topic",
            "integration",
            key,
            "\n".join(body).rstrip() + "\n",
            len(rows),
            meta=ArtifactMeta(source="consolidate"),
        )

    def _write_records(
        self, rel: str, title: str, kind: str, rows: list[Record], *, intro: str, scope_key: str | None = None
    ) -> MemoryArtifact:
        body = [f"# {title}", "", intro, ""]
        if rows:
            body.extend(
                _bullet(r)
                for r in sorted(rows, key=lambda r: (r.scope_kind or "", r.scope_key or "", r.created_at), reverse=True)
            )
        else:
            body.append(f"_No {kind} records yet._")
        return self._write(rel, title, kind, "global", scope_key, "\n".join(body).rstrip() + "\n", len(rows))

    def _write_references(self, rows: list[Record], source_records: list[Record]) -> None:
        refs = [r.source_ref for r in rows if r.source_ref is not None]
        by_kind = Counter(ref.kind for ref in refs)
        file_rows = [r for r in rows if _is_file_record(r)]
        doc_rows = [r for r in rows if _is_doc_record(r)]
        body = [
            "# References",
            "",
            "Evidence, receipts, files, docs, and integration pointers backing memory.",
            "SQLite records remain canonical; this page is a compact browse index, not a fact dump.",
            "",
        ]
        body.append("## Source types")
        body.append("")
        if by_kind:
            for kind, count in sorted(by_kind.items(), key=lambda kv: (-kv[1], kv[0])):
                safe_kind = _safe_source_label(kind)
                body.append(f"- **{safe_kind}** — {count} records; {source_kind_description(safe_kind)}")
        else:
            body.append("_No source receipts yet._")
        body.extend(["", "## Buckets", ""])
        body.append(f"- files/repos: {len(file_rows)} records")
        body.append(f"- docs/web: {len(doc_rows)} records")
        body.append(f"- explicit source records: {len(source_records)} records")
        recent = self._reference_examples(file_rows, doc_rows, source_records)
        if recent:
            body.extend(["", "## Recent pointers", "", *recent])
        if source_records:
            body.extend(["", f"Explicit source records are in `references/records.md` ({len(source_records)} records)."])
        self._write("references/index.md", "References", "source", "global", None, "\n".join(body).rstrip() + "\n", None)
        self._write_records(
            "references/records.md",
            "Explicit source records",
            "source",
            source_records,
            intro="Records whose canonical kind is `source`; use these as receipts, not facts.",
        )

    def _reference_examples(
        self,
        file_rows: list[Record],
        doc_rows: list[Record],
        source_records: list[Record],
        *,
        limit: int = 10,
    ) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        candidates = sorted(
            [*file_rows, *doc_rows, *source_records],
            key=lambda r: r.last_confirmed_at,
            reverse=True,
        )
        for record in candidates:
            if record.id in seen:
                continue
            seen.add(record.id)
            snippet = _reference_snippet(record)
            if not snippet:
                continue
            scope = record.scope_kind or "global"
            kind = _safe_source_label(record.source_ref.kind) if record.source_ref is not None else canonical_kind(record.kind)
            out.append(f"- **{kind}** · {scope}: {snippet}")
            if len(out) >= limit:
                break
        return out

    def _ensure_changelog(self) -> None:
        self._migrate_legacy_changelog()
        if not self._monthly_changelog_paths():
            now = datetime.now(UTC)
            self._ensure_month_changelog(self._safe_path(self._changelog_month_rel(now)), now.strftime("%Y-%m"))
        self._write_changelog_rollups()

    def _changelog_month_rel(self, at: datetime) -> str:
        return f"changelog/{at:%Y}/{at:%Y-%m}.md"

    def _ensure_month_changelog(self, path: Path, month: str) -> None:
        if path.exists():
            st = path.lstat()
            if not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode):
                raise FileNotFoundError(path.name)
            self._sanitize_changelog_file(path, ensure_trailing_newline=True)
            return
        self._write_text_no_symlink(path, _CHANGELOG_HEADER_TEMPLATE.format(month=month))

    def _migrate_legacy_changelog(self) -> None:
        path = self.root / "changelog.md"
        if not path.exists() and not path.is_symlink():
            return
        try:
            st = path.lstat()
        except FileNotFoundError:
            return
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
            raise FileNotFoundError("changelog.md")
        content = self._read_text_no_symlink(path)
        sanitized = _sanitize_changelog_content(content)
        fallback = datetime.now(UTC)
        for line in sanitized.splitlines():
            if not line.startswith("- "):
                continue
            match = _LEGACY_CHANGELOG_RE.match(line)
            year = match.group(1) if match else fallback.strftime("%Y")
            month = f"{year}-{match.group(2)}" if match else fallback.strftime("%Y-%m")
            target = self._safe_path(f"changelog/{year}/{month}.md")
            self._ensure_month_changelog(target, month)
            existing = self._read_text_no_symlink(target)
            if line not in existing.splitlines():
                if existing and not existing.endswith("\n"):
                    self._append_text_no_symlink(target, "\n")
                self._append_text_no_symlink(target, f"{line}\n")
        path.unlink()

    def _monthly_changelog_paths(self) -> list[Path]:
        changelog_dir = self.root / "changelog"
        if not changelog_dir.exists() or changelog_dir.is_symlink() or not changelog_dir.is_dir():
            return []
        out: list[Path] = []
        for path in self._iter_artifact_files(changelog_only=True):
            rel = path.relative_to(self.root).as_posix()
            if _CHANGELOG_MONTH_RE.match(rel):
                out.append(path)
        return sorted(out, key=lambda p: p.relative_to(self.root).as_posix())

    def _write_changelog_rollups(self) -> None:
        years: defaultdict[str, dict[str, list[str]]] = defaultdict(dict)
        for path in self._monthly_changelog_paths():
            rel = path.relative_to(self.root).as_posix()
            match = _CHANGELOG_MONTH_RE.match(rel)
            if not match:
                continue
            year, month = match.groups()
            self._sanitize_changelog_file(path, ensure_trailing_newline=True)
            lines = [line for line in self._read_text_no_symlink(path).splitlines() if line.startswith("- ")]
            years[year][month] = lines

        index = [
            "# Changelog",
            "",
            "Memory mutation history.",
            "Monthly files are atomic append logs; yearly and root files are compact rollups only.",
            "",
            "## Years",
            "",
        ]
        if years:
            for year in sorted(years, reverse=True):
                year_lines = [line for month in years[year].values() for line in month]
                event_count = len(year_lines)
                month_count = len(years[year])
                index.append(
                    f"- `changelog/{year}.md` — {event_count} events across "
                    f"{month_count} month{'s' if month_count != 1 else ''}."
                )
                self._write_year_changelog(year, years[year])
        else:
            index.append("_No changelog events yet._")
        self._write("changelog/index.md", "Changelog", "changelog", "global", None, "\n".join(index).rstrip() + "\n", 0)

    def _write_year_changelog(self, year: str, months: dict[str, list[str]]) -> None:
        body = [
            f"# Changelog {year}",
            "",
            "Yearly rollup. Atomic timestamped events live in monthly files.",
            "",
            "## Months",
            "",
        ]
        for month in sorted(months, reverse=True):
            count = len(months[month])
            body.append(f"- `changelog/{year}/{month}.md` — {count} event{'s' if count != 1 else ''}.")
        self._write(
            f"changelog/{year}.md", f"Changelog {year}", "changelog", "global", None, "\n".join(body).rstrip() + "\n", 0
        )

    def _write(
        self,
        rel: str,
        title: str,
        kind: str,
        scope_kind: str,
        scope_key: str | None,
        content: str,
        count: int | None,
        *,
        meta: ArtifactMeta = ArtifactMeta(),
    ) -> MemoryArtifact:
        if not self._allowed_artifact_rel(rel):
            raise FileNotFoundError(rel)
        self.ensure_dirs()
        path = self._safe_path(rel)
        if path.is_symlink():
            raise FileNotFoundError(rel)
        body = strip_frontmatter(content)
        generated = _artifact_generated(rel, body)
        editable = _artifact_editable(rel, body)
        frontmatter = dump_frontmatter({
            "kind": kind,
            "title": title,
            "scope": {"kind": scope_kind, "key": scope_key},
            "labels": list(meta.labels),
            "source": meta.source,
            "record_count": count,
            "generated": generated,
            "editable": editable,
            "updated": QuotedStr(datetime.now(UTC).isoformat()),
        })
        self._write_text_no_symlink(path, frontmatter + body)
        if scope_key:
            self._scope_keys_by_rel[rel] = scope_key
        st = path.lstat()
        if not stat.S_ISREG(st.st_mode):
            raise FileNotFoundError(rel)
        return MemoryArtifact(
            path=rel,
            title=title,
            kind=kind,
            scope_kind=scope_kind,
            scope_key=scope_key,
            content=body,
            record_count=count,
            updated_at=datetime.fromtimestamp(st.st_mtime, UTC).isoformat(),
            type="file",
            directory=_artifact_directory(rel),
            generated=generated,
            editable=editable,
            readonly_reason=_readonly_reason(rel, kind, generated),
            snippet=_artifact_snippet(body),
            labels=meta.labels,
            source=meta.source,
        )

    def list_artifacts(self, *, kind: str | None = None, q: str | None = None) -> list[MemoryArtifact]:
        self.ensure_dirs()
        query = (q or "").strip().lower()
        artifacts: list[MemoryArtifact] = []
        for path in self._iter_artifact_files():
            rel = path.relative_to(self.root).as_posix()
            try:
                st = path.lstat()
                content = self._read_text_no_symlink(path)
            except FileNotFoundError:
                continue
            fm, _ = parse_frontmatter(content)
            artifact_kind, title, scope_kind, scope_key = self._artifact_meta(rel, content)
            if kind and artifact_kind != kind:
                continue
            snippet = _artifact_snippet(content, query if query else None)
            haystack = " ".join([rel, title, artifact_kind, _artifact_directory(rel), snippet or "", content]).lower()
            if query and query not in haystack:
                continue
            generated = _artifact_generated(rel, content)
            editable = _artifact_editable(rel, content)
            artifacts.append(
                MemoryArtifact(
                    path=rel,
                    title=title,
                    kind=artifact_kind,
                    scope_kind=scope_kind,
                    scope_key=scope_key,
                    content="",
                    record_count=_record_count_for_artifact(rel, artifact_kind, content),
                    updated_at=datetime.fromtimestamp(st.st_mtime, UTC).isoformat(),
                    type="file",
                    directory=_artifact_directory(rel),
                    generated=generated,
                    editable=editable,
                    readonly_reason=_readonly_reason(rel, artifact_kind, generated),
                    snippet=snippet,
                    labels=tuple(fm.get("labels") or ()),
                    source=fm.get("source"),
                )
            )
        return sorted(artifacts, key=lambda a: self._artifact_sort_key(a.path))

    def read_artifact(self, rel: str) -> MemoryArtifact:
        safe = Path(rel)
        if safe.is_absolute() or ".." in safe.parts:
            raise FileNotFoundError(rel)
        rel_posix = safe.as_posix()
        if not self._allowed_artifact_rel(rel_posix):
            raise FileNotFoundError(rel)
        path = self._safe_path(rel_posix)
        try:
            st = path.lstat()
        except FileNotFoundError as exc:
            raise FileNotFoundError(rel) from exc
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
            raise FileNotFoundError(rel)
        if _CHANGELOG_MONTH_RE.match(rel_posix):
            self._sanitize_changelog_file(path)
            st = path.lstat()
        content = self._read_text_no_symlink(path)
        fm, body = parse_frontmatter(content)
        # Two-zone pages: serve the synthesized PROSE zone (the wiki view) as the
        # body, and surface the timeline atoms separately so the client can show
        # them as secondary/collapsed evidence. The timeline stays canonical on disk.
        timeline: tuple = ()
        if _PAGE_SENTINEL in body:
            prose, _, timeline_text = body.partition(_PAGE_SENTINEL)
            timeline = tuple(ln for ln in (_parse_line(r) for r in timeline_text.splitlines()) if ln is not None)
            body = prose.strip() or "_No synthesized summary yet — synthesis pass pending._"
            # Drop the synthesizer's own leading `# Title` h1 (the chrome shows the title) — never a `## Section`.
            body = re.sub(r"^\s*#[^#][^\n]*\n+", "", body, count=1).lstrip("\n")
        kind, title, scope_kind, scope_key = self._artifact_meta(rel_posix, content)
        generated = _artifact_generated(rel_posix, content)
        editable = _artifact_editable(rel_posix, content)
        return MemoryArtifact(
            path=rel_posix,
            title=title,
            kind=kind,
            scope_kind=scope_kind,
            scope_key=scope_key,
            content=body,
            record_count=_record_count_for_artifact(rel_posix, kind, content),
            updated_at=datetime.fromtimestamp(st.st_mtime, UTC).isoformat(),
            type="file",
            directory=_artifact_directory(rel_posix),
            generated=generated,
            editable=editable,
            readonly_reason=_readonly_reason(rel_posix, kind, generated),
            snippet=_artifact_snippet(content),
            labels=tuple(fm.get("labels") or ()),
            source=fm.get("source"),
            timeline=timeline,
        )

    def _artifact_meta(self, rel: str, content: str) -> tuple[str, str, str, str | None]:
        fm, _ = parse_frontmatter(content)
        if fm.get("kind") and fm.get("title") and isinstance(fm.get("scope"), dict):
            scope = fm["scope"]
            scope_key = scope.get("key")
            if scope_key is not None:
                self._scope_keys_by_rel[rel] = scope_key
            return str(fm["kind"]), str(fm["title"]), str(scope.get("kind") or "global"), scope_key
        if rel in ROOT_ARTIFACTS:
            kind, title = ROOT_ARTIFACTS[rel]
            return kind, _title_from_content(content, title), "global", None
        parts = Path(rel).parts
        if not parts:
            raise FileNotFoundError(rel)
        dirname = parts[0]
        kind = ARTIFACT_DIR_KINDS.get(dirname)
        if kind is None:
            raise FileNotFoundError(rel)
        fallback = Path(rel).stem.replace("-", " ").replace("_", " ").title()
        title = _title_from_content(content, fallback)
        name = Path(rel).name
        # topics/ unifies entities + projects: a page is a project (scope "project") when
        # its frontmatter carries a scope_key, otherwise an emergent subject (scope "entity").
        if dirname == "topics" and name not in {"index.md", "needs-triage.md"}:
            fm, _ = parse_frontmatter(content)
            sk = fm.get("scope_key")
            return (kind, title, "project", str(sk)) if sk else (kind, title, "entity", Path(rel).stem)
        if dirname == "entities" and name not in {"index.md", "needs-triage.md"}:
            return kind, title, "entity", Path(rel).stem
        if dirname == "projects" and name not in {"index.md", "inbox.md"}:
            return kind, title, "project", self._scope_key_for_project_artifact(rel, title)
        return kind, title, "global", None

    def _scope_key_for_project_artifact(self, rel: str, title: str) -> str | None:
        if rel in self._scope_keys_by_rel:
            return self._scope_keys_by_rel[rel]
        stem = Path(rel).stem
        matches = [
            key for key, name in self.project_names.items() if _slug(name, fallback="project") == stem or name == title
        ]
        if matches:
            matches.sort(key=lambda key: (0 if key.startswith("project:") else 1, len(key), key))
            return matches[0]
        return stem

    def _artifact_sort_key(self, rel: str) -> tuple[int, int, str]:
        if rel in ROOT_ARTIFACTS:
            return (0, list(ROOT_ARTIFACTS).index(rel), rel)
        parts = Path(rel).parts
        dirname = parts[0] if parts else ""
        return (1, ARTIFACT_DIR_ORDER.get(dirname, 99), rel)

    def _allowed_artifact_rel(self, rel: str) -> bool:
        safe = Path(rel)
        if safe.is_absolute() or ".." in safe.parts:
            return False
        parts = safe.parts
        if not parts or any(part in ("", ".") or part.startswith(".") for part in parts):
            return False
        if safe.suffix != ".md":
            return False
        if len(parts) == 1:
            return rel in ROOT_ARTIFACTS
        return parts[0] in ARTIFACT_DIR_KINDS

    def _iter_artifact_files(self, *, changelog_only: bool = False) -> list[Path]:
        out: list[Path] = []
        root_files = () if changelog_only else ROOT_ARTIFACTS
        for rel in root_files:
            path = self.root / rel
            try:
                st = path.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISREG(st.st_mode) and not stat.S_ISLNK(st.st_mode):
                out.append(path)
        dirnames = ("changelog",) if changelog_only else tuple(ARTIFACT_DIR_KINDS)
        for dirname in dirnames:
            directory = self.root / dirname
            out.extend(self._walk_markdown_files(directory))
        return sorted(out, key=lambda p: p.relative_to(self.root).as_posix())

    def _walk_markdown_files(self, directory: Path) -> list[Path]:
        try:
            st = directory.lstat()
        except FileNotFoundError:
            return []
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
            return []
        out: list[Path] = []
        try:
            children = sorted(directory.iterdir(), key=lambda p: p.name)
        except OSError:
            return []
        for child in children:
            try:
                child_st = child.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(child_st.st_mode):
                continue
            if stat.S_ISDIR(child_st.st_mode):
                out.extend(self._walk_markdown_files(child))
            elif stat.S_ISREG(child_st.st_mode) and child.suffix == ".md":
                rel = child.relative_to(self.root).as_posix()
                if self._allowed_artifact_rel(rel):
                    out.append(child)
        return out

    def _unlink_regular_artifact(self, rel: str) -> None:
        try:
            path = self._safe_path(rel)
            st = path.lstat()
        except FileNotFoundError:
            return
        if stat.S_ISREG(st.st_mode) and not stat.S_ISLNK(st.st_mode):
            path.unlink(missing_ok=True)

    def _remove_markdown_tree(self, directory: Path) -> None:
        try:
            st = directory.lstat()
        except FileNotFoundError:
            return
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
            return
        try:
            children = sorted(directory.iterdir(), key=lambda p: p.name)
        except OSError:
            return
        for child in children:
            try:
                child_st = child.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(child_st.st_mode):
                continue
            if stat.S_ISDIR(child_st.st_mode):
                self._remove_markdown_tree(child)
                try:
                    child.rmdir()
                except OSError:
                    pass
            elif stat.S_ISREG(child_st.st_mode) and child.suffix == ".md" and self._within_root(child):
                child.unlink(missing_ok=True)

    def _assert_root_safe(self) -> None:
        try:
            st = self.root.lstat()
        except FileNotFoundError:
            return
        if stat.S_ISLNK(st.st_mode):
            raise FileNotFoundError(str(self.root))
        if not stat.S_ISDIR(st.st_mode):
            raise NotADirectoryError(str(self.root))

    def _safe_path(self, rel: str) -> Path:
        self._assert_root_safe()
        safe = Path(rel)
        if safe.is_absolute() or ".." in safe.parts:
            raise FileNotFoundError(rel)
        rel_posix = safe.as_posix()
        if rel_posix in ("", "."):
            raise FileNotFoundError(rel)
        path = self.root / safe
        if not self._within_root(path):
            raise FileNotFoundError(rel)
        if not self._within_root(path.parent):
            raise FileNotFoundError(rel)
        return path

    def _absolute_root(self) -> Path:
        return Path(os.path.abspath(self.root))

    def _within_root(self, path: Path) -> bool:
        root = self._absolute_root()
        candidate = Path(os.path.abspath(path))
        try:
            return os.path.commonpath([str(root), str(candidate)]) == str(root)
        except ValueError:
            return False

    def _ensure_parent_dir(self, path: Path) -> None:
        self.ensure_dirs()
        try:
            rel_parent = path.parent.relative_to(self.root)
        except ValueError as exc:
            raise FileNotFoundError(path.name) from exc
        current = self.root
        for part in rel_parent.parts:
            current = current / part
            try:
                st = current.lstat()
            except FileNotFoundError:
                current.mkdir(mode=0o700)
                st = current.lstat()
            if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
                raise FileNotFoundError(current.name)

    def _assert_parent_safe(self, path: Path) -> None:
        try:
            rel_parent = path.parent.relative_to(self.root)
        except ValueError as exc:
            raise FileNotFoundError(path.name) from exc
        current = self.root
        for part in rel_parent.parts:
            current = current / part
            try:
                st = current.lstat()
            except FileNotFoundError as exc:
                raise FileNotFoundError(path.name) from exc
            if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
                raise FileNotFoundError(current.name)

    def _open_no_follow(self, path: Path, flags: int, mode: int = 0o600) -> int:
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        if nofollow:
            flags |= nofollow
        nonblock = getattr(os, "O_NONBLOCK", 0)
        if nonblock:
            flags |= nonblock
        try:
            return os.open(path, flags, mode)
        except OSError as exc:
            suspicious = path.is_symlink() or exc.errno in {
                errno.ELOOP,
                getattr(errno, "EMLINK", errno.ELOOP),
                getattr(errno, "ENXIO", errno.ELOOP),
            }
            if suspicious or (exc.errno == errno.ENOENT and path.is_symlink()):
                raise FileNotFoundError(path.name) from exc
            raise

    def _lstat_regular(self, path: Path, *, allow_missing: bool = False) -> os.stat_result | None:
        self._assert_parent_safe(path)
        try:
            st = path.lstat()
        except FileNotFoundError:
            if allow_missing:
                return None
            raise FileNotFoundError(path.name)
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
            raise FileNotFoundError(path.name)
        return st

    def _open_regular_no_follow(self, path: Path, flags: int, mode: int = 0o600, *, allow_missing: bool) -> int:
        if allow_missing:
            self._ensure_parent_dir(path)
        self._lstat_regular(path, allow_missing=allow_missing)
        fd = self._open_no_follow(path, flags, mode)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise FileNotFoundError(path.name)
            return fd
        except Exception:
            os.close(fd)
            raise

    def _write_text_no_symlink(self, path: Path, content: str) -> None:
        fd = self._open_regular_no_follow(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600, allow_missing=True)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)

    def _append_text_no_symlink(self, path: Path, content: str) -> None:
        fd = self._open_regular_no_follow(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600, allow_missing=True)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(content)

    def _read_text_no_symlink(self, path: Path) -> str:
        fd = self._open_regular_no_follow(path, os.O_RDONLY, allow_missing=False)
        with os.fdopen(fd, "r", encoding="utf-8") as f:
            return f.read()

    def _sanitize_changelog_file(self, path: Path, *, ensure_trailing_newline: bool = False) -> None:
        self._lstat_regular(path, allow_missing=False)
        content = self._read_text_no_symlink(path)
        rel = path.relative_to(self.root).as_posix()
        month_match = _CHANGELOG_MONTH_RE.match(rel)
        if month_match:
            label = month_match.group(2)  # YYYY-MM
            sanitized = _render_changelog_month(
                content, year=int(month_match.group(1)), month_num=int(label.split("-")[1]), month_label=label
            )
        else:
            sanitized = _sanitize_changelog_content(content, compact_dates=True)
        if ensure_trailing_newline and sanitized and not sanitized.endswith("\n"):
            sanitized += "\n"
        if sanitized != content:
            self._write_text_no_symlink(path, sanitized)
