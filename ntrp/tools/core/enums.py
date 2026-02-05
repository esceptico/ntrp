from enum import StrEnum


class EditType(StrEnum):
    """Types of note edit operations."""

    EDIT = "edit"
    CREATE = "create"
    DELETE = "delete"
    MOVE = "move"


class CalendarAction(StrEnum):
    """Types of calendar operations."""

    CREATE = "create"
    EDIT = "edit"
    DELETE = "delete"


class ToolGroup(StrEnum):
    """Tool groups for registration."""

    DEFAULT = "default"
    NOTES = "notes"
    SEARCH = "search"
    EMAIL = "email"
    CALENDAR = "calendar"
    RECENT = "recent"
    MEMORY = "memory"
    BASH = "bash"
    FILES = "files"
    WEB = "web"
    EXPLORATION = "exploration"
    PLAN = "plan"
