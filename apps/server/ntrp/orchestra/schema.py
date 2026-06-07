import json
from typing import Any

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


def _is_model(schema: Any) -> bool:
    return isinstance(schema, type) and issubclass(schema, BaseModel)


def coerce(text: str, schema: Any) -> Any:
    """Parse the agent's text into the requested shape.

    `schema` is either a pydantic model (validated) or a plain dict describing the
    desired JSON shape — the dict form is lenient (parsed, not validated) so that
    dynamic workflow scripts stay free of pydantic boilerplate."""
    raw = extract_json(text)
    if _is_model(schema):
        return schema.model_validate_json(raw)
    return json.loads(raw)


def schema_instruction(schema: Any) -> str:
    shape = schema.model_json_schema() if _is_model(schema) else schema
    return (
        "Return ONLY JSON matching this shape, with no prose, no markdown fences, "
        "nothing else:\n"
        f"{json.dumps(shape)}"
    )
