async def test_schedule_dispatch(t):
    await t.send("Dispatch the daily digest schedule.")
    t.completed()
    t.no_failed_actions()
