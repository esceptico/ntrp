import json
import re
from datetime import UTC, datetime
from uuid import uuid4

from ntrp.memory.pages import Page
from ntrp.operator.runner import OperatorDeps, RunRequest, run_agent
from ntrp.slices.asks import AskStore
from ntrp.slices.models import Ask, Slice
from ntrp.slices.projection import parse_open_loops

_ASK_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)

_CONTRACT = {
    "observe": "You may READ anything and update the topic page, but take no external action.",
    "act": "You may run this slice's automations and workflows; irreversible actions still require approval.",
}


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
    m = _ASK_BLOCK.search(result_text)
    if not m:
        return None
    return json.loads(m.group(1))["ask"]


async def run_slice_agent(
    deps: OperatorDeps, slice: Slice, page: Page, asks: AskStore, recent: list[dict],
) -> str | None:
    request = RunRequest(
        prompt=build_slice_prompt(slice, page, recent),
        auto_approve=slice.autonomy == "act",
        source_id=f"slice:{slice.key}",
        automation_id=f"slice:{slice.key}",
    )
    result = await run_agent(deps, request)
    if not result.output:
        return None
    nominated = parse_agent_ask(result.output)
    if nominated:
        asks.upsert(Ask(
            id=f"agent:{slice.key}:{uuid4().hex[:8]}",
            slice_key=slice.key, text=nominated["text"], kind=nominated["kind"],
            source="agent", actions=[{"verb": "open_page", "ref": slice.page_path}],
            state="active", created_at=datetime.now(UTC).isoformat(),
            provenance=f"run:{result.run_id}",
        ))
    return result.output
