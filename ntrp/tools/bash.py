import shlex
import subprocess
from typing import Any

from pydantic import BaseModel, Field

from ntrp.constants import BASH_OUTPUT_LIMIT
from ntrp.tools.core.base import ApprovalInfo, Tool, ToolResult
from ntrp.tools.core.context import ToolExecution

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

BASH_DESCRIPTION = """Execute a bash command in the user's shell.

PREFER OTHER TOOLS:
- For searching files: use search() instead of grep/find
- For reading files: use read_note() or read_file()
- For editing files: use edit_note() or create_note()

USE bash FOR:
- System commands: git, npm, pip, brew
- File operations: mkdir, cp, mv (with permission)
- Checking system state: pwd, whoami, date

SAFETY: Destructive commands (rm -rf) are blocked. Non-safe commands require approval."""


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


def execute_bash(command: str, working_dir: str | None = None, timeout: int = 30) -> str:
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


class BashTool(Tool):
    name = "bash"
    description = BASH_DESCRIPTION
    input_model = BashInput

    mutates = True

    def __init__(self, working_dir: str | None = None, timeout: int = 30):
        self.working_dir = working_dir
        self.timeout = timeout

    async def approval_info(self, command: str = "", **kwargs: Any) -> ApprovalInfo | None:
        if command and not is_safe_command(command) and not is_blocked_command(command):
            return ApprovalInfo(description=command, preview=None, diff=None)
        return None

    async def execute(
        self, execution: ToolExecution, command: str = "", working_dir: str | None = None, **kwargs: Any
    ) -> ToolResult:
        if not command:
            return ToolResult(content="Error: command is required", preview="Missing command", is_error=True)
        if is_blocked_command(command):
            return ToolResult(content=f"Blocked: {command}", preview="Blocked", is_error=True)

        cwd = working_dir or self.working_dir
        output = execute_bash(command, cwd, self.timeout)
        lines = output.count("\n") + 1
        return ToolResult(content=output, preview=f"{lines} lines")
