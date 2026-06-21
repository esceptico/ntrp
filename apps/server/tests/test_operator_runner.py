from datetime import UTC, datetime
from pathlib import Path

import pytest

from ntrp.context.models import SessionState
from ntrp.core.factory import AgentConfig
from ntrp.operator import runner
from ntrp.operator.runner import OperatorDeps, RunRequest
from ntrp.skills.registry import SkillRegistry


def _write_skill(root: Path, name: str, description: str) -> None:
    skill_dir = root / name
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# Body\n"
    )


class FakeExecutor:
    def get_tools(self, read_only: bool = False) -> list[dict]:
        return []


def _deps(skill_registry: SkillRegistry | None) -> OperatorDeps:
    return OperatorDeps(
        executor=FakeExecutor(),
        config=AgentConfig(model="test-model", research_model=None, max_depth=1, deferred_tools=False),
        source_details={},
        create_session=lambda: SessionState(
            session_id="s1",
            started_at=datetime.now(UTC),
            name="test",
        ),
        notifiers=[],
        skill_registry=skill_registry,
    )


@pytest.mark.asyncio
async def test_prepare_includes_skill_inventory_in_system_prompt(tmp_path, monkeypatch):
    _write_skill(tmp_path, "operator-helper", "Helps operator runs use skills")
    registry = SkillRegistry()
    registry.load([(tmp_path, "project")])
    monkeypatch.setattr(runner, "create_agent", lambda **kwargs: object())

    _, messages, _, _ = await runner._prepare(
        _deps(registry),
        RunRequest(prompt="do it", auto_approve=True, source_id="test"),
    )

    system_prompt = messages[0]["content"]
    assert "<available_skills>" in system_prompt
    assert "operator-helper" in system_prompt
    assert "Helps operator runs use skills" in system_prompt


@pytest.mark.asyncio
async def test_prepare_allows_missing_skill_registry(monkeypatch):
    monkeypatch.setattr(runner, "create_agent", lambda **kwargs: object())

    _, messages, _, _ = await runner._prepare(
        _deps(None),
        RunRequest(prompt="do it", auto_approve=True, source_id="test"),
    )

    assert "<available_skills>" not in messages[0]["content"]
