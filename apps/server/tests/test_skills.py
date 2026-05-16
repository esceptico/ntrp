from pathlib import Path

from fastapi.testclient import TestClient

from ntrp.server.app import app
from ntrp.server.deps import require_skill_service
from ntrp.skills.registry import SkillRegistry
from ntrp.skills.service import SkillService, get_skills_dirs


def _write_skill(root: Path, name: str, frontmatter: str, body: str = "# Body\n") -> None:
    skill_dir = root / name
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(f"---\n{frontmatter}---\n\n{body}")


def test_builtin_obsidian_skill_is_registered():
    registry = SkillRegistry()
    registry.load(get_skills_dirs())

    skill = registry.get("obsidian")

    assert skill is not None
    assert skill.location == "builtin"


def test_registry_rejects_invalid_skill_metadata(tmp_path):
    _write_skill(
        tmp_path,
        "Bad_Name",
        "name: Bad_Name\ndescription: works\n",
    )
    registry = SkillRegistry()

    registry.load([(tmp_path, "project")])

    assert registry.get("Bad_Name") is None
    assert registry.validation_issues[0]["reason"] == "invalid_name"
    assert registry.validation_issues[0]["path"].endswith("Bad_Name/SKILL.md")


def test_registry_loads_skill_governance_metadata(tmp_path):
    _write_skill(
        tmp_path,
        "research-helper",
        (
            "name: research-helper\n"
            "description: Helps with research\n"
            "source: github:example/research-helper\n"
            "version: 2026-05-16\n"
            "reviewed_at: 2026-05-16\n"
        ),
    )
    registry = SkillRegistry()

    registry.load([(tmp_path, "project")])

    skill = registry.get("research-helper")
    assert skill is not None
    assert skill.source == "github:example/research-helper"
    assert skill.version == "2026-05-16"
    assert skill.reviewed_at == "2026-05-16"


def test_skill_service_governance_report_marks_cleanup_candidates(tmp_path):
    _write_skill(
        tmp_path,
        "old-helper",
        (
            "name: old-helper\n"
            "description: Old helper\n"
            "reviewed_at: 2025-01-01\n"
        ),
    )
    registry = SkillRegistry()
    registry.load([(tmp_path, "project")])
    service = SkillService(registry)

    report = service.governance_report(now_date="2026-05-16")

    assert report["summary"]["cleanup_candidate_count"] == 1
    assert report["cleanup_candidates"][0]["name"] == "old-helper"
    assert report["cleanup_candidates"][0]["reason"] == "review_stale"
    assert registry.get("old-helper") is not None


def test_skill_governance_endpoint_returns_report(tmp_path):
    _write_skill(
        tmp_path,
        "old-helper",
        (
            "name: old-helper\n"
            "description: Old helper\n"
            "reviewed_at: 2025-01-01\n"
        ),
    )
    registry = SkillRegistry()
    registry.load([(tmp_path, "project")])
    service = SkillService(registry)
    app.dependency_overrides[require_skill_service] = lambda: service

    try:
        response = TestClient(app).get("/skills/governance")
    finally:
        app.dependency_overrides.pop(require_skill_service, None)

    assert response.status_code == 200
    assert response.json()["summary"]["cleanup_candidate_count"] == 1
    assert response.json()["cleanup_candidates"][0]["name"] == "old-helper"
