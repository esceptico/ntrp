from ntrp.config import Config
from ntrp.integrations.base import Integration
from ntrp.integrations.obsidian.client import ObsidianClient
from ntrp.integrations.obsidian.tools import (
    CreateNoteTool,
    DeleteNoteTool,
    EditNoteTool,
    MoveNoteTool,
    NotesTool,
    ReadNoteTool,
)


def _build(config: Config) -> ObsidianClient | None:
    if config.vault_path is None:
        return None
    return ObsidianClient(vault_path=config.vault_path)


OBSIDIAN = Integration(
    id="notes",
    label="Obsidian",
    tools=[NotesTool, ReadNoteTool, EditNoteTool, CreateNoteTool, DeleteNoteTool, MoveNoteTool],
    build=_build,
)
