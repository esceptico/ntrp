from collections.abc import Awaitable, Callable

from evals.report import EventEvalResult
from evals.runtime_case import RuntimeCase

EventCase = Callable[[RuntimeCase], Awaitable[None]]


async def run_event_case(name: str, case: EventCase, runtime_case: RuntimeCase) -> EventEvalResult:
    try:
        await case(runtime_case)
    except AssertionError as exc:
        return EventEvalResult(name=name, passed=False, events=runtime_case.events, error=str(exc))
    except Exception as exc:
        return EventEvalResult(name=name, passed=False, events=runtime_case.events, error=f"{type(exc).__name__}: {exc}")
    return EventEvalResult(name=name, passed=True, events=runtime_case.events)
