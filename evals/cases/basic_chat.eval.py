async def test_basic_chat(t):
    result = await t.send("Say hello.")
    result.completed()
    result.no_failed_actions()
