import re
from typing import Literal, TypedDict


class ChatSegmentRefParts(TypedDict):
    kind: Literal["chat_segment"]
    session_id: str
    message_start: int
    message_end: int


class ChatMessageRangeRefParts(TypedDict):
    kind: Literal["chat_message_range"]
    session_id: str
    message_start_id: str
    message_end_id: str


SourceRefParts = ChatSegmentRefParts | ChatMessageRangeRefParts

_CHAT_SEGMENT_RE = re.compile(r"^chat:(?P<session_id>.+):(?P<message_start>\d+)-(?P<message_end>\d+)$")
_CHAT_MESSAGE_RANGE_RE = re.compile(
    r"^chatmsg:(?P<session_id>.+):(?P<message_start_id>[^.]+)\.\.(?P<message_end_id>.+)$"
)


def chat_segment_ref(session_id: str, start: int, end: int) -> str:
    return f"chat:{session_id}:{start}-{end}"


def chat_message_range_ref(session_id: str, start_id: str, end_id: str) -> str:
    return f"chatmsg:{session_id}:{start_id}..{end_id}"


def parse_source_ref(source_ref: str | None) -> SourceRefParts | None:
    if not source_ref:
        return None

    stripped = source_ref.strip()
    match = _CHAT_MESSAGE_RANGE_RE.fullmatch(stripped)
    if match:
        start_id = match.group("message_start_id")
        end_id = match.group("message_end_id")
        if not start_id or not end_id:
            return None
        return {
            "kind": "chat_message_range",
            "session_id": match.group("session_id"),
            "message_start_id": start_id,
            "message_end_id": end_id,
        }

    match = _CHAT_SEGMENT_RE.fullmatch(stripped)
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
