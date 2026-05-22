import pytest

from ntrp.agent.tools.dispatch import dispatch_tools
from ntrp.agent.types.events import ToolCompleted
from ntrp.agent.types.llm import Role
from ntrp.agent.types.tool_call import FunctionCall, PendingToolCall, ToolCall
from ntrp.core.content import ImageContent


class FakeRunner:
    async def execute_all(self, _calls):
        yield ToolCompleted(
            tool_id="call_1",
            name="slack_thread",
            result="thread text",
            preview="thread",
            duration_ms=1,
            is_error=False,
            data=None,
            display_name="SlackThread",
            model_content=(ImageContent(media_type="image/png", data="ZmFrZXBuZw=="),),
        )


@pytest.mark.asyncio
async def test_dispatch_tools_appends_meta_user_message_for_model_visible_images():
    raw = ToolCall(
        id="call_1",
        type="function",
        function=FunctionCall(name="slack_thread", arguments='{"message_id":"C1:1"}'),
    )
    pending = PendingToolCall(tool_call=raw, name="slack_thread", args={"message_id": "C1:1"})
    messages = []

    async for _event in dispatch_tools(FakeRunner(), messages, [pending], [raw]):
        pass

    assert messages[0] == {"role": Role.TOOL, "tool_call_id": "call_1", "content": "thread text"}
    assert messages[1]["role"] == Role.USER
    assert messages[1]["is_meta"] is True
    assert messages[1]["client_id"] == "tool-media:call_1"
    assert messages[1]["content"][-1] == {"type": "image", "media_type": "image/png", "data": "ZmFrZXBuZw=="}
