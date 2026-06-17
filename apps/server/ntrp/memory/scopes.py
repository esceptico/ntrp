"""Default memory scope resolution for reads and writes."""

from dataclasses import dataclass, replace
from typing import Any

from ntrp.memory.models import Kind, SourceRef


@dataclass(frozen=True)
class MemoryScope:
    kind: str | None
    key: str | None = None


GLOBAL_SCOPE = MemoryScope("global", None)
USER_SCOPE = MemoryScope("user", None)
SESSION_SOURCE_KINDS = {"chat_turn", "curator", "session_handoff"}
INTEGRATION_SOURCE_KINDS = {"file", "web", "email", "gmail", "calendar", "slack", "mcp", "integration"}


def project_scope(project: Any) -> MemoryScope:
    return MemoryScope("project", project.knowledge_scope or project.project_id)


def scope_for_write(
    *,
    kind: str | None,
    project=None,
    session_id: str | None = None,
    source_ref: SourceRef | None = None,
    explicit_scope: MemoryScope | None = None,
) -> MemoryScope:
    if explicit_scope is not None:
        return explicit_scope
    if kind == Kind.DIRECTIVE or kind == str(Kind.DIRECTIVE):
        return GLOBAL_SCOPE
    if project is not None:
        return project_scope(project)
    if source_ref is not None and source_ref.kind in INTEGRATION_SOURCE_KINDS:
        return MemoryScope("integration", f"{source_ref.kind}:{source_ref.ref}"[:500])
    return USER_SCOPE


def scopes_for_read(*, project=None, session_id: str | None = None) -> list[MemoryScope]:
    if project is not None:
        return [GLOBAL_SCOPE, USER_SCOPE, project_scope(project)]
    if session_id:
        return [GLOBAL_SCOPE, USER_SCOPE, MemoryScope("session", session_id)]
    return [GLOBAL_SCOPE, USER_SCOPE]


def apply_scope_to_source(source_ref: SourceRef | None, scope: MemoryScope) -> SourceRef | None:
    if source_ref is None:
        return None
    return replace(source_ref, scope_kind=scope.kind, scope_key=scope.key)
