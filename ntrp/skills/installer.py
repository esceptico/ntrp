from pathlib import Path

import httpx

from ntrp.logging import get_logger

_logger = get_logger(__name__)

GITHUB_API = "https://api.github.com"


async def install_from_github(source: str, target_dir: Path) -> str:
    parts = source.strip("/").split("/")
    if len(parts) < 3:
        raise ValueError(f"Expected 'owner/repo/path/to/skill', got: {source}")

    owner, repo = parts[0], parts[1]
    path = "/".join(parts[2:])
    skill_name = parts[-1]

    skill_dir = target_dir / skill_name
    if skill_dir.exists():
        raise ValueError(f"Skill '{skill_name}' already exists at {skill_dir}")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            await _download_dir(client, owner, repo, path, skill_dir)
    except httpx.HTTPStatusError as e:
        _cleanup(skill_dir)
        if e.response.status_code == 404:
            raise ValueError(f"Not found: {source}") from None
        raise ValueError(f"GitHub API error: {e.response.status_code}") from None
    except Exception:
        _cleanup(skill_dir)
        raise

    if not (skill_dir / "SKILL.md").exists():
        _cleanup(skill_dir)
        raise ValueError(f"No SKILL.md found in {source}")

    _logger.info("Installed skill '%s' from %s", skill_name, source)
    return skill_name


async def _download_dir(
    client: httpx.AsyncClient, owner: str, repo: str, path: str, target: Path,
) -> None:
    url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
    resp = await client.get(url, headers={"Accept": "application/vnd.github.v3+json"})
    resp.raise_for_status()
    items = resp.json()

    target.mkdir(parents=True, exist_ok=True)

    for item in items:
        if item["type"] == "file":
            file_resp = await client.get(item["download_url"])
            file_resp.raise_for_status()
            (target / item["name"]).write_bytes(file_resp.content)
        elif item["type"] == "dir":
            await _download_dir(client, owner, repo, f"{path}/{item['name']}", target / item["name"])


def _cleanup(path: Path) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)
