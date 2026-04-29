from fastapi.testclient import TestClient

from ntrp.server.app import app


def test_context_routes_are_registered():
    paths = TestClient(app).get("/openapi.json").json()["paths"]

    assert "/context" in paths
    assert "/compact" in paths
    assert "/directives" in paths
