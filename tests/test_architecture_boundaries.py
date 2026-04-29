from pathlib import Path

from ntrp.server.app import app

ROOT = Path(__file__).resolve().parents[1]


def test_backend_persistence_tables_are_only_referenced_by_owner_modules():
    table_owners = {
        "outbox_events": {Path("ntrp/outbox/store.py")},
        "scheduled_tasks": {Path("ntrp/automation/store.py")},
        "automation_event_dedupe": {Path("ntrp/automation/store.py")},
        "automation_event_queue": {Path("ntrp/automation/store.py")},
        "automation_count_state": {Path("ntrp/automation/store.py")},
        "chat_extraction_state": {Path("ntrp/automation/store.py")},
        "monitor_state": {Path("ntrp/monitor/store.py")},
    }

    violations: list[str] = []
    for path in ROOT.joinpath("ntrp").rglob("*.py"):
        rel = path.relative_to(ROOT)
        source = path.read_text()
        for table, allowed_paths in table_owners.items():
            if table in source and rel not in allowed_paths:
                violations.append(f"{table} referenced from {rel}")

    assert violations == []


def test_services_do_not_import_runtime_composition_root():
    violations: list[str] = []
    for path in ROOT.joinpath("ntrp/services").rglob("*.py"):
        rel = path.relative_to(ROOT)
        source = path.read_text()
        if "ntrp.server.runtime" in source:
            violations.append(f"runtime imported from {rel}")

    assert violations == []


def test_server_app_does_not_own_http_route_handlers():
    source = ROOT.joinpath("ntrp/server/app.py").read_text()
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
