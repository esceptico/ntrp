from enum import StrEnum


class IsolationLevel(StrEnum):
    """Context isolation level for sub-agents."""

    FULL = "full"  # New session state, no inherited context
    SHARED = "shared"  # Use parent's session state
