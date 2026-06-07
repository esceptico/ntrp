import json

from pydantic import BaseModel

_DECODER = json.JSONDecoder()


def extract_json(text: str) -> str:
    """Return the first complete JSON value embedded in `text`.

    Scans for the first '{' or '[' and consumes exactly one balanced value with
    raw_decode, ignoring surrounding prose, code fences, or trailing text. Falls
    back to the stripped input when no JSON value is found, so the caller's
    validator raises a meaningful error."""
    stripped = text.strip()
    for i, ch in enumerate(stripped):
        if ch in "{[":
            try:
                obj, _ = _DECODER.raw_decode(stripped, i)
            except ValueError:
                continue
            return json.dumps(obj)
    return stripped


def coerce(text: str, schema: type[BaseModel]) -> BaseModel:
    return schema.model_validate_json(extract_json(text))


def schema_instruction(schema: type[BaseModel]) -> str:
    return (
        "Return ONLY a JSON object that matches this JSON schema, with no prose, "
        "no markdown fences, nothing else:\n"
        f"{json.dumps(schema.model_json_schema())}"
    )
