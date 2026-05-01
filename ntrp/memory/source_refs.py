def chat_segment_ref(session_id: str, start: int, end: int) -> str:
    return f"chat:{session_id}:{start}-{end}"
