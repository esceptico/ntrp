from mcp.types import CallToolResult, EmbeddedResource, ImageContent, TextContent, TextResourceContents

from ntrp.mcp.results import call_tool_result_to_tool_result


def _adapt(result: CallToolResult):
    return call_tool_result_to_tool_result(result)


def test_text_only_result_uses_text_content():
    result = _adapt(CallToolResult(content=[TextContent(type="text", text="## Results\n\n- `Note.md`")]))

    assert result.content == "## Results\n\n- `Note.md`"
    assert result.data is None
    assert result.is_error is False


def test_text_and_structured_content_keeps_text_primary():
    result = _adapt(
        CallToolResult(
            content=[TextContent(type="text", text="Found 1 note")],
            structuredContent={"hits": [{"path": "Note.md"}], "warnings": []},
        )
    )

    assert result.content == "Found 1 note"
    assert result.data == {"structuredContent": {"hits": [{"path": "Note.md"}], "warnings": []}}


def test_structured_content_only_falls_back_to_json():
    result = _adapt(CallToolResult(content=[], structuredContent={"hits": [{"path": "Note.md"}], "warnings": []}))

    assert result.content == '{"hits": [{"path": "Note.md"}], "warnings": []}'
    assert result.data == {"structuredContent": {"hits": [{"path": "Note.md"}], "warnings": []}}


def test_error_result_uses_text_content_as_error_message():
    result = _adapt(CallToolResult(content=[TextContent(type="text", text="Permission denied")], isError=True))

    assert result.content == "Permission denied"
    assert result.preview == "Permission denied"
    assert result.is_error is True


def test_multiple_text_blocks_are_joined():
    result = _adapt(
        CallToolResult(
            content=[
                TextContent(type="text", text="First block"),
                TextContent(type="text", text="Second block"),
            ]
        )
    )

    assert result.content == "First block\nSecond block"


def test_non_text_blocks_are_model_safe_placeholders():
    result = _adapt(CallToolResult(content=[ImageContent(type="image", data="base64", mimeType="image/png")]))

    assert result.content == "[image content]"
    assert result.data == {
        "content": [
            {
                "type": "image",
                "mimeType": "image/png",
                "base64Length": 6,
            }
        ]
    }


def test_text_blocks_are_not_polluted_by_non_text_placeholders():
    result = _adapt(
        CallToolResult(
            content=[
                TextContent(type="text", text="Visible result"),
                ImageContent(type="image", data="base64", mimeType="image/png"),
            ]
        )
    )

    assert result.content == "Visible result"
    assert result.data == {
        "content": [
            {
                "type": "image",
                "mimeType": "image/png",
                "base64Length": 6,
            }
        ]
    }


def test_embedded_text_resource_is_model_visible_text():
    result = _adapt(
        CallToolResult(
            content=[
                EmbeddedResource(
                    type="resource",
                    resource=TextResourceContents(
                        uri="file:///tmp/note.md",
                        mimeType="text/markdown",
                        text="# Note",
                    ),
                )
            ]
        )
    )

    assert result.content == "# Note"
    assert result.data == {
        "content": [
            {
                "type": "resource",
                "uri": "file:///tmp/note.md",
                "mimeType": "text/markdown",
            }
        ]
    }


def test_result_meta_is_preserved_outside_model_content():
    result = _adapt(
        CallToolResult(
            content=[TextContent(type="text", text="Visible")],
            _meta={"trace_id": "abc"},
        )
    )

    assert result.content == "Visible"
    assert result.data == {"_meta": {"trace_id": "abc"}}
