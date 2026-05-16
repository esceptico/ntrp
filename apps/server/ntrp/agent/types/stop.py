from enum import StrEnum


class StopReason(StrEnum):
    END_TURN = "end_turn"
    MAX_ITERATIONS = "max_iterations"
    MAX_DEPTH = "max_depth"
    MAX_TOOL_CALLS = "max_tool_calls"
    MAX_WALL_TIME = "max_wall_time"
    MAX_COST = "max_cost"
    CANCELLED = "cancelled"
