import json


def parse_args(raw: str | dict) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def blocks_to_text(content: str | list | None) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts = []
    image_count = 0
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block["text"])
        elif isinstance(block, dict) and block.get("type") == "image":
            image_count += 1
        elif isinstance(block, str):
            parts.append(block)
    text = "\n\n".join(parts)
    if image_count:
        tag = f"[{image_count} image{'s' if image_count > 1 else ''}]"
        return f"{text}\n\n{tag}" if text else tag
    return text
