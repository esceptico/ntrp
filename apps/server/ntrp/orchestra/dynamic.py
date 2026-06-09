import ast
import json
import textwrap
import traceback
from typing import Any

from pydantic import BaseModel, Field

from ntrp.orchestra.engine import Orchestra

_SCRIPT_FILENAME = "<workflow-script>"
# The script body is wrapped as the body of `async def __workflow__():`, which
# occupies source line 1. Shift compiled line numbers back by this so the errors
# the model sees point at the lines it actually wrote.
_WRAPPER_OFFSET = 1


def _normalize(script: str) -> str:
    return script.strip() or "return None"


def _exception_messages(exc: BaseException) -> list[str]:
    # Unwrap TaskGroup ExceptionGroups (e.g. a spawn-cap WorkflowSpawnLimit raised
    # inside parallel/pipeline) so the real leaf message surfaces instead of the
    # bare "N sub-exceptions" summary.
    if isinstance(exc, BaseExceptionGroup):
        out: list[str] = []
        for sub in exc.exceptions:
            out += _exception_messages(sub)
        return out
    return traceback.format_exception_only(type(exc), exc)


def format_script_traceback(exc: BaseException, script: str) -> str:
    """Traceback trimmed to the model's own script frames, so a failing dynamic
    workflow points at the line the model wrote rather than ntrp internals. Source
    text is rendered from `script` directly (no linecache — a shared key would let
    concurrent workflows clobber each other's registration)."""
    src_lines = _normalize(script).splitlines()
    frames = [f for f in traceback.extract_tb(exc.__traceback__) if f.filename == _SCRIPT_FILENAME]
    parts: list[str] = []
    if frames:
        parts.append("Traceback (most recent call last):\n")
        for f in frames:
            parts.append(f'  File "{f.filename}", line {f.lineno}, in {f.name}\n')
            if f.lineno and 1 <= f.lineno <= len(src_lines):
                parts.append(f"    {src_lines[f.lineno - 1].strip()}\n")
    parts += _exception_messages(exc)
    return "".join(parts)


async def run_script(orchestra: Orchestra, script: str, args: dict) -> Any:
    """Execute a model-authored orchestration script — a 'harness for the task'.

    The script body runs as the body of an async function with the combinators in
    scope (no imports needed): `agent`, `parallel`, `pipeline`, `phase`, `log`,
    plus `args`, `json`, and pydantic `BaseModel`/`Field` for optional inline
    schemas. It uses `await` and `return`s the result.

    Runs IN-PROCESS because it must reach `spawn_fn`. This is NOT a security
    sandbox: the agent already has a `bash` tool (arbitrary execution), so exec'ing
    its own orchestration adds no capability. Robustness — not isolation — is
    bounded by the Orchestra (global concurrency cap + per-run spawn cap) and the
    calling tool (error capture + lifecycle events).
    """
    source = f"async def __workflow__():\n{textwrap.indent(_normalize(script), '    ')}\n"
    try:
        tree = ast.parse(source, _SCRIPT_FILENAME, "exec")
    except SyntaxError as exc:
        if exc.lineno is not None:
            exc.lineno = max(1, exc.lineno - _WRAPPER_OFFSET)
        raise
    ast.increment_lineno(tree, -_WRAPPER_OFFSET)
    tree.body[0].lineno = 1  # synthetic wrapper frame; keep a valid line number
    namespace: dict[str, Any] = {
        "o": orchestra,
        "args": args,
        "agent": orchestra.agent,
        "parallel": orchestra.parallel,
        "pipeline": orchestra.pipeline,
        "phase": orchestra.phase,
        "log": orchestra.log,
        "budget": orchestra.budget_view,
        "json": json,
        "BaseModel": BaseModel,
        "Field": Field,
    }
    exec(compile(tree, _SCRIPT_FILENAME, "exec"), namespace)
    return await namespace["__workflow__"]()
