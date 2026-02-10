import asyncio
import os

from ntrp.logging import get_logger

_logger = get_logger(__name__)


class BashNotifier:
    channel = "bash"

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
            _logger.error(
                "Bash notifier %r exited %d: %s",
                self._command,
                proc.returncode,
                stderr.decode().strip(),
            )
