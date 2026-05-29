"""Durable on-disk store for large tool results.

Oversized tool output is written to a file under the app-data dir and the model
re-reads it with the normal `read_file` tool by path (offset/limit/grep) — the
pattern Claude Code and Hermes use. No bespoke read-by-id tool, no opaque handle
to reproduce. Files are keyed flat by tool_call_id so any layer can derive the
path without threading session state.
"""

from pathlib import Path

from ntrp.settings import NTRP_DIR

RESULTS_BASE = NTRP_DIR / "tool-results"


def result_file_path(tool_call_id: str) -> Path:
    return RESULTS_BASE / f"{tool_call_id}.txt"


def persist_result(tool_call_id: str, content: str) -> Path:
    path = result_file_path(tool_call_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
