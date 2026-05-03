from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from ntrp.config import Config
    from ntrp.notifiers.base import Notifier

from ntrp.tools.core.base import Tool


@dataclass(frozen=True)
class IntegrationField:
    key: str
    label: str
    secret: bool = False
    env_var: str | None = None


@dataclass(frozen=True)
class IntegrationHealth:
    status: Literal["connected", "error", "not_configured"]
    detail: str | None = None


@dataclass(frozen=True)
class Integration:
    id: str
    label: str
    service_fields: list[IntegrationField] = field(default_factory=list)
    tools: dict[str, Tool] = field(default_factory=dict)
    notifier_class: type["Notifier"] | None = None
    build: Callable[["Config"], object | None] | None = None


@dataclass(frozen=True)
class ToolProviderStatus:
    id: str
    label: str
    kind: Literal["native", "mcp"]
    health: IntegrationHealth
    tool_count: int
