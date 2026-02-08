from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

from pydantic import BaseModel

from ntrp.tools.core.context import ToolExecution


def _inline_refs(schema: dict) -> dict:
    """Resolve $ref pointers by inlining definitions from $defs."""
    defs = schema.get("$defs", {})
    if not defs:
        return schema

    def _resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                ref_path = node["$ref"]
                # "#/$defs/ModelName" -> "ModelName"
                ref_name = ref_path.rsplit("/", 1)[-1]
                if ref_name in defs:
                    return _resolve(defs[ref_name])
                return node
            return {k: _resolve(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [_resolve(item) for item in node]
        return node

    return _resolve(schema)


@dataclass(frozen=True)
class ToolResult:
    content: str
    preview: str
    metadata: dict | None = None
    is_error: bool = False


class Tool(ABC):
    name: str
    description: str
    mutates: bool = False
    source_type: ClassVar[type | None] = None
    input_model: ClassVar[type[BaseModel] | None] = None

    @property
    def available(self) -> bool:
        return True

    @abstractmethod
    async def execute(self, execution: ToolExecution, **kwargs: Any) -> ToolResult: ...

    def to_dict(self) -> dict:
        schema: dict = {"name": self.name, "description": self.description}
        if self.input_model is not None:
            json_schema = _inline_refs(self.input_model.model_json_schema())
            schema["parameters"] = {
                "type": "object",
                "properties": json_schema.get("properties", {}),
                "required": json_schema.get("required", []),
            }
        return {
            "type": "function",
            "function": schema,
        }

    def get_metadata(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "mutates": self.mutates,
        }
