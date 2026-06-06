from ntrp.memory.models import Provenance, ScopeKind
from ntrp.server.routers.memory import _pin_write_request


def test_pin_write_request_defaults_to_user_scope():
    req = _pin_write_request("the user prefers dark mode", None)
    assert req.content == "the user prefers dark mode"
    assert req.scope.kind == ScopeKind.USER
    assert req.provenance == Provenance.USER_AUTHORED
    assert req.bypass_admit is True
    assert req.source_refs and req.source_refs[0].kind == "desktop_pin"


def test_pin_write_request_uses_project_scope_when_given():
    req = _pin_write_request("auth uses JWT", "proj-123")
    assert req.scope.kind == ScopeKind.PROJECT
    assert req.scope.key == "proj-123"
    assert req.provenance == Provenance.USER_AUTHORED
