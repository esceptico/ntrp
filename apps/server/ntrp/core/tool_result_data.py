def persistable_tool_result_data(data: dict | None) -> dict | None:
    if not isinstance(data, dict):
        return None
    child_agent = data.get("child_agent")
    if isinstance(child_agent, dict):
        return {"child_agent": child_agent}
    return None
