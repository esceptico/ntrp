async def test_approval_wait(t):
    await t.send("Draft an action that needs approval.")
    t.waiting_for_approval()
    t.no_failed_actions()
