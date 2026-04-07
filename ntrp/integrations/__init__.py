from ntrp.integrations.base import (
    Integration,
    IntegrationField,
    IntegrationHealth,
    ToolProviderStatus,
)
from ntrp.integrations.registry import IntegrationRegistry
from ntrp.integrations.obsidian import OBSIDIAN
from ntrp.integrations.slack import SLACK
from ntrp.integrations.web import WEB

ALL_INTEGRATIONS: list[Integration] = [OBSIDIAN, WEB, SLACK]

__all__ = [
    "ALL_INTEGRATIONS",
    "Integration",
    "IntegrationField",
    "IntegrationHealth",
    "IntegrationRegistry",
    "ToolProviderStatus",
]
