import asyncio
import os
from typing import Any

from ntrp.notifiers.base import Notifier


class BashNotifier(Notifier):
    channel = "bash"

    @classmethod
    def from_config(cls, config: dict, runtime: Any) -> "BashNotifier":
        return cls(command=config["command"])

    def __init__(self, command: str):
        self._command = command

    async def send(self, subject: str, body: str) -> None:
        env = {**os.environ, "NTRP_SUBJECT": subject, "NTRP_BODY": body}
        proc = await asyncio.create_subprocess_shell(
            self._command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        _, stderr = await proc.communicate(input=body.encode())
        if proc.returncode != 0:
            raise RuntimeError(f"Bash notifier {self._command!r} exited {proc.returncode}: {stderr.decode().strip()}")
