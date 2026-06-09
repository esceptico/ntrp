from typing import Any

from pydantic import BaseModel, create_model

from ntrp.tools.core import Tool, ToolAction, ToolPolicy, ToolResult, ToolScope, tool

# Structured output for workflow agents. When a script calls agent(task, schema=X),
# the worker gets a `structured_output` tool whose input model IS X — it calls the
# tool with its answer, the args are validated at the tool boundary (a bad shape is
# a cheap in-run retry, not a re-spawn), and those validated args are the result.
# No "JSON in the chat message", no string parsing.

_LEAF_TYPES: dict[str, type] = {"str": str, "int": int, "float": float, "bool": bool}


def _is_model(schema: Any) -> bool:
    return isinstance(schema, type) and issubclass(schema, BaseModel)


def model_from_schema(schema: Any, name: str = "StructuredOutput") -> type[BaseModel]:
    """A pydantic model is used as-is; a plain dict shape is built into one so
    scripts can stay free of pydantic boilerplate (e.g. {"facts": ["str"]})."""
    if _is_model(schema):
        return schema
    return _model_from_dict(schema, name)


def _type_from_spec(spec: Any, name: str) -> Any:
    if isinstance(spec, str):
        if spec not in _LEAF_TYPES:
            raise ValueError(f"unknown leaf type {spec!r} in workflow schema (use str/int/float/bool)")
        return _LEAF_TYPES[spec]
    if isinstance(spec, list):
        if len(spec) != 1:
            raise ValueError("a list in a workflow schema must hold exactly one element type")
        return list[_type_from_spec(spec[0], name)]
    if isinstance(spec, dict):
        return _model_from_dict(spec, name)
    raise ValueError(f"unsupported workflow schema spec: {spec!r}")


def _model_from_dict(schema: Any, name: str) -> type[BaseModel]:
    if not isinstance(schema, dict) or not schema:
        raise ValueError("workflow schema must be a non-empty dict or a pydantic model")
    fields = {key: (_type_from_spec(spec, f"{name}_{key}"), ...) for key, spec in schema.items()}
    return create_model(name, **fields)


def structured_output_tool(model: type[BaseModel], sink: list[BaseModel]) -> Tool:
    """A one-shot tool that records its (already pydantic-validated) args. The
    orchestra reads `sink[-1]` after the worker runs — that's the return value."""

    async def execute(execution: Any, args: BaseModel) -> ToolResult:
        sink.append(args)
        return ToolResult(content="Final answer recorded.", preview="recorded")

    return tool(
        description="Call this exactly once with your final answer as the structured result. "
        "Do not also write the answer as prose.",
        input_model=model,
        execute=execute,
        policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL, audit=False),
    )
