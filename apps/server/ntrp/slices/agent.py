import json
import re
from datetime import UTC, datetime
from uuid import uuid4

from ntrp.logging import get_logger
from ntrp.slices.asks import AskStore
from ntrp.slices.models import Ask, Slice

_logger = get_logger(__name__)

_ASK_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
_VALID_ASK_KINDS = frozenset({"review", "decide", "act", "drift"})

# Observe-mode toolset as DATA: the automation's tool_scope allowlist
# (visible and editable on the automation itself) instead of a code-side
# toolset hack. Read/search surfaces + the memory tools that edit the
# slice's own page — nothing that acts on the outside world.
OBSERVE_TOOL_SCOPE = [
    "memory_*",
    "recall",
    "remember",
    "forget",
    "web_search",
    "web_fetch",
    "read_file",
    "list_files",
    "find_files",
    "search_text",
    "current_time",
    "update_todos",
]

_CONTRACT = {
    "observe": "You may read anything and update this slice's topic page, but take no external action.",
    "act": "You may run this slice's automations and workflows; irreversible actions still require approval.",
}


def slice_agent_instructions(slice: Slice) -> str:
    """The automation's description = the standing per-turn message. The
    fresh topic page is NOT embedded here — it arrives via the SLICE system
    block on the slice-tagged channel session, so every turn sees current
    state while these instructions stay static."""
    return (
        f"You are the standing agent for the '{slice.title}' slice of the user's life. "
        f"Its topic page is in your SLICE context block.\n"
        f"Autonomy contract ({slice.autonomy}): {_CONTRACT[slice.autonomy]}\n\n"
        "This turn: absorb what changed in this domain since your last turn (your channel "
        "history is your own past runs), update the topic page if warranted (memory tools), "
        "and decide whether ANYTHING needs the user.\n"
        "Ask-worthy: something new that needs their judgment, a drift between a commitment "
        "and reality, or a stale decision-ready open loop they haven't touched. Routine "
        "tracking is not ask-worthy.\n"
        "Nominate at most ONE ask — the single highest-leverage item. If something needs "
        "them, end your reply with exactly one fenced json block:\n"
        '```json\n{"ask": {"text": "<one sentence>", "kind": "review|decide|act|drift"}}\n```\n'
        "If nothing needs them, end with no json block — silence is correct on a quiet day."
    )


def parse_agent_ask(result_text: str) -> dict | None:
    """Parse the agent's fenced-json ask nomination, validating it at this
    trust boundary (the model's free-form output). An invalid nomination is
    treated as silence — logged, never upserted — rather than trusted or
    defensively patched up."""
    m = _ASK_BLOCK.search(result_text)
    if not m:
        return None
    ask = json.loads(m.group(1))["ask"]
    kind = ask.get("kind")
    text = ask.get("text")
    if kind not in _VALID_ASK_KINDS:
        _logger.warning("Slice agent nominated an ask with invalid kind %r; treating as silence", kind)
        return None
    if not isinstance(text, str) or not text.strip():
        _logger.warning("Slice agent nominated an ask with empty/non-str text %r; treating as silence", text)
        return None
    return ask


def record_slice_run(asks: AskStore, slice_key: str, page_path: str, result_text: str, run_ref: str) -> None:
    """Post-run ask sync (called from the outbox run-completed pipeline):
    every run re-decides the slice's ONE ask — silence retires the previous
    nomination just like a new one supersedes it."""
    nominated = parse_agent_ask(result_text)
    asks.retire_active_agent_asks(slice_key)
    if nominated:
        asks.upsert(
            Ask(
                id=f"agent:{slice_key}:{uuid4().hex[:8]}",
                slice_key=slice_key,
                text=nominated["text"],
                kind=nominated["kind"],
                source="agent",
                actions=[{"verb": "open_page", "ref": page_path}],
                state="active",
                created_at=datetime.now(UTC).isoformat(),
                provenance=run_ref,
            )
        )
