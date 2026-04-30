---
name: add-tool
description: Create a custom user tool in ~/.ntrp/tools/ using the current tool(...) API.
---

# Add User Tool

Help the user create a custom tool. User tools live in `~/.ntrp/tools/` as Python files and are discovered when the server starts.

**Important**: Use `bash` to run the scaffold script and apply edits. Use `read_file` to read and verify. Do not create class-based tools. The only supported user-tool registration shape is a module-level `tools: dict[str, Tool]` built with `tool(...)`.

## Step 1: Gather requirements

Ask the user:
1. What should the tool do?
2. What parameters does it need?
3. Does it modify external state? (if yes -> `mutates=True`, needs an approval function)
4. Does it need an existing source or service? (see available services below)

## Step 2: Scaffold the tool file

Run the scaffold script (path is relative to the `path` attribute from the `<skill>` tag above):

```bash
bash <skill_path>/scripts/scaffold.sh <tool_name>
```

This creates `~/.ntrp/tools/<tool_name>.py` from the current `tool(...)` template.

## Step 3: Customize

Use `read_file` on `~/.ntrp/tools/<tool_name>.py`, then use `bash` to apply edits:

- Rename `ToolInput` and `execute_tool` if clearer
- Fill in `display_name` and `description`
- Update `ToolInput` fields to match the user's parameters
- Implement the execute function
- If `mutates=True`, uncomment and implement the approval function, then pass it as `approval=...`
- If the tool needs a source/service, uncomment `requires={...}` and add service access (see patterns below)
- Keep the module-level `tools = {"tool_name": tool(...)}` mapping

## Required shape

```python
from pydantic import BaseModel, Field

from ntrp.tools.core import ToolResult, tool
from ntrp.tools.core.context import ToolExecution


class MyInput(BaseModel):
    query: str = Field(description="Search query")


async def my_tool(execution: ToolExecution, args: MyInput) -> ToolResult:
    return ToolResult(content=args.query, preview="Done")


tools = {
    "my_tool": tool(
        display_name="MyTool",
        description="Describe when the agent should use this tool.",
        input_model=MyInput,
        execute=my_tool,
    )
}
```

The execute function must return `ToolResult`. Returning a string, dict, or arbitrary object is invalid.

## Service access patterns

### Client-backed

```python
from ntrp.integrations.slack.client import SlackClient


async def search_slack(execution: ToolExecution, args: MyInput) -> ToolResult:
    client = execution.ctx.get_client("slack", SlackClient)
    if client is None:
        return ToolResult(content="Slack is not configured.", preview="Missing service", is_error=True)
    results = await client.search_messages(args.query)
    lines = [f"{item.title}: {item.content}" for item in results]
    return ToolResult(content="\n".join(lines), preview=f"{len(results)} results")


tools = {
    "search_slack": tool(
        description="Search Slack messages.",
        input_model=MyInput,
        requires={"slack"},
        execute=search_slack,
    )
}
```

### Generic service lookup

```python
async def recall_memory(execution: ToolExecution, args: MyInput) -> ToolResult:
    memory = execution.ctx.services["memory"]
```

## Available services

Keys for `requires` and `execution.ctx.services`:

| Key | Type | What it provides |
|-----|------|-----------------|
| `gmail` | `MultiGmailSource` | Email read/search/send |
| `calendar` | `MultiCalendarSource` | Calendar events CRUD |
| `web` | `WebClient` | Web search and content fetch |
| `memory` | `FactMemory` | Long-term memory store |
| `automation` | `AutomationService` | Scheduled automation management |
| `skill_registry` | `SkillRegistry` | Skill lookup and loading |
| `search_index` | `SearchIndex` | Vector search across indexed sources |
| `slack` | `SlackClient` | Slack search/read APIs |
| `mcp` | `MCPManager` | Connected MCP tools |
| `notifiers` | `NotifierService` | Configured notifiers |

Use `execution.ctx.get_client("service_id", ClientType)` for integration clients when you can import the concrete client type. Use `execution.ctx.services["key"]` for internal services such as `memory` and `automation`.

## `tool(...)` arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `description` | yes | The LLM reads this to decide when to call the tool |
| `execute` | yes | Async function receiving `(ToolExecution, args)` and returning `ToolResult` |
| `display_name` | no | Shown in the UI |
| `input_model` | no | Pydantic `BaseModel`; omitted means no parameters |
| `requires` | no | Service keys; tool is hidden when any is missing |
| `mutates` | no | `True` marks the tool as mutating and runs approval middleware |
| `approval` | no | Async function returning `ApprovalInfo | None` before execution |
| `volatile` | no | `True` disables result caching/offloading assumptions for changing data |

## Step 4: Verify and inform

1. Use `read_file` to verify the final tool file
2. Tell the user to restart the server (`ntrp-server serve`) for discovery
3. Name conflicts with built-ins are skipped with a warning; import errors are logged and skipped

## Notes

- User tools use the same `tool(...)` API as built-in tools
- User tools can use existing sources/services but cannot define new ones
- External packages must be installed in the environment (`uv pip install ...`)
- Multiple tools in one file are allowed: add more entries to the module-level `tools` mapping
