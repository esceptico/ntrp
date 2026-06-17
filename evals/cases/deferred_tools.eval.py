async def test_deferred_tools(t):
    result = await t.send("Load Slack tools.")
    result.called_tool("load_tools")
    result.loaded_tool_group("slack")
    result.completed()
