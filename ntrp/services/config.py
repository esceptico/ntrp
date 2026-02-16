import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import HTTPException

from ntrp.config import Config, load_user_settings, save_user_settings
from ntrp.llm.models import EMBEDDING_DEFAULTS
from ntrp.tools.directives import load_directives, save_directives

if TYPE_CHECKING:
    from ntrp.server.indexer import Indexer
    from ntrp.server.sources import SourceManager


class ConfigService:
    def __init__(
        self,
        config: Config,
        source_mgr: "SourceManager",
        indexer: "Indexer",
        reinit_memory_fn,
        rebuild_executor_fn,
        start_indexing_fn,
        start_reembed_fn,
        config_lock: asyncio.Lock,
        get_max_depth,
        set_max_depth,
    ):
        self.config = config
        self.source_mgr = source_mgr
        self.indexer = indexer
        self._reinit_memory = reinit_memory_fn
        self._rebuild_executor = rebuild_executor_fn
        self._start_indexing = start_indexing_fn
        self._start_reembed = start_reembed_fn
        self._config_lock = config_lock
        self._get_max_depth = get_max_depth
        self._set_max_depth = set_max_depth

    async def update(self, req) -> dict:
        async with self._config_lock:
            settings = load_user_settings()

            if req.chat_model:
                self.config.chat_model = req.chat_model
                settings["chat_model"] = req.chat_model
            if req.explore_model:
                self.config.explore_model = req.explore_model
                settings["explore_model"] = req.explore_model
            if req.memory_model:
                self.config.memory_model = req.memory_model
                settings["memory_model"] = req.memory_model
            if req.chat_model or req.explore_model or req.memory_model:
                save_user_settings(settings)

            if req.max_depth is not None:
                self._set_max_depth(req.max_depth)

            if req.vault_path is not None:
                if req.vault_path == "":
                    self.config.vault_path = None
                    await self.source_mgr.remove("notes")
                    settings.pop("vault_path", None)
                else:
                    vault_path = Path(req.vault_path).expanduser()
                    if not vault_path.exists():
                        raise HTTPException(status_code=400, detail=f"Vault path does not exist: {vault_path}")
                    self.config.vault_path = vault_path
                    await self.source_mgr.reinit("notes", self.config)
                    settings["vault_path"] = str(vault_path)
                save_user_settings(settings)

            if req.browser is not None or req.browser_days is not None:
                browser = req.browser if req.browser is not None else self.config.browser
                browser_days = req.browser_days if req.browser_days is not None else self.config.browser_days

                if browser == "" or browser == "none":
                    browser = None

                self.config.browser = browser
                self.config.browser_days = browser_days
                if browser:
                    await self.source_mgr.reinit("browser", self.config)
                else:
                    await self.source_mgr.remove("browser")

                if browser:
                    settings["browser"] = browser
                else:
                    settings.pop("browser", None)
                settings["browser_days"] = browser_days
                save_user_settings(settings)

            if req.sources:
                sources_settings = settings.setdefault("sources", {})

                if req.sources.gmail is not None:
                    self.config.gmail = req.sources.gmail
                    sources_settings["gmail"] = req.sources.gmail
                    if req.sources.gmail:
                        await self.source_mgr.reinit("email", self.config)
                    else:
                        await self.source_mgr.remove("email")

                if req.sources.calendar is not None:
                    self.config.calendar = req.sources.calendar
                    sources_settings["calendar"] = req.sources.calendar
                    if req.sources.calendar:
                        await self.source_mgr.reinit("calendar", self.config)
                    else:
                        await self.source_mgr.remove("calendar")

                if req.sources.memory is not None:
                    self.config.memory = req.sources.memory
                    sources_settings["memory"] = req.sources.memory
                    await self._reinit_memory(req.sources.memory)

                save_user_settings(settings)

        return {
            "chat_model": self.config.chat_model,
            "memory_model": self.config.memory_model,
            "max_depth": self._get_max_depth(),
            "vault_path": str(self.config.vault_path) if self.config.vault_path else None,
            "browser": self.config.browser,
            "has_notes": self.config.vault_path is not None and self.source_mgr.sources.get("notes") is not None,
            "has_browser": self.config.browser is not None,
        }

    async def update_embedding(self, model_id: str) -> dict:
        valid_embedding = {m.id for m in EMBEDDING_DEFAULTS}
        if model_id not in valid_embedding:
            raise HTTPException(status_code=400, detail=f"Unknown model: {model_id}")

        if model_id == self.config.embedding_model:
            return {"status": "unchanged", "embedding_model": model_id}

        self.config.embedding_model = model_id

        settings = load_user_settings()
        settings["embedding_model"] = model_id
        save_user_settings(settings)

        await self.indexer.update_embedding(self.config.embedding)
        self._start_indexing()

        self._start_reembed(self.config.embedding)

        return {
            "status": "reindexing",
            "embedding_model": model_id,
            "embedding_dim": self.config.embedding.dim,
        }

    def get_summary(self, *, memory_connected: bool) -> dict:
        has_google = self.source_mgr.has_google_auth()
        return {
            "chat_model": self.config.chat_model,
            "explore_model": self.config.explore_model,
            "memory_model": self.config.memory_model,
            "embedding_model": self.config.embedding_model,
            "vault_path": self.config.vault_path,
            "browser": self.config.browser,
            "gmail_enabled": self.config.gmail,
            "has_browser": self.config.browser is not None,
            "has_notes": self.config.vault_path is not None
            and self.source_mgr.sources.get("notes") is not None,
            "max_depth": self._get_max_depth(),
            "memory_enabled": memory_connected,
            "sources": {
                "gmail": {"enabled": self.config.gmail, "connected": has_google},
                "calendar": {"enabled": self.config.calendar, "connected": has_google},
                "memory": {"enabled": self.config.memory, "connected": memory_connected},
                "web": {"connected": "web" in self.source_mgr.sources},
                "notes": {
                    "connected": "notes" in self.source_mgr.sources,
                    "path": str(self.config.vault_path) if self.config.vault_path else None,
                },
                "browser": {
                    "connected": "browser" in self.source_mgr.sources,
                    "type": self.config.browser,
                },
            },
        }

    def update_directives(self, content: str) -> dict:
        save_directives(content)
        return {"content": content.strip()}

    def get_directives(self) -> dict:
        return {"content": load_directives() or ""}
