from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ToolAction(StrEnum):
    READ = "read"
    DRAFT = "draft"
    WRITE = "write"
    EXECUTE = "execute"


class ToolScope(StrEnum):
    INTERNAL = "internal"
    EXTERNAL = "external"


class ToolPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: ToolAction
    scope: ToolScope
    requires_approval: bool = False
    permissions: frozenset[str] = Field(default_factory=frozenset)
    timeout_seconds: int | None = None
    audit: bool = True
    max_result_chars: int | None = None
    offload: bool = True


class PermissionDecision(StrEnum):
    EXECUTE = "execute"
    REQUEST_APPROVAL = "request_approval"
    DENY = "deny"


class ToolOverrideDecision(StrEnum):
    APPROVE = "approve"
    ASK = "ask"
    DENY = "deny"


@dataclass(frozen=True)
class ApprovalInfo:
    description: str
    preview: str | None
    diff: str | None
