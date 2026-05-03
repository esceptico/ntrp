from datetime import datetime

from fastapi import HTTPException, Request

from ntrp.config import Config, get_config
from ntrp.core.factory import AgentConfig
from ntrp.integrations import ALL_INTEGRATIONS, IntegrationRegistry
from ntrp.llm.router import close as llm_close
from ntrp.llm.router import init as llm_init
from ntrp.logging import get_logger
from ntrp.mcp.manager import MCPManager
from ntrp.notifiers.base import NotifierContext
from ntrp.notifiers.service import NotifierService
from ntrp.operator.runner import OperatorDeps
from ntrp.server.runtime.automation import AutomationRuntime
from ntrp.server.runtime.config import RuntimeConfig
from ntrp.server.runtime.knowledge import KnowledgeRuntime
from ntrp.server.state import RunRegistry
from ntrp.server.stores import Stores
from ntrp.services.session import SessionService
from ntrp.skills.registry import SkillRegistry
from ntrp.skills.service import SkillService, get_skills_dirs
from ntrp.tools.executor import ToolExecutor

_logger = get_logger(__name__)


class Runtime:
    def __init__(self, config: Config | None = None):
        initial_config = config or get_config()
        self.integrations = IntegrationRegistry(ALL_INTEGRATIONS)
        self.integrations.sync(initial_config)
        self.run_registry = RunRegistry()
        self.knowledge = KnowledgeRuntime(initial_config)

        self.stores: Stores | None = None
        self.automation: AutomationRuntime | None = None
        self.mcp_manager: MCPManager | None = None
        self.executor: ToolExecutor | None = None
        self.skill_registry: SkillRegistry | None = None
        self.skill_service: SkillService | None = None
        self.notifier_service: NotifierService | None = None

        self._connected = False
        self._closing = False

        self.config_runtime = RuntimeConfig(
            initial_config,
            get_integrations=lambda: self.integrations,
            get_knowledge=lambda: self.knowledge,
            get_stores=lambda: self.stores,
            sync_mcp=lambda config: self.sync_mcp(config),
            is_closing=lambda: self._closing,
        )

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def config(self) -> Config:
        return self.config_runtime.config

    @property
    def config_service(self):
        return self.config_runtime.service

    def config_status(self) -> dict[str, int | str]:
        return self.config_runtime.status()

    @property
    def session_service(self) -> SessionService | None:
        return self.stores.sessions if self.stores else None

    @property
    def embedding(self):
        return self.knowledge.embedding

    @property
    def indexer(self):
        return self.knowledge.indexer

    @property
    def memory(self):
        return self.knowledge.memory

    @property
    def memory_service(self):
        return self.knowledge.memory_service

    @property
    def search_index(self):
        return self.knowledge.search_index

    @property
    def scheduler(self):
        return self.automation.scheduler if self.automation else None

    @property
    def automation_service(self):
        return self.automation.automation_service if self.automation else None

    @property
    def monitor(self):
        return self.automation.monitor if self.automation else None

    @property
    def outbox_runtime(self):
        return self.automation.outbox_runtime if self.automation else None

    @property
    def outbox_worker(self):
        outbox_runtime = self.outbox_runtime
        return outbox_runtime.worker if outbox_runtime else None

    @property
    def tool_services(self) -> dict[str, object]:
        services: dict[str, object] = dict(self.integrations.clients)
        services.update(self.knowledge.tool_services())
        if self.automation_service:
            services["automation"] = self.automation_service
        if self.skill_registry:
            services["skill_registry"] = self.skill_registry
        if self.mcp_manager and self.mcp_manager.tools:
            services["mcp"] = self.mcp_manager
        if self.notifier_service and self.notifier_service.notifiers:
            services["notifiers"] = self.notifier_service
        return services

    def _create_executor(self) -> ToolExecutor:
        mcp_tools = list(self.mcp_manager.tools) if self.mcp_manager else None
        return ToolExecutor(
            mcp_tools=mcp_tools,
            get_services=lambda: self.tool_services,
        )

    # --- Subsystem lifecycle ---

    async def reload_config(self) -> None:
        await self.config_runtime.reload()

    async def sync_mcp(self, config: Config | None = None) -> None:
        config = config or self.config
        if self.mcp_manager:
            await self.mcp_manager.close()
            self.mcp_manager = None

        if config.mcp_servers:
            self.mcp_manager = MCPManager()
            await self.mcp_manager.connect(config.mcp_servers)

        if self.executor:
            self.executor = self._create_executor()

    # --- Connect / close ---

    async def connect(self) -> None:
        if self._connected:
            return

        llm_init(self.config)
        self.stores = await Stores.connect(self.config)
        await self.knowledge.connect(self.stores)
        self._init_skills()
        await self._init_notifiers()
        self._init_automation()
        await self._init_mcp()
        self._init_tools()

        self._connected = True
        _logger.info(
            "Runtime ready",
            integrations=len(self.integrations.clients),
            tools=len(self.executor.registry),
        )

    def _init_skills(self) -> None:
        self.skill_registry = SkillRegistry()
        self.skill_registry.load(get_skills_dirs())
        self.skill_service = SkillService(self.skill_registry)

    async def _init_notifiers(self) -> None:
        self.notifier_service = NotifierService(
            store=self.stores.notifiers,
            ctx=NotifierContext(
                get_source=lambda name: self.tool_services.get(name),
                get_config_value=lambda key: self.config.model_dump().get(key),
            ),
        )
        await self.notifier_service.seed_defaults()
        await self.notifier_service.rebuild()

    def _init_automation(self) -> None:
        self.automation = AutomationRuntime(
            stores=self.stores,
            build_operator_deps=self.build_operator_deps,
            get_memory=lambda: self.memory,
            get_calendar_source=lambda: self.integrations.get_client("calendar"),
            indexer=self.indexer,
        )

    async def _init_mcp(self) -> None:
        if self.config.mcp_servers:
            self.mcp_manager = MCPManager()
            await self.mcp_manager.connect(self.config.mcp_servers)

    def _init_tools(self) -> None:
        self.executor = self._create_executor()

    async def close(self) -> None:
        self._closing = True

        # Phase 1: stop accepting new work
        cancelled = await self.run_registry.cancel_all()
        if cancelled:
            _logger.info("Cancelled %d active run(s)", cancelled)

        # Phase 2: stop background services
        if self.automation:
            await self.automation.stop()
        await self.knowledge.stop()

        # Phase 3: close resources
        if self.mcp_manager:
            await self.mcp_manager.close()
        await self.knowledge.close()
        if self.stores:
            await self.stores.close()
        await llm_close()

    # --- Queries ---

    def get_available_integrations(self) -> list[str]:
        ids = list(self.integrations.clients.keys())
        if self.memory:
            ids.append("memory")
        return ids

    def get_integration_errors(self) -> dict[str, str]:
        errors = dict(self.integrations.errors)
        if self.indexer and self.indexer.error:
            errors["index"] = self.indexer.error
        return errors

    def build_chat_deps(self):
        if not self.executor or not self.session_service:
            raise RuntimeError("Chat dependencies are not initialized")
        from ntrp.services.chat import ChatDeps

        return ChatDeps(
            chat_model=self.config.chat_model,
            agent_config=AgentConfig.from_config(self.config),
            executor=self.executor,
            session_service=self.session_service,
            run_registry=self.run_registry,
            available_integrations=self.get_available_integrations(),
            integration_errors=self.get_integration_errors(),
            enqueue_run_completed=self.stores.outbox.enqueue_run_completed if self.stores else None,
            memory=self.memory,
            skill_registry=self.skill_registry,
            notifier_service=self.notifier_service,
        )

    # --- Background tasks ---

    def build_operator_deps(self) -> OperatorDeps:
        return OperatorDeps(
            executor=self.executor,
            memory=self.memory,
            config=AgentConfig.from_config(self.config),
            source_details={},
            create_session=self.stores.sessions.create,
            notifiers=self.notifier_service.list_summary() if self.notifier_service else [],
            enqueue_run_completed=self.stores.outbox.enqueue_run_completed,
        )

    async def start_scheduler(self) -> None:
        if not self.automation:
            raise RuntimeError("Automation runtime is not initialized")
        await self.automation.start_scheduler()

    def start_monitor(self) -> None:
        if not self.automation:
            raise RuntimeError("Automation runtime is not initialized")
        self.automation.start_monitor()

    async def sync_google_sources(self) -> None:
        self.integrations.sync(self.config)
        await self.restart_monitor()

    async def restart_monitor(self) -> None:
        if not self.automation:
            return
        await self.automation.restart_monitor()

    def start_indexing(self) -> None:
        self.knowledge.start_indexing()

    async def get_index_status(self) -> dict:
        return await self.knowledge.get_index_status()

    async def get_scheduler_status(self) -> dict:
        if not self.automation:
            return {"status": "disabled", "running_tasks": 0, "registered_handlers": []}
        return await self.automation.get_scheduler_status()

    async def get_chat_runs_status(self) -> dict:
        return self.run_registry.get_status()

    async def get_outbox_status(self) -> dict:
        if not self.automation:
            return {"status": "disabled"}
        return await self.automation.get_outbox_status()

    async def get_outbox_health(self) -> dict:
        if not self.automation:
            return {"worker_running": False, "pending": 0, "ready": 0, "running": 0, "dead": 0}
        return await self.automation.get_outbox_health()

    async def replay_outbox_dead_events(self, event_ids: list[int]) -> dict:
        if not self.automation:
            return {"status": "disabled", "requested": event_ids, "replayed": [], "missing": event_ids, "skipped": []}
        return await self.automation.replay_outbox_dead_events(event_ids)

    async def prune_outbox_completed(self, *, before: datetime, limit: int) -> dict:
        if not self.automation:
            return {"status": "disabled", "deleted": 0, "before": before.isoformat(), "limit": limit}
        return await self.automation.prune_outbox_completed(before=before, limit=limit)


def get_runtime(request: Request) -> Runtime:
    try:
        runtime: Runtime | None = request.app.state.runtime
    except AttributeError:
        runtime = None
    if runtime is None or not runtime.connected:
        raise HTTPException(status_code=503, detail="Server is initializing")
    return runtime
