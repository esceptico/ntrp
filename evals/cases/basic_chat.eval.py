async def test_basic_chat(t):
    await t.send("Say hello.")
    t.completed()
    t.no_failed_actions()
