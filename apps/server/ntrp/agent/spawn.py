import asyncio

from ntrp.agent.agent import Agent
from ntrp.agent.hooks import AgentHooks
from ntrp.agent.llm.client import LLMClient
from ntrp.agent.tools.executor import AgentToolExecutor
from ntrp.agent.types.llm import Role


class SpawnContext:
    def __init__(
        self,
        client: LLMClient,
        executor: AgentToolExecutor,
        max_depth: int = 3,
        hooks: AgentHooks | None = None,
    ):
        self.client = client
        self.executor = executor
        self.max_depth = max_depth
        self.hooks = hooks

    def child_agent(
        self,
        tools: list[dict],
        model: str,
        current_depth: int,
        hooks: AgentHooks | None = None,
    ) -> Agent:
        return Agent(
            tools=tools,
            client=self.client,
            executor=self.executor,
            model=model,
            max_depth=self.max_depth,
            current_depth=current_depth,
            hooks=hooks or self.hooks,
        )

    async def spawn(
        self,
        task: str,
        *,
        system_prompt: str,
        tools: list[dict],
        model: str,
        current_depth: int,
        timeout: int = 300,
        hooks: AgentHooks | None = None,
    ) -> str:
        child = self.child_agent(
            tools=tools,
            model=model,
            current_depth=current_depth,
            hooks=hooks,
        )
        messages = [
            {"role": Role.SYSTEM, "content": system_prompt},
            {"role": Role.USER, "content": task},
        ]
        result = await asyncio.wait_for(child.run(messages), timeout=timeout)
        return result.text
