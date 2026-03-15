import asyncio
import json
import shlex
import subprocess
import time
from typing import Any

from pydantic import BaseModel, Field

from ntrp.constants import BASH_OUTPUT_LIMIT, BASH_TIMEOUT
from ntrp.events.sse import BackgroundTaskEvent, ToolCallEvent, ToolResultEvent
from ntrp.logging import get_logger
from ntrp.tools.core.base import ApprovalInfo, Tool, ToolResult
from ntrp.tools.core.context import ToolExecution

_logger = get_logger(__name__)

SAFE_COMMANDS = frozenset(
    {
        "ls",
        "cat",
        "head",
        "tail",
        "wc",
        "file",
        "stat",
        "du",
        "df",
        "find",
        "locate",
        "which",
        "whereis",
        "type",
        "grep",
        "awk",
        "sed",
        "cut",
        "sort",
        "uniq",
        "tr",
        "diff",
        "pwd",
        "whoami",
        "hostname",
        "uname",
        "date",
        "uptime",
        "env",
        "printenv",
        "git status",
        "git log",
        "git diff",
        "git branch",
        "git show",
        "git remote",
        "git tag",
        "git stash list",
        "npm list",
        "pip list",
        "pip show",
        "curl",
        "wget",
        "ping",
        "host",
        "dig",
        "nslookup",
    }
)

BLOCKED_PATTERNS = frozenset(
    {
        "rm -rf /",
        "rm -rf ~",
        "rm -rf *",
        "dd if=",
        "mkfs",
        "fdisk",
        ":(){:|:&};:",
        "> /dev/sd",
        "chmod -R 777 /",
    }
)

BASH_DESCRIPTION = f"""Execute a bash command in the user's shell.

Each command runs in a fresh subprocess — no state (env vars, shell functions, cwd) persists between calls. Commands run in the server's working directory by default. Use the working_dir parameter to run in a different directory instead of 'cd'.

Set background=true for commands that may take more than a few seconds (installs, builds, test suites, downloads). The command runs asynchronously and results are delivered automatically when it finishes. Use list_background_tasks to check running tasks and cancel_background_task to stop one.

PREFER OTHER TOOLS:
- For searching files: use search() instead of grep/find
- For reading files: use read_note() or read_file()
- For editing files: use edit_note() or create_note()

USE bash FOR:
- System commands: git, npm, pip, brew
- File operations: mkdir, cp, mv (with permission)
- Checking system state: pwd, whoami, date

Commands time out after {BASH_TIMEOUT}s. Destructive commands (rm -rf) are blocked. Non-safe commands require approval."""


def is_safe_command(command: str) -> bool:
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    if not parts:
        return False
    base_cmd = parts[0]
    if base_cmd in SAFE_COMMANDS:
        return True
    if len(parts) >= 2:
        cmd_with_arg = f"{base_cmd} {parts[1]}"
        if cmd_with_arg in SAFE_COMMANDS:
            return True
    if command.endswith("--version") or " --version" in command:
        return True
    return False


def is_blocked_command(command: str) -> bool:
    cmd_lower = command.lower().strip()
    return any(blocked in cmd_lower for blocked in BLOCKED_PATTERNS)


def execute_bash(command: str, working_dir: str | None = None, timeout: int = BASH_TIMEOUT) -> str:
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=working_dir,
        )

        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            if output:
                output += "\n"
            output += f"[stderr]\n{result.stderr}"

        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"

        if len(output) > BASH_OUTPUT_LIMIT:
            output = output[:BASH_OUTPUT_LIMIT] + "\n... [truncated]"

        return output if output else "(no output)"

    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"


class BashInput(BaseModel):
    command: str = Field(description="The shell command to execute")
    working_dir: str | None = Field(default=None, description="Working directory (optional, defaults to current)")
    background: bool = Field(
        default=False, description="Run in background, return immediately. Results delivered automatically when done."
    )


class BashTool(Tool):
    name = "bash"
    display_name = "Bash"
    description = BASH_DESCRIPTION
    input_model = BashInput

    mutates = True

    def __init__(self, timeout: int = BASH_TIMEOUT):
        self.timeout = timeout

    async def approval_info(self, execution: ToolExecution, command: str, **kwargs: Any) -> ApprovalInfo | None:
        if not is_safe_command(command) and not is_blocked_command(command):
            return ApprovalInfo(description=command, preview=None, diff=None)
        return None

    async def execute(
        self,
        execution: ToolExecution,
        command: str,
        working_dir: str | None = None,
        background: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        if is_blocked_command(command):
            return ToolResult(content=f"Blocked: {command}", preview="Blocked", is_error=True)

        if not background:
            output = await asyncio.to_thread(execute_bash, command, working_dir, self.timeout)
            lines = output.count("\n") + 1
            return ToolResult(content=output, preview=f"{lines} lines")

        registry = execution.ctx.background_tasks
        task_id = registry.generate_id()

        async def _run_background():
            start = time.monotonic()
            try:
                output = await asyncio.to_thread(execute_bash, command, working_dir, self.timeout)
                status = "completed"
            except asyncio.CancelledError:
                return
            except Exception as e:
                output = f"Error: {e}"
                status = "failed"
                _logger.warning("Background task %s failed: %s", task_id, e)
            duration_ms = int((time.monotonic() - start) * 1000)

            synthetic_call_id = f"bg_{task_id}"
            messages = [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": synthetic_call_id,
                            "type": "function",
                            "function": {
                                "name": "background_result",
                                "arguments": json.dumps({"task_id": task_id, "command": command}),
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": synthetic_call_id,
                    "content": output,
                },
            ]

            emit = execution.ctx.io.emit
            if emit:
                await emit(
                    ToolCallEvent(
                        tool_id=synthetic_call_id,
                        name="bash",
                        args={"command": command},
                        display_name="Bash",
                    )
                )
                lines = output.count("\n") + 1
                await emit(
                    ToolResultEvent(
                        tool_id=synthetic_call_id,
                        name="bash",
                        result=output,
                        preview=f"{lines} lines" if status == "completed" else "failed",
                        duration_ms=duration_ms,
                        display_name="Bash",
                    )
                )
                await emit(BackgroundTaskEvent(task_id=task_id, command=command, status=status))

            await registry.inject(messages)

        task = asyncio.create_task(_run_background())
        registry.register(task_id, task, command=command)

        if execution.ctx.io.emit:
            await execution.ctx.io.emit(BackgroundTaskEvent(task_id=task_id, command=command, status="started"))

        return ToolResult(
            content=f"Background task {task_id} started: {command}",
            preview=f"Background · {task_id}",
        )
