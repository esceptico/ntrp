import re
from typing import Literal, TypedDict


class ChatSegmentRefParts(TypedDict):
    kind: Literal["chat_segment"]
    session_id: str
    message_start: int
    message_end: int


SourceRefParts = ChatSegmentRefParts

_CHAT_SEGMENT_RE = re.compile(r"^chat:(?P<session_id>.+):(?P<message_start>\d+)-(?P<message_end>\d+)$")


def chat_segment_ref(session_id: str, start: int, end: int) -> str:
    return f"chat:{session_id}:{start}-{end}"


def parse_source_ref(source_ref: str | None) -> SourceRefParts | None:
    if not source_ref:
        return None

    match = _CHAT_SEGMENT_RE.fullmatch(source_ref.strip())
    if not match:
        return None

    message_start = int(match.group("message_start"))
    message_end = int(match.group("message_end"))
    if message_end < message_start:
        return None

    return {
        "kind": "chat_segment",
        "session_id": match.group("session_id"),
        "message_start": message_start,
        "message_end": message_end,
    }
