async def test_approval_wait(t):
    result = await t.send("Draft an action that needs approval.")
    result.waiting_for_approval()
    result.no_failed_actions()
