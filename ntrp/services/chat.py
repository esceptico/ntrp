from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

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
from ntrp.memory.formatting import format_session_memory
from ntrp.server.state import RunState, RunStatus
from ntrp.server.stream import run_agent_loop, to_sse
from ntrp.skills.registry import SkillRegistry
from ntrp.tools.core.context import IOBridge
from ntrp.tools.directives import load_directives

INIT_AUTO_APPROVE = {"remember", "forget"}


@dataclass
class ChatContext:
    runtime: Runtime
    run: RunState
    session_state: SessionState
    messages: list[dict]
    user_message: str
    is_init: bool


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


async def _resolve_session(runtime) -> SessionData:
    data = await runtime.restore_session()
    if not data:
        return SessionData(runtime.create_session(), [])
    return data


async def _prepare_messages(
    runtime,
    messages: list[dict],
    user_message: str,
    last_activity: datetime | None = None,
) -> tuple[list[dict], list[dict]]:
    memory_context = None
    if runtime.memory:
        user_facts = await runtime.memory.get_context()
        memory_context = format_session_memory(user_facts=user_facts) or None

    skills_context = runtime.skill_registry.to_prompt_xml() if runtime.skill_registry else None
    directives = load_directives()

    system_blocks = build_system_blocks(
        source_details=runtime.get_source_details(),
        last_activity=last_activity,
        memory_context=memory_context,
        skills_context=skills_context,
        directives=directives,
        use_cache_control=_is_anthropic(runtime.config.chat_model),
    )

    if not messages:
        messages = [{"role": "system", "content": system_blocks}]
    elif isinstance(messages[0], dict) and messages[0].get("role") == "system":
        messages[0]["content"] = system_blocks
    else:
        messages.insert(0, {"role": "system", "content": system_blocks})

    messages.append({"role": "user", "content": user_message})

    return messages, system_blocks


if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from ntrp.server.runtime import Runtime


class ChatService:
    def __init__(self, runtime: Runtime):
        self.runtime = runtime

    async def prepare(self, message: str, skip_approvals: bool = False) -> ChatContext:
        runtime = self.runtime
        registry = runtime.run_registry

        session_data = await _resolve_session(runtime)
        session_state = session_data.state
        messages = session_data.messages

        user_message = message
        is_init = user_message.strip().lower() == "/init"
        if is_init:
            user_message = INIT_INSTRUCTION
        elif runtime.skill_registry:
            user_message, _ = expand_skill_command(user_message, runtime.skill_registry)

        messages, system_blocks = await _prepare_messages(
            runtime, messages, user_message, last_activity=session_state.last_activity
        )

        run = registry.create_run(session_state.session_id)
        run.messages = messages
        run.status = RunStatus.RUNNING

        return ChatContext(
            runtime=runtime,
            run=run,
            session_state=session_state,
            messages=messages,
            user_message=user_message,
            is_init=is_init,
        )

    async def stream(self, ctx: ChatContext) -> AsyncGenerator[str]:
        runtime = ctx.runtime
        run = ctx.run
        session_state = ctx.session_state

        run.approval_queue = asyncio.Queue()
        run.choice_queue = asyncio.Queue()

        yield to_sse(
            SessionInfoEvent(
                session_id=session_state.session_id,
                run_id=run.run_id,
                sources=runtime.get_available_sources(),
                source_errors=runtime.get_source_errors(),
                skip_approvals=session_state.skip_approvals,
            )
        )

        yield to_sse(ThinkingEvent(status="processing..."))
        runtime.channel.publish(RunStarted(run_id=run.run_id, session_id=session_state.session_id))

        agent: Agent | None = None
        result: str | None = None
        try:
            agent = create_agent(
                executor=runtime.executor,
                model=runtime.config.chat_model,
                tools=runtime.tools,
                system_prompt=ctx.messages[0]["content"] if ctx.messages else [],
                session_state=session_state,
                memory=runtime.memory,
                channel=runtime.channel,
                max_depth=runtime.max_depth,
                explore_model=runtime.config.explore_model,
                run_id=run.run_id,
                cancel_check=lambda: run.cancelled,
                io=IOBridge(
                    approval_queue=run.approval_queue,
                    choice_queue=run.choice_queue,
                ),
                extra_auto_approve=INIT_AUTO_APPROVE if ctx.is_init else None,
            )

            async for sse in run_agent_loop(ctx, agent, ctx.user_message):
                if isinstance(sse, AgentResult):
                    result = sse.text
                else:
                    yield sse

            if result is None:
                return  # Cancelled — session saved in finally

            if result:
                yield to_sse(TextEvent(content=result))

            run.prompt_tokens = agent.total_input_tokens
            run.completion_tokens = agent.total_output_tokens
            run.cache_read_tokens = agent.total_cache_read_tokens
            run.cache_write_tokens = agent.total_cache_write_tokens
            run.cost = agent.total_cost

            yield to_sse(DoneEvent(run_id=run.run_id, usage=asdict(run.get_usage())))
            runtime.run_registry.complete_run(run.run_id)

        except Exception as e:
            yield to_sse(ErrorEvent(message=str(e), recoverable=False))
            run.status = RunStatus.ERROR

        finally:
            if agent:
                run.prompt_tokens = agent.total_input_tokens
                run.completion_tokens = agent.total_output_tokens
                run.cache_read_tokens = agent.total_cache_read_tokens
                run.cache_write_tokens = agent.total_cache_write_tokens
                run.cost = agent.total_cost
                run.messages = agent.messages
            session_state.last_activity = datetime.now(UTC)
            metadata = {"last_input_tokens": agent._last_input_tokens} if agent else None
            await runtime.save_session(session_state, run.messages, metadata=metadata)
            runtime.channel.publish(
                RunCompleted(
                    run_id=run.run_id,
                    prompt_tokens=run.prompt_tokens,
                    completion_tokens=run.completion_tokens,
                    cache_read_tokens=run.cache_read_tokens,
                    cache_write_tokens=run.cache_write_tokens,
                    result=result or "",
                )
            )

    async def compact(self) -> dict:
        runtime = self.runtime
        model = runtime.config.chat_model

        data = await runtime.restore_session()
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
            await runtime.save_session(
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
