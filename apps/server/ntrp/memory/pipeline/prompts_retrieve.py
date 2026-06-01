"""Retrieve-stage rubric + structured-output schema (CONTRACTS §9).

Isolated to the Retrieve component. The shared prompts.py (which the integration
phase assembles from every stage's rubric) may re-export these, but Retrieve owns
its own prompt so it can be built and tested independently.

The compression call is query-conditioned, SELECTS from the input set, and never
invents claims. Each kept claim must keep its source_refs intact — the prompt
returns indices into the numbered candidate list, never free text claims.
"""

from pydantic import BaseModel, Field

RETRIEVE_COMPRESS_SYSTEM = """\
You compress a personal knowledge base down to what answers ONE goal, for \
injection into an assistant's context. You are given a GOAL and a NUMBERED list \
of atomic, already-true claims recalled for it.

Your job:
- SELECT the claims that actually bear on the goal. Drop the rest.
- For each kept claim, optionally re-render it MORE TERSELY, preserving its exact \
meaning. Never add, infer, combine, or invent any fact not present in that claim.
- Order kept claims most-relevant first.
- Stay within the token budget by dropping whole low-relevance claims, not by \
fabricating summaries that span claims.

Rules:
- You may only reference claims by their given index. Every index you return MUST \
be one of the provided indices.
- Never merge two claims into one line. One kept index → one rendered line.
- If a claim is irrelevant to the goal, omit its index entirely.
- If nothing is relevant, return an empty selection.
- Do not editorialize, do not answer the goal yourself — only curate claims.\
"""


class CompressedClaim(BaseModel):
    index: int = Field(description="Index into the provided numbered claim list.")
    rendered: str = Field(
        description="Terse restatement of that claim's meaning, no new facts."
    )


class CompressionResult(BaseModel):
    kept: list[CompressedClaim] = Field(
        default_factory=list,
        description="Selected claims, most-relevant first, within budget.",
    )


def build_compression_user_prompt(goal: str, numbered_claims: list[str], token_budget: int) -> str:
    lines = "\n".join(numbered_claims)
    return (
        f"GOAL:\n{goal}\n\n"
        f"TOKEN BUDGET (approx): {token_budget}\n\n"
        f"CANDIDATE CLAIMS (index: content):\n{lines}\n\n"
        "Return the kept claims by index, most-relevant first, within budget."
    )
