import asyncio
from collections.abc import AsyncGenerator
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from ntrp.channel import Channel
from ntrp.context.compression import compress_context_async, find_compressible_range
from ntrp.context.models import SessionData, SessionState
from ntrp.core.agent import Agent
from ntrp.core.factory import create_agent
from ntrp.core.prompts import INIT_INSTRUCTION, build_system_blocks
from ntrp.events.internal import RunCompleted, RunStarted
from ntrp.events.sse import (
    AgentResult,
    DoneEvent,
    ErrorEvent,
    SessionInfoEvent,
    TextEvent,
    ThinkingEvent,
)
from ntrp.llm.models import Provider, get_model
from ntrp.logging import get_logger
from ntrp.memory.facts import FactMemory
from ntrp.memory.formatting import format_session_memory
from ntrp.server.state import RunRegistry, RunState, RunStatus
from ntrp.server.stream import run_agent_loop
from ntrp.services.session import SessionService
from ntrp.skills.registry import SkillRegistry
from ntrp.tools.core.context import IOBridge
from ntrp.tools.directives import load_directives
from ntrp.tools.executor import ToolExecutor

if TYPE_CHECKING:
    from ntrp.server.runtime import Runtime


_logger = get_logger(__name__)

INIT_AUTO_APPROVE = {"remember", "forget"}


@dataclass
class ChatContext:
    run: RunState
    session_state: SessionState
    is_init: bool
    executor: ToolExecutor
    tools: list[dict]
    model: str
    explore_model: str | None
    memory: FactMemory | None
    channel: Channel
    max_depth: int
    available_sources: list[str]
    source_errors: dict[str, str]
    session_service: SessionService
    run_registry: RunRegistry


def expand_skill_command(message: str, registry: SkillRegistry) -> tuple[str, bool]:
    stripped = message.strip()
    if not stripped.startswith("/"):
        return message, False
    parts = stripped[1:].split(None, 1)
    skill_name = parts[0]
    args = parts[1] if len(parts) > 1 else ""
    body = registry.load_body(skill_name)
    if body is None:
        return message, False
    expanded = f'<skill name="{skill_name}">\n{body}\n</skill>'
    if args:
        expanded += f"\n\nUser request: {args}"
    return expanded, True


def _is_anthropic(model: str) -> bool:
    return get_model(model).provider == Provider.ANTHROPIC


class ChatService:
    def __init__(self, runtime: "Runtime"):
        self.runtime = runtime

    async def _resolve_session(self) -> SessionData:
        data = await self.runtime.session_service.load()
        if data and data.messages and len(data.messages) >= 2:
            return data
        return SessionData(self.runtime.session_service.create(), [])

    async def _prepare_messages(
        self,
        messages: list[dict],
        user_message: str,
        last_activity: datetime | None = None,
    ) -> list[dict]:
        runtime = self.runtime
        memory_context = None
        if runtime.memory:
            observations, user_facts = await runtime.memory.get_context()
            memory_context = format_session_memory(observations=observations, user_facts=user_facts)

        skills_context = runtime.skill_registry.to_prompt_xml() if runtime.skill_registry else None
        directives = load_directives()

        system_blocks = build_system_blocks(
            source_details=runtime.source_mgr.get_details(),
            last_activity=last_activity,
            memory_context=memory_context,
            skills_context=skills_context,
            directives=directives,
            use_cache_control=_is_anthropic(runtime.config.chat_model),
        )

        if not messages:
            messages = [{"role": "system", "content": system_blocks}]
        elif isinstance(messages[0], dict) and messages[0]["role"] == "system":
            messages[0]["content"] = system_blocks
        else:
            messages.insert(0, {"role": "system", "content": system_blocks})

        messages.append({"role": "user", "content": user_message})

        return messages

    async def prepare(self, message: str, skip_approvals: bool = False, session_id: str | None = None) -> ChatContext:
        runtime = self.runtime
        registry = runtime.run_registry

        if session_id:
            session_data = await runtime.session_service.load(session_id)
            if not session_data:
                session_data = SessionData(runtime.session_service.create(), [])
        else:
            session_data = await self._resolve_session()
        session_state = session_data.state
        session_state.skip_approvals = skip_approvals
        messages = session_data.messages

        user_message = message
        is_init = user_message.strip().lower() == "/init"
        if is_init:
            user_message = INIT_INSTRUCTION
        elif runtime.skill_registry:
            user_message, _ = expand_skill_command(user_message, runtime.skill_registry)

        if not session_state.name and not is_init and not message.strip().startswith("/"):
            session_state.name = message.strip()[:50]

        messages = await self._prepare_messages(messages, user_message, last_activity=session_state.last_activity)

        run = registry.create_run(session_state.session_id)
        run.messages = messages
        run.status = RunStatus.RUNNING

        return ChatContext(
            run=run,
            session_state=session_state,
            is_init=is_init,
            executor=runtime.executor,
            tools=runtime.executor.get_tools(),
            model=runtime.config.chat_model,
            explore_model=runtime.config.explore_model,
            memory=runtime.memory,
            channel=runtime.channel,
            max_depth=runtime.config.max_depth,
            available_sources=runtime.get_available_sources(),
            source_errors=runtime.get_source_errors(),
            session_service=runtime.session_service,
            run_registry=runtime.run_registry,
        )

    async def stream(self, ctx: ChatContext) -> AsyncGenerator[str]:
        run = ctx.run
        session_state = ctx.session_state

        run.approval_queue = asyncio.Queue()
        run.choice_queue = asyncio.Queue()

        yield SessionInfoEvent(
            session_id=session_state.session_id,
            run_id=run.run_id,
            sources=ctx.available_sources,
            source_errors=ctx.source_errors,
            skip_approvals=session_state.skip_approvals,
            session_name=session_state.name or "",
        ).to_sse_string()

        yield ThinkingEvent(status="processing...").to_sse_string()
        ctx.channel.publish(RunStarted(run_id=run.run_id, session_id=session_state.session_id))

        agent: Agent | None = None
        result: str | None = None
        try:
            agent = create_agent(
                executor=ctx.executor,
                model=ctx.model,
                tools=ctx.tools,
                system_prompt=ctx.run.messages[0]["content"] if ctx.run.messages else [],
                session_state=session_state,
                memory=ctx.memory,
                channel=ctx.channel,
                max_depth=ctx.max_depth,
                explore_model=ctx.explore_model,
                run_id=run.run_id,
                cancel_check=lambda: run.cancelled,
                io=IOBridge(
                    approval_queue=run.approval_queue,
                    choice_queue=run.choice_queue,
                ),
                extra_auto_approve=INIT_AUTO_APPROVE if ctx.is_init else None,
            )

            async for sse in run_agent_loop(ctx, agent):
                if isinstance(sse, AgentResult):
                    result = sse.text
                else:
                    yield sse

            if result is None:
                return  # Cancelled — session saved in finally

            if result:
                yield TextEvent(content=result).to_sse_string()

            yield DoneEvent(run_id=run.run_id, usage=asdict(run.get_usage())).to_sse_string()
            ctx.run_registry.complete_run(run.run_id)

        except Exception as e:
            _logger.exception("Chat stream failed (run_id=%s, session_id=%s)", run.run_id, session_state.session_id)
            yield ErrorEvent(message=str(e), recoverable=False).to_sse_string()
            run.status = RunStatus.ERROR

        finally:
            if agent:
                run.prompt_tokens = agent.total_input_tokens
                run.completion_tokens = agent.total_output_tokens
                run.cache_read_tokens = agent.total_cache_read_tokens
                run.cache_write_tokens = agent.total_cache_write_tokens
                run.cost = agent.total_cost
                run.messages = agent.messages
            last_tokens = getattr(agent, "_last_input_tokens", None) if agent else None
            metadata = {"last_input_tokens": last_tokens} if last_tokens is not None else None
            await ctx.session_service.save(session_state, run.messages, metadata=metadata)
            ctx.channel.publish(
                RunCompleted(
                    run_id=run.run_id,
                    prompt_tokens=run.prompt_tokens,
                    completion_tokens=run.completion_tokens,
                    cache_read_tokens=run.cache_read_tokens,
                    cache_write_tokens=run.cache_write_tokens,
                    result=result,
                )
            )

    async def compact(self, session_id: str | None = None) -> dict:
        runtime = self.runtime
        model = runtime.config.chat_model

        data = await runtime.session_service.load(session_id)
        if not data:
            return {"status": "no_session", "message": "No active session to compact"}

        session_state = data.state
        messages = data.messages
        before_count = len(messages)
        before_tokens = data.last_input_tokens

        start, end = find_compressible_range(messages)
        if start == 0 and end == 0:
            return {
                "status": "nothing_to_compact",
                "message": f"Nothing to compact ({before_count} messages)",
                "message_count": before_count,
            }

        msg_count = end - start
        new_messages, was_compressed = await compress_context_async(
            messages=messages,
            model=model,
            force=True,
        )

        if was_compressed:
            await runtime.session_service.save(
                session_state,
                new_messages,
                metadata={"last_input_tokens": None},
            )
            return {
                "status": "compacted",
                "message": f"Compacted {before_count} → {len(new_messages)} messages ({msg_count} summarized)",
                "before_tokens": before_tokens,
                "before_messages": before_count,
                "after_messages": len(new_messages),
                "messages_compressed": msg_count,
            }

        return {
            "status": "already_optimal",
            "message": f"Context already optimal ({before_count} messages)",
            "message_count": before_count,
        }
