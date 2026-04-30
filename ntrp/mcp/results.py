import json
from dataclasses import dataclass
from typing import Any

from mcp import types as mcp_types

from ntrp.tools.core.base import ToolResult


@dataclass(frozen=True)
class ContentProjection:
    text: str
    fallback: str
    metadata: tuple[dict[str, Any], ...] = ()


def call_tool_result_to_tool_result(result: mcp_types.CallToolResult) -> ToolResult:
    projection = _project_content(result.content)
    content = _model_content(result, projection)
    return ToolResult(
        content=content,
        preview=content[:100] if content else "Empty result",
        is_error=bool(result.isError),
        data=_metadata(result, projection),
    )


def _model_content(result: mcp_types.CallToolResult, projection: ContentProjection) -> str:
    if projection.text:
        return projection.text
    if projection.fallback:
        return projection.fallback
    if result.structuredContent is not None:
        return json.dumps(result.structuredContent, ensure_ascii=False, sort_keys=True)
    return ""


def _project_content(blocks: list[mcp_types.ContentBlock]) -> ContentProjection:
    text: list[str] = []
    fallback: list[str] = []
    metadata: list[dict[str, Any]] = []

    for block in blocks:
        match block:
            case mcp_types.TextContent():
                text.append(block.text)
            case mcp_types.EmbeddedResource(resource=mcp_types.TextResourceContents() as resource):
                text.append(resource.text)
                metadata.append(_resource_metadata(resource))
            case mcp_types.ImageContent():
                fallback.append("[image content]")
                metadata.append(_media_metadata("image", block.mimeType, block.data))
            case mcp_types.AudioContent():
                fallback.append("[audio content]")
                metadata.append(_media_metadata("audio", block.mimeType, block.data))
            case mcp_types.ResourceLink():
                fallback.append(f"[resource: {block.uri}]")
                metadata.append(_resource_link_metadata(block))
            case mcp_types.EmbeddedResource():
                fallback.append(f"[resource: {block.resource.uri}]")
                metadata.append(_resource_metadata(block.resource))

    return ContentProjection(
        text="\n".join(part for part in text if part),
        fallback="\n".join(part for part in fallback if part),
        metadata=tuple(metadata),
    )


def _metadata(result: mcp_types.CallToolResult, projection: ContentProjection) -> dict | None:
    data = {}
    if result.structuredContent is not None:
        data["structuredContent"] = result.structuredContent
    if result.meta is not None:
        data["_meta"] = result.meta
    if projection.metadata:
        data["content"] = list(projection.metadata)
    return data or None


def _media_metadata(kind: str, mime_type: str, data: str) -> dict[str, Any]:
    return {
        "type": kind,
        "mimeType": mime_type,
        "base64Length": len(data),
    }


def _resource_link_metadata(block: mcp_types.ResourceLink) -> dict[str, Any]:
    data: dict[str, Any] = {
        "type": "resource_link",
        "uri": str(block.uri),
        "name": block.name,
    }
    if block.title:
        data["title"] = block.title
    if block.mimeType:
        data["mimeType"] = block.mimeType
    if block.size is not None:
        data["size"] = block.size
    return data


def _resource_metadata(resource: mcp_types.TextResourceContents | mcp_types.BlobResourceContents) -> dict[str, Any]:
    data: dict[str, Any] = {
        "type": "resource",
        "uri": str(resource.uri),
    }
    if resource.mimeType:
        data["mimeType"] = resource.mimeType
    if isinstance(resource, mcp_types.BlobResourceContents):
        data["base64Length"] = len(resource.blob)
    return data
