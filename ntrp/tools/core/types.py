from dataclasses import dataclass


@dataclass(frozen=True)
class ApprovalInfo:
    description: str
    preview: str | None
    diff: str | None
