from enum import StrEnum


class StopReason(StrEnum):
    END_TURN = "end_turn"
    MAX_ITERATIONS = "max_iterations"
    MAX_DEPTH = "max_depth"
    CANCELLED = "cancelled"
