from ntrp.config import Config
from ntrp.integrations.base import Integration
from ntrp.integrations.obsidian.client import ObsidianClient
from ntrp.integrations.obsidian.tools import (
    create_note_tool,
    delete_note_tool,
    edit_note_tool,
    move_note_tool,
    notes_tool,
    read_note_tool,
)


def _build(config: Config) -> ObsidianClient | None:
    if config.vault_path is None:
        return None
    return ObsidianClient(vault_path=config.vault_path)


OBSIDIAN = Integration(
    id="notes",
    label="Obsidian",
    tools={
        "notes": notes_tool,
        "read_note": read_note_tool,
        "edit_note": edit_note_tool,
        "create_note": create_note_tool,
        "delete_note": delete_note_tool,
        "move_note": move_note_tool,
    },
    build=_build,
)
