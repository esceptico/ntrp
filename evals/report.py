from dataclasses import dataclass


@dataclass
class EventEvalResult:
    name: str
    passed: bool
    events: list[dict]
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "events": self.events,
            "error": self.error,
        }
