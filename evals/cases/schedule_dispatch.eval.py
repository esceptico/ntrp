async def test_schedule_dispatch(t):
    result = await t.send("Dispatch the daily digest schedule.")
    result.completed()
    result.no_failed_actions()
