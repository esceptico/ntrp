from collections.abc import Callable
from dataclasses import replace

from ntrp.agent.model_request import ModelRequest, ModelRequestNext
from ntrp.tools.core.context import RunContext
from ntrp.tools.core.registry import ToolRegistry
from ntrp.tools.deferred import visible_tool_names


class DeferredToolsModelRequestMiddleware:
    """Replace the request tool list with always-visible + run-loaded tools."""

    def __init__(
        self,
        *,
        registry: ToolRegistry,
        run: RunContext,
        get_services: Callable[[], dict],
    ):
        self._registry = registry
        self._run = run
        self._get_services = get_services

    async def __call__(self, request: ModelRequest, next_request: ModelRequestNext) -> ModelRequest:
        if not self._run.deferred_tools_enabled:
            return await next_request(request)

        # Preserve upstream filtering. Operator/read-only paths may pass only non-mutating
        # schemas into Agent.tools; deferred loading must not re-add tools excluded there.
        allowed = {t.get("function", {}).get("name") for t in request.tools}
        allowed.discard(None)
        capabilities = frozenset(self._get_services())
        names = visible_tool_names(
            self._registry,
            capabilities,
            self._run.loaded_tools,
            allowed_names=set(allowed),
        )
        prepared = replace(
            request,
            tools=self._registry.get_schemas(capabilities=capabilities, names=names),
        )
        return await next_request(prepared)
