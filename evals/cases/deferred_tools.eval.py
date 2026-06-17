async def test_deferred_tools(t):
    await t.send("Load Slack tools.")
    t.called_tool("load_tools")
    t.loaded_tool_group("slack")
    t.completed()
