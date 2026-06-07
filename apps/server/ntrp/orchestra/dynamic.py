import json
import textwrap
from typing import Any

from pydantic import BaseModel, Field

from ntrp.orchestra.engine import Orchestra


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
    body = textwrap.indent(script.strip() or "return None", "    ")
    source = f"async def __workflow__():\n{body}\n"
    namespace: dict[str, Any] = {
        "o": orchestra,
        "args": args,
        "agent": orchestra.agent,
        "parallel": orchestra.parallel,
        "pipeline": orchestra.pipeline,
        "phase": orchestra.phase,
        "log": orchestra.log,
        "json": json,
        "BaseModel": BaseModel,
        "Field": Field,
    }
    exec(compile(source, "<workflow-script>", "exec"), namespace)
    return await namespace["__workflow__"]()
