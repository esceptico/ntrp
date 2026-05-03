from pathlib import Path

from ntrp.server.app import app

SERVER_DIR = Path(__file__).resolve().parents[1]
SERVER_ROOT = SERVER_DIR / "ntrp"


def server_path(path: str) -> Path:
    return Path(path)


def test_backend_persistence_tables_are_only_referenced_by_owner_modules():
    table_owners = {
        "outbox_events": {server_path("ntrp/outbox/store.py")},
        "scheduled_tasks": {server_path("ntrp/automation/store.py")},
        "automation_event_dedupe": {server_path("ntrp/automation/store.py")},
        "automation_event_queue": {server_path("ntrp/automation/store.py")},
        "automation_count_state": {server_path("ntrp/automation/store.py")},
        "chat_extraction_state": {server_path("ntrp/automation/store.py")},
        "monitor_state": {server_path("ntrp/monitor/store.py")},
        "memory_events": {
            server_path("ntrp/memory/store/base.py"),
            server_path("ntrp/memory/store/events.py"),
            server_path("ntrp/memory/store/migrations.py"),
        },
    }

    violations: list[str] = []
    for path in SERVER_ROOT.rglob("*.py"):
        rel = path.relative_to(SERVER_DIR)
        source = path.read_text()
        for table, allowed_paths in table_owners.items():
            if table in source and rel not in allowed_paths:
                violations.append(f"{table} referenced from {rel}")

    assert violations == []


def test_services_do_not_import_runtime_composition_root():
    violations: list[str] = []
    for path in SERVER_ROOT.joinpath("services").rglob("*.py"):
        rel = path.relative_to(SERVER_DIR)
        source = path.read_text()
        if "ntrp.server.runtime" in source:
            violations.append(f"runtime imported from {rel}")

    assert violations == []


def test_server_app_does_not_own_http_route_handlers():
    source = SERVER_ROOT.joinpath("server/app.py").read_text()
    route_decorators = ("@app.get(", "@app.post(", "@app.put(", "@app.patch(", "@app.delete(")

    assert not any(decorator in source for decorator in route_decorators)


def test_server_routes_are_unique_by_method_and_path():
    seen: dict[tuple[tuple[str, ...], str], str] = {}
    duplicates: list[str] = []

    for route in app.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if not methods or not path:
            continue
        key = (tuple(sorted(methods)), path)
        name = getattr(route, "name", "<unnamed>")
        if key in seen:
            duplicates.append(f"{','.join(key[0])} {path}: {seen[key]} and {name}")
        else:
            seen[key] = name

    assert duplicates == []
