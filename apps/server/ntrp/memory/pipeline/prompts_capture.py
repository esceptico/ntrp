"""Capture-stage prompt + structured-output schema (CONTRACTS §4).

NOTE (contract deviation, surfaced not freelanced): CONTRACTS §13 lists a single
shared `prompts.py` for all stages. To avoid clobbering a file other component
builders also write, Capture's prompt lives in its own module. The integration
phase can fold this into `prompts.py` verbatim — the schema/text are the contract.

The ONLY LLM call Capture makes is the SEMANTIC boundary check, and it runs
BACKGROUND-ONLY (never on the interactive hot path). It detects a topic shift in
a batch of un-segmented exchanges so a never-closing stream still gets bounded.
"""

from pydantic import BaseModel, Field

SEMANTIC_BOUNDARY_SYSTEM = """You segment a continuous stream of agent activity into topically-coherent units.

You are given:
- CONTINUITY: the first line of the prior captured window (anchor, not a summary).
- BATCH: the next un-segmented exchanges, each tagged [i] by index.
- SOURCE_KIND: where the stream came from (live_chat | automation | scheduled).

Decide whether the BATCH contains a topic/task SHIFT — a point where the subject
of work changes enough that everything after it belongs to a different unit than
everything before it.

Rules:
- Report a shift ONLY when there is a clear change of topic or task, not on every
  sub-step of the same task. Operational runs doing one job are ONE unit.
- If you report a shift, `cut_after_index` is the index of the LAST exchange that
  belongs to the CURRENT (pre-shift) unit. Everything after it starts the next.
- `cut_after_index` must be a valid index in BATCH and must not be the final
  index (a cut after the last item segments nothing).
- When unsure, report no shift. Over-segmentation fragments knowledge; a missed
  shift is recovered on the next sweep.

You do not summarize, judge worth, or extract facts. You only mark the boundary."""

SEMANTIC_BOUNDARY_USER = """SOURCE_KIND: {source_kind}
CONTINUITY: {continuity}

BATCH:
{batch}"""


class SemanticBoundary(BaseModel):
    """Structured output for the SEMANTIC boundary check (CONTRACTS §4)."""

    shift: bool = Field(description="True iff the batch contains a topic/task shift.")
    cut_after_index: int | None = Field(
        default=None,
        description="Index of the last exchange in the current unit; null when shift is false.",
    )
    reason: str = Field(description="One line: why the cut is here (or why no shift).")


def render_batch(exchanges: list[tuple[int, str]], *, max_chars_per_exchange: int = 800) -> str:
    """Render (index, text) exchanges as indexed lines, head/tail truncating long dumps."""
    lines: list[str] = []
    for idx, text in exchanges:
        body = text.strip()
        if len(body) > max_chars_per_exchange:
            head = body[: max_chars_per_exchange // 2]
            tail = body[-max_chars_per_exchange // 2 :]
            body = f"{head}\n…[truncated]…\n{tail}"
        lines.append(f"[{idx}] {body}")
    return "\n\n".join(lines)
