from ntrp.integrations.base import (
    Integration,
    IntegrationField,
    IntegrationHealth,
    ToolProviderStatus,
)
from ntrp.integrations.registry import IntegrationRegistry
from ntrp.integrations.slack import SLACK

ALL_INTEGRATIONS: list[Integration] = [SLACK]

__all__ = [
    "ALL_INTEGRATIONS",
    "Integration",
    "IntegrationField",
    "IntegrationHealth",
    "IntegrationRegistry",
    "ToolProviderStatus",
]
