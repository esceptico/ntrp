import json
import re
from datetime import UTC, datetime
from typing import get_args
from uuid import uuid4

from ntrp.logging import get_logger
from ntrp.memory.pages import Page
from ntrp.operator.runner import OperatorDeps, RunRequest, run_agent
from ntrp.slices.asks import AskStore
from ntrp.slices.models import Ask, AskKind, Slice
from ntrp.slices.projection import parse_open_loops

_logger = get_logger(__name__)

_ASK_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
_VALID_ASK_KINDS = frozenset(get_args(AskKind))

_CONTRACT = {
    "observe": "You may READ anything and update the topic page, but take no external action.",
    "act": "You may run this slice's automations and workflows; irreversible actions still require approval.",
}

# Names of the memory-write tools (see ntrp/tools/memory.py) — the "update the
# topic page" half of the observe contract. Granted on top of the read-only
# toolset via RunRequest.extra_tool_names so an observe-mode run stays
# non-auto-approve (approvals still gate everything else) while still able to
# do the one write action its contract promises.
_OBSERVE_EXTRA_TOOLS = frozenset({"remember", "forget", "memory_patch", "memory_write"})


def build_slice_prompt(slice: Slice, page: Page, recent: list[dict]) -> str:
    loops = "\n".join(f"- {l}" for l in parse_open_loops(page.prose)) or "- (none)"
    events = "\n".join(f"- {json.dumps(e)}" for e in recent) or "- (none)"
    return (
        f"You are the standing agent for the '{slice.title}' slice of the user's life.\n"
        f"Autonomy contract ({slice.autonomy}): {_CONTRACT[slice.autonomy]}\n\n"
        f"Topic page:\n\n{page.prose}\n\n"
        f"Open loops:\n{loops}\n\n"
        f"What changed since your last run:\n{events}\n\n"
        "Your job: absorb what changed, update the topic page if warranted (memory tools), "
        "and decide whether ANYTHING needs the user. Nominate at most ONE ask.\n"
        "If something needs them, end your reply with exactly one fenced json block:\n"
        '```json\n{"ask": {"text": "<one sentence>", "kind": "review|decide|act|drift"}}\n```\n'
        "If nothing needs them, end with no json block — silence is the correct output on a quiet day."
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


async def run_slice_agent(
    deps: OperatorDeps, slice: Slice, page: Page, asks: AskStore, recent: list[dict],
) -> str | None:
    # Observe: narrow toolset (read + the named memory-write tools) with
    # approvals SKIPPED — a detached run has no approval UI, and the page is
    # the agent's own notebook; safety comes from the toolset. NOTE the two
    # separate runner dials: extra_tool_names picks the set, skip_approvals
    # (not auto_approve, which only widens the set) disarms the gates.
    # Act: full set, gates ON — gated calls fail fast in detached runs; the
    # ask-mediated approval loop for act mode is future work.
    observe = slice.autonomy == "observe"
    request = RunRequest(
        prompt=build_slice_prompt(slice, page, recent),
        auto_approve=not observe,
        skip_approvals=observe,
        source_id=f"slice:{slice.key}",
        automation_id=f"slice:{slice.key}",
        extra_tool_names=_OBSERVE_EXTRA_TOOLS if observe else frozenset(),
    )
    result = await run_agent(deps, request)
    if not result.output:
        # A silent-empty run is indistinguishable from a healthy quiet one in
        # the automations UI — leave a diagnostic trail instead of "".
        return "(agent run ended without a report — likely hit an error or produced only tool calls)"
    nominated = parse_agent_ask(result.output)
    # Every run re-decides the slice's ONE ask: silence retires the previous
    # nomination just like a new one supersedes it — a stale ask outliving
    # the agent's own re-evaluation contradicts the contract.
    asks.retire_active_agent_asks(slice.key)
    if nominated:
        asks.upsert(Ask(
            id=f"agent:{slice.key}:{uuid4().hex[:8]}",
            slice_key=slice.key, text=nominated["text"], kind=nominated["kind"],
            source="agent", actions=[{"verb": "open_page", "ref": slice.page_path}],
            state="active", created_at=datetime.now(UTC).isoformat(),
            provenance=f"run:{result.run_id}",
        ))
    return result.output
