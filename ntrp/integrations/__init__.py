from ntrp.integrations.base import (
    Integration,
    IntegrationField,
    IntegrationHealth,
    ToolProviderStatus,
)
from ntrp.integrations.registry import IntegrationRegistry
from ntrp.integrations.calendar import CALENDAR
from ntrp.integrations.gmail import GMAIL
from ntrp.integrations.obsidian import OBSIDIAN
from ntrp.integrations.slack import SLACK
from ntrp.integrations.telegram import TELEGRAM
from ntrp.integrations.web import WEB

ALL_INTEGRATIONS: list[Integration] = [OBSIDIAN, GMAIL, CALENDAR, WEB, SLACK, TELEGRAM]

__all__ = [
    "ALL_INTEGRATIONS",
    "Integration",
    "IntegrationField",
    "IntegrationHealth",
    "IntegrationRegistry",
    "ToolProviderStatus",
]
