import json

from click.testing import CliRunner
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ntrp.cli import main
from ntrp.server.routers.runtime_info import router


def test_agent_surface_manifest_discovers_path_ids(tmp_path):
    from ntrp.agent_surface.discovery import discover_agent_surface
    from ntrp.agent_surface.manifest import write_manifest

    skill = tmp_path / "agent" / "skills" / "revenue-definitions" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: revenue-definitions\ndescription: Revenue terms.\n---\nBody\n")
    schedule = tmp_path / "agent" / "schedules" / "memory" / "rebuild.yaml"
    schedule.parent.mkdir(parents=True)
    schedule.write_text('cron: "0 9 * * *"\nprompt: "Rebuild memory."\n')

    manifest = discover_agent_surface(tmp_path)
    path = write_manifest(tmp_path, manifest)

    assert manifest.skills[0].id == "revenue-definitions"
    assert manifest.schedules[0].id == "memory/rebuild"
    assert path == tmp_path / ".ntrp" / "manifest.json"
    data = json.loads(path.read_text())
    assert data["agent_surface"]["root"] == "agent/"
    assert data["skills"][0]["id"] == "revenue-definitions"
    assert data["schedules"][0]["id"] == "memory/rebuild"


def test_runtime_info_endpoint_returns_manifest(tmp_path, monkeypatch):
    from ntrp.agent_surface.runtime_info import build_runtime_info

    (tmp_path / "agent" / "skills" / "demo").mkdir(parents=True)
    (tmp_path / "agent" / "skills" / "demo" / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Demo skill.\n---\nBody\n"
    )
    monkeypatch.chdir(tmp_path)

    test_app = FastAPI()
    test_app.include_router(router)

    response = TestClient(test_app).get("/runtime/info")

    assert response.status_code == 200
    assert response.json() == build_runtime_info(tmp_path).model_dump(mode="json")


def test_cli_info_prints_runtime_info(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(main, ["info"])

    assert result.exit_code == 0
    assert "Runtime" in result.output
    assert ".ntrp/manifest.json" in result.output
