from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from ntrp.agent import ToolResult
from ntrp.tools.core.context import ToolExecution
from ntrp.tools.core.types import ApprovalInfo, ToolPolicy


def _inline_refs(schema: dict) -> dict:
    """Resolve $ref pointers by inlining definitions from $defs."""
    defs = schema.get("$defs", {})
    if not defs:
        return schema

    def _resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                ref_path = node["$ref"]
                ref_name = ref_path.rsplit("/", 1)[-1]
                if ref_name in defs:
                    return _resolve(defs[ref_name])
                return node
            return {k: _resolve(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [_resolve(item) for item in node]
        return node

    return _resolve(schema)


__all__ = ["Tool", "ToolResult", "ApprovalInfo"]


class Tool(ABC):
    display_name: str | None = None
    description: str
    policy: ToolPolicy
    input_model: type[BaseModel] | None = None
    # Semantic kind used by the UI to pick a rendering surface. "agent"
    # marks tools that internally spawn a sub-agent (research, etc.) so
    # the chat can render them as agent cards instead of plain rows.
    kind: str = "tool"

    async def approval_info(self, execution: ToolExecution, **kwargs: Any) -> ApprovalInfo | None:
        return None

    @abstractmethod
    async def execute(self, execution: ToolExecution, **kwargs: Any) -> ToolResult: ...

    def to_dict(self, name: str) -> dict:
        schema: dict = {"name": name, "description": self.description}
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

    def get_metadata(self, name: str) -> dict:
        policy = self.policy.model_dump(mode="json")
        policy["permissions"] = sorted(policy["permissions"])
        return {
            "name": name,
            "display_name": self.display_name or name.replace("_", " ").title(),
            "description": self.description,
            "kind": self.kind,
            "policy": policy,
        }
