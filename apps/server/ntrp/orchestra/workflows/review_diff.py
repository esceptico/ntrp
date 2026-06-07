from pydantic import BaseModel, Field

from ntrp.orchestra.engine import Orchestra
from ntrp.orchestra.registry import WorkflowMeta


class ReviewParams(BaseModel):
    base: str = Field(default="main", description="Git ref to diff the working tree against.")


class Finding(BaseModel):
    file: str
    line: int = 0
    severity: str
    issue: str


class FindingList(BaseModel):
    findings: list[Finding] = Field(default_factory=list)


class Verdict(BaseModel):
    real: bool
    reason: str = ""


META = WorkflowMeta(
    name="review-diff",
    description="Review the working-tree diff across dimensions and adversarially verify each finding.",
    params=ReviewParams,
)

_DIMENSIONS = [
    ("bugs", "Find correctness bugs and logic errors"),
    ("perf", "Find performance problems"),
    ("style", "Find code-style and convention violations"),
]


async def _verify(o: Orchestra, finding: Finding) -> Finding | None:
    verdict = await o.agent(
        "A reviewer claims this issue exists in the current working-tree diff:\n"
        f"{finding.model_dump_json()}\n"
        "Verify it against the actual changed code. Try hard to REFUTE it. "
        "Set real=false if it is wrong, already handled, or not actually in the diff.",
        schema=Verdict,
        phase="verify",
    )
    return finding if verdict and verdict.real else None


async def run(o: Orchestra, args: ReviewParams) -> dict:
    o.phase("review")
    o.log(f"Reviewing diff vs {args.base} across {len(_DIMENSIONS)} dimensions")
    batches = await o.pipeline(
        _DIMENSIONS,
        lambda dim, *_: o.agent(
            f"Run `git diff {args.base}` and review ONLY the changed lines. {dim[1]}. "
            "For each issue report file, line, severity, and a one-line description.",
            schema=FindingList,
            phase="review",
        ),
        lambda found, dim, _: o.parallel([(lambda f=f: _verify(o, f)) for f in found.findings]),
    )
    confirmed = [f for batch in batches if batch for f in batch if f]
    return {"count": len(confirmed), "confirmed": [f.model_dump() for f in confirmed]}
