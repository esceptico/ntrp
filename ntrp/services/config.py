from pathlib import Path
from typing import TYPE_CHECKING

from ntrp.config import PERSIST_KEYS, load_user_settings, save_user_settings

if TYPE_CHECKING:
    from ntrp.server.runtime import Runtime


class ConfigService:
    def __init__(self, runtime: "Runtime"):
        self.runtime = runtime

    async def update(self, **fields) -> None:
        if "vault_path" in fields:
            path = fields["vault_path"]
            if path:
                vault = Path(path).expanduser()
                if not vault.exists():
                    raise ValueError(f"Vault path does not exist: {vault}")
                fields["vault_path"] = str(vault)
            else:
                fields["vault_path"] = None

        persist = {k: v for k, v in fields.items() if k in PERSIST_KEYS}
        if not persist:
            return

        settings = load_user_settings()
        backup = dict(settings)
        for key, value in persist.items():
            if value is None:
                settings.pop(key, None)
            else:
                settings[key] = value
        save_user_settings(settings)

        try:
            await self.runtime.reload_config()
        except Exception:
            save_user_settings(backup)
            raise
