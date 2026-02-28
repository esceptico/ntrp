---
name: add-tool
description: Create a custom user tool in ~/.ntrp/tools/ — auto-discovered at startup
---

# Add User Tool

Help the user create a custom tool. User tools live in `~/.ntrp/tools/` as Python files and are auto-discovered at startup.

**Important**: Use `bash` to create directories and copy files. Use `read_file` to read and verify. Do not generate tool code from scratch — start from the scaffold.

## Step 1: Gather requirements

Ask the user:
1. What should the tool do?
2. What parameters does it need?
3. Does it modify external state? (if yes → `mutates = True`, needs approval flow)
4. Does it need an existing source or service? (see available services below)

## Step 2: Copy the scaffold

The scaffold template is at `<skill_path>/assets/scaffold.py` (where `<skill_path>` is the `path` attribute from the `<skill>` tag above).

1. Use `read_file` to read the scaffold
2. Use `bash` to create the target directory and copy:

```bash
mkdir -p ~/.ntrp/tools
cp <skill_path>/assets/scaffold.py ~/.ntrp/tools/<tool_name>.py
```

## Step 3: Customize

Use `read_file` on `~/.ntrp/tools/<tool_name>.py`, then use `bash` to apply edits:

- Rename classes (`ToolInput`, `UserTool`) to match the tool's purpose
- Fill in `name`, `display_name`, `description`
- Update `ToolInput` fields to match the user's parameters
- Implement the `execute()` method
- If `mutates = True`, uncomment and implement `approval_info()`
- If the tool needs a source, uncomment `requires` and add source access (see patterns below)

## Source/service access patterns

### Source-backed (protocol lookup)

```python
from ntrp.sources.base import NotesSource  # or EmailSource, CalendarSource, etc.

class MyTool(Tool):
    requires = frozenset({"notes"})

    async def execute(self, execution: ToolExecution, query: str, **kwargs: Any) -> ToolResult:
        source = execution.ctx.get_source(NotesSource)
        data = source.search(query)
        return ToolResult(content="\n".join(data), preview=f"{len(data)} results")
```

### Service-backed (dict access)

```python
class MyTool(Tool):
    requires = frozenset({"memory"})

    async def execute(self, execution: ToolExecution, **kwargs: Any) -> ToolResult:
        memory = execution.ctx.services["memory"]
```

## Available services

Keys for `requires` and `execution.ctx.services`:

| Key | Type | What it provides |
|-----|------|-----------------|
| `notes` | `NotesSource` | Obsidian vault read/write/search |
| `gmail` | `EmailSource` | Email read/search/send |
| `calendar` | `CalendarSource` | Calendar events CRUD |
| `browser` | `BrowserSource` | Browser history search |
| `web` | `WebSearchSource` | Web search and content fetch |
| `memory` | `FactMemory` | Long-term memory store |
| `automation` | `AutomationService` | Scheduled automation management |
| `skill_registry` | `SkillRegistry` | Skill lookup and loading |
| `search_index` | `SearchIndex` | Vector search across indexed sources |

Source protocols: `ntrp/sources/base.py`. Use `execution.ctx.get_source(ProtocolType)` for type-safe access.

## Tool class fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Unique identifier, used in tool calls |
| `display_name` | yes | Shown in the UI |
| `description` | yes | The LLM reads this to decide when to call the tool |
| `input_model` | no | Pydantic BaseModel — auto-generates JSON Schema for the LLM |
| `requires` | no | `frozenset` of service keys — tool hidden when any is missing |
| `mutates` | no | `True` → triggers user approval before `execute()` runs |

## Step 4: Verify and inform

1. Use `read_file` to verify the final tool file
2. Tell the user to restart the server (`ntrp serve`) for discovery
3. Name conflicts with built-ins are skipped with a warning; import errors are logged and skipped

## Notes

- User tools have the same API as built-in tools
- User tools can use existing sources/services but cannot define new ones
- External packages must be installed in the environment (`uv pip install ...`)
- Multiple Tool classes in one file are all registered
